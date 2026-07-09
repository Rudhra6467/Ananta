"""
Trading Engine - the orchestration loop.
Fuses Layers 1-4 into Layer 5 (fusion) and Layer 6 (risk) and persists outcomes.
Runs as a periodic background task. Paper-only by default.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from ai_reasoning import MacroBias, analyze_macro
from analytics import compute_entry_volatility, sector_for_symbol
from asset_profiles import asset_class as get_asset_class
from asset_profiles import scan_interval
from breakout_classifier import detect_breakout
from live_execution import ExecutionResult, LiveExecutor, get_default_executor, get_dry_run_executor
from market_data import fetch_ohlcv_1h, fetch_snapshot
from models import (
    AIReasoning,
    PendingOrder,
    Portfolio,
    Position,
    RiskSettings,
    TradeLog,
    compute_return_and_hold,
)
from market_context import get_sector_context
from news_source import get_cache_info, get_current_summary
from research import log_evaluation_cycle
from shadow_sim import maybe_open_shadow
from risk_engine import compute_kill_switches, fuse_signals, position_size_quantity
from setup_classifier import classify_setup
from strategies import scan_strategies, STRATEGY_DEFS, ema
from levels import get_levels, nearest_resistance, nearest_support
from primary_layer import evaluate_primary, fifty_pct_metric
from regime import classify_regime
from router import continuation_allowed, route, squeeze_allowed
from squeeze import evaluate_squeeze
from continuation import evaluate_continuation
from strategy_runtime import overlay_settings, resolve_active_params
from circuit_breaker import evaluate_breaker

logger = logging.getLogger(__name__)

# EXECUTION TIMEFRAME = 1h. All strategy + exit signals process 1h candles.
# 750 bars ≈ 31 days — enough for EMA200 (200h ≈ 8d) + ATR/regime lookbacks.
EXEC_BARS_LIMIT = 750



def _market_regime(btc_closes: list[float]) -> str:
    """BTC structural regime (SOFT metric, logged not gating): BULL / NEUTRAL / BEAR."""
    if len(btc_closes) < 200:
        return "NEUTRAL"
    e50 = ema(btc_closes, 50)[-1]
    e200 = ema(btc_closes, 200)[-1]
    price = btc_closes[-1]
    if price > e50 > e200:
        return "BULL"
    if price < e50 < e200:
        return "BEAR"
    return "NEUTRAL"


def _rel_strength(asset_closes: list[float], btc_closes: list[float], n: int = 30) -> float | None:
    """Relative strength vs BTC over n 4H bars (SOFT metric): asset%% − BTC%%."""
    if len(asset_closes) < n + 1 or len(btc_closes) < n + 1:
        return None
    a = (asset_closes[-1] / asset_closes[-1 - n] - 1.0) * 100.0
    b = (btc_closes[-1] / btc_closes[-1 - n] - 1.0) * 100.0
    return round(a - b, 3)


# Monotonic cycle counter for staggered multi-asset scanning (credit control).
_SCAN_CYCLE = 0


# ---------- per-symbol cooldown helpers ----------
async def get_symbol_cooldown(db: AsyncIOMotorDatabase, symbol: str) -> dict | None:
    """Returns the cooldown doc if active, else None.
    Auto-deletes expired entries."""
    doc = await db.cooldowns.find_one({"_id": symbol})
    if not doc:
        return None
    try:
        unlock = datetime.fromisoformat(doc["unlock_at"].replace("Z", "+00:00"))
        if unlock.tzinfo is None:
            unlock = unlock.replace(tzinfo=UTC)
    except Exception:
        return None
    if datetime.now(UTC) >= unlock:
        # cooldown expired - clear so future BUYs are not falsely blocked
        await db.cooldowns.delete_one({"_id": symbol})
        return None
    # return a freshly-built dict (never the raw Mongo doc) for JSON safety
    return {
        "unlock_at": doc.get("unlock_at"),
        "reason": doc.get("reason"),
        "started_at": doc.get("started_at"),
    }


async def set_symbol_cooldown(
    db: AsyncIOMotorDatabase, symbol: str, seconds: int, reason: str,
) -> None:
    if seconds <= 0:
        return
    unlock_at = datetime.now(UTC) + timedelta(seconds=int(seconds))
    await db.cooldowns.replace_one(
        {"_id": symbol},
        {"_id": symbol, "unlock_at": unlock_at.isoformat(), "reason": reason,
         "started_at": datetime.now(UTC).isoformat()},
        upsert=True,
    )


# ---------- persistence helpers ----------
async def load_settings(db: AsyncIOMotorDatabase) -> RiskSettings:
    """Load the `settings` singleton — the ONLY config the live engine reads.

    All engine modules (trading_engine, exit_engine, risk_engine, position_watcher,
    shadow_sim, levels, backtest) receive their configuration exclusively via the
    RiskSettings returned here. Do not add engine reads from other collections
    (e.g. strategy_configs); route new tunables through RiskSettings instead.
    """
    doc = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    if not doc:
        s = RiskSettings()
        await db.settings.insert_one(s.model_dump())
        return s
    return RiskSettings(**doc)


async def load_strategy_states(db: AsyncIOMotorDatabase) -> dict[str, dict]:
    """Read the per-strategy lifecycle status set in the Strategy Center.
    Returns {key: {"status": str, "enabled": bool}}. Missing rows default to
    an enabled PAPER strategy so behaviour is unchanged until an owner toggles it."""
    states: dict[str, dict] = {}
    with contextlib.suppress(Exception):
        rows = await db.strategy_meta.find({}, {"_id": 0, "key": 1, "status": 1, "enabled": 1}).to_list(200)
        for r in rows:
            k = r.get("key")
            if k:
                states[k] = {"status": r.get("status", "PAPER"), "enabled": r.get("enabled", True)}
    return states


def strategy_entry_allowed(states: dict[str, dict], key: str) -> bool:
    """A strategy may open NEW positions unless it is explicitly DISABLED/ERROR
    or toggled off. LIVE/PAPER/TESTING/OPTIMIZING all permit entries (paper book)."""
    st = states.get(key)
    if not st:
        return True  # default-on until an owner sets a state
    if st.get("enabled") is False:
        return False
    return st.get("status") not in ("DISABLED", "ERROR")


async def save_settings(db: AsyncIOMotorDatabase, settings: RiskSettings) -> RiskSettings:
    settings.updated_at = datetime.now(UTC).isoformat()
    await db.settings.replace_one({"id": "singleton"}, settings.model_dump(), upsert=True)
    return settings


async def load_portfolio(db: AsyncIOMotorDatabase) -> Portfolio:
    doc = await db.portfolio.find_one({"id": "singleton"}, {"_id": 0})
    if not doc:
        p = Portfolio()
        await db.portfolio.insert_one(p.model_dump())
        return p
    p = Portfolio(**doc)
    # ensure day rollover even when no trading cycle has run
    today = datetime.now(UTC).date().isoformat()
    if p.day_start_date != today:
        equity = p.cash + sum(pos.cost_basis for pos in p.positions)
        p.day_start_equity = equity
        p.day_start_date = today
        await db.portfolio.replace_one({"id": "singleton"}, p.model_dump(), upsert=True)
    return p


async def save_portfolio(db: AsyncIOMotorDatabase, portfolio: Portfolio) -> Portfolio:
    portfolio.updated_at = datetime.now(UTC).isoformat()
    await db.portfolio.replace_one({"id": "singleton"}, portfolio.model_dump(), upsert=True)
    return portfolio


async def reset_portfolio(db: AsyncIOMotorDatabase) -> Portfolio:
    fresh = Portfolio()
    await db.portfolio.replace_one({"id": "singleton"}, fresh.model_dump(), upsert=True)
    await db.trades.delete_many({})
    await db.reasoning.delete_many({})
    return fresh


def _ensure_day_start(p: Portfolio) -> Portfolio:
    today = datetime.now(UTC).date().isoformat()
    if p.day_start_date != today:
        equity = p.cash + sum(pos.cost_basis for pos in p.positions)
        p.day_start_equity = equity
        p.day_start_date = today
    return p


# ---------- Vault Engine (live capital sourcing) ----------
async def apply_vault_sync(portfolio: Portfolio, settings: RiskSettings) -> dict:
    """Source deployable capital.

    When ``vault_sync_enabled`` is True AND the mode is LIVE/DRY_RUN, fetch the
    free USD/USDC balance from the exchange and cap the bot's deployable cash at
    ``vault_max_override_usd`` (the override is a CEILING only, never a floor).
    The live balance is used when it is smaller than the cap.

    PAPER mode is fully simulated and left untouched (live balance never bleeds
    into the paper sandbox). Returns an evidence dict for the reasoning log.
    """
    if not settings.vault_sync_enabled:
        return {"vault_sync": False}
    if settings.trading_mode not in ("LIVE", "DRY_RUN"):
        return {"vault_sync": False, "note": "ignored in PAPER mode"}

    if settings.trading_mode == "LIVE":
        executor, err = get_default_executor()
    else:
        executor, err = get_dry_run_executor()
    if executor is None:
        return {"vault_sync": "executor_unavailable", "error": err}

    free = await executor.fetch_free_quote_balance()
    if free is None:
        return {"vault_sync": "balance_unavailable",
                "note": "fetch_balance failed (needs private API keys)"}

    cap = float(settings.vault_max_override_usd)
    deployable = min(free, cap)
    portfolio.cash = deployable
    return {
        "vault_sync": True,
        "free_balance_usd": round(free, 4),
        "override_cap_usd": cap,
        "deployable_cash_usd": round(deployable, 4),
    }


# ---------- Execution Friction Layer (Phase B) ----------
async def log_friction_tally(db: AsyncIOMotorDatabase, settings: RiskSettings) -> dict:
    """Compute + log the rolling 24h Total Friction Cost (maker/taker fees +
    realized execution slippage) to the console. Returns the tally dict."""
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    docs = await db.trades.find(
        {"timestamp": {"$gte": cutoff}}, {"_id": 0, "fee_usd": 1, "slippage_usd": 1},
    ).to_list(2000)
    fees = sum(float(d.get("fee_usd", 0.0) or 0.0) for d in docs)
    slippage = sum(float(d.get("slippage_usd", 0.0) or 0.0) for d in docs)
    total = fees + slippage
    logger.info(
        "TOTAL FRICTION COST (rolling 24h): fees=$%.4f + slippage=$%.4f = $%.4f",
        fees, slippage, total,
    )
    return {"fees_usd": round(fees, 4), "slippage_usd": round(slippage, 4), "total_friction_usd": round(total, 4)}


async def process_pending_orders(db: AsyncIOMotorDatabase) -> list[dict]:
    """Resolve resting PAPER Post-Only maker BUY orders each watcher tick.

    Fill rules (per user spec):
      * price crosses through our bid (last <= our_bid) -> FILL @ our_bid
      * price stays flat at our bid for 2 consecutive ticks -> FILL @ our_bid
      * best bid ticks up away from our resting bid -> MISSED_FILL_PRICE_RUN (cancel)

    Filled maker entries pay the lower maker fee.
    """
    pendings = await db.pending_orders.find({}).to_list(100)
    if not pendings:
        return []

    settings = await load_settings(db)
    portfolio = _ensure_day_start(await load_portfolio(db))
    results: list[dict] = []
    dirty = False

    for raw in pendings:
        po = PendingOrder(**raw)
        snap = await fetch_snapshot(po.symbol)
        if snap is None:
            continue
        our_bid = po.limit_price
        fill = False
        fill_reason = ""

        if snap.price <= our_bid:
            fill, fill_reason = True, "PRICE_CROSSED"
        elif snap.bid > our_bid * (1.0 + 1e-4):
            # market bid moved up away from our resting maker bid -> we got left behind
            await db.pending_orders.delete_one({"id": po.id})
            logger.info("MISSED_FILL_PRICE_RUN %s — price ran up (bid %.6f > resting %.6f); maker order cancelled",
                        po.symbol, snap.bid, our_bid)
            await db.reasoning.insert_one(AIReasoning(
                symbol=po.symbol, bias="NEUTRAL", confidence=0.0,
                reason="Post-Only maker order cancelled: MISSED_FILL_PRICE_RUN",
                news_summary="(position-watcher; maker fill simulation)",
                evidence={"source": "pending_order", "outcome": "MISSED_FILL_PRICE_RUN",
                          "resting_bid": our_bid, "current_bid": snap.bid, "current_price": snap.price},
                decision="BLOCKED", blocked_reasons=["MISSED_FILL_PRICE_RUN"],
            ).model_dump())
            results.append({"symbol": po.symbol, "outcome": "MISSED_FILL_PRICE_RUN"})
            continue
        else:
            # flat at our bid — wait up to 2 ticks
            new_ticks = po.ticks_flat + 1
            if new_ticks >= 2:
                fill, fill_reason = True, "FLAT_2_TICKS"
            else:
                await db.pending_orders.update_one({"id": po.id}, {"$set": {"ticks_flat": new_ticks}})
                continue

        if fill:
            # cap by available cash (incl. maker fee); if insufficient, cancel.
            fee_factor = 1.0 + settings.maker_fee_pct / 100.0
            notional_needed = po.quantity * our_bid * fee_factor
            if notional_needed > portfolio.cash:
                await db.pending_orders.delete_one({"id": po.id})
                logger.info("PAPER maker fill %s cancelled — insufficient cash (%.4f < %.4f incl fee)",
                            po.symbol, portfolio.cash, notional_needed)
                results.append({"symbol": po.symbol, "outcome": "CANCELLED_NO_CASH"})
                continue

            notional, fee = _execute_buy(portfolio, po.symbol, po.quantity, our_bid, settings.maker_fee_pct)
            if notional <= 0:
                # defensive: _execute_buy declined (e.g. rounding/cash edge) — cancel, don't leave it stuck
                await db.pending_orders.delete_one({"id": po.id})
                logger.info("PAPER maker fill %s cancelled — _execute_buy declined", po.symbol)
                results.append({"symbol": po.symbol, "outcome": "CANCELLED_NO_CASH"})
                continue
            new_pos = next((p for p in portfolio.positions if p.symbol == po.symbol), None)
            if new_pos is not None and new_pos.sector is None:
                new_pos.sector = po.sector
                new_pos.atr_at_entry = po.atr_at_entry
                new_pos.atr_percentile_at_entry = po.atr_percentile_at_entry
                new_pos.volatility_regime = po.volatility_regime
                new_pos.entry_extension_pct = po.entry_extension_pct
                new_pos.structural_stop = po.structural_stop
                if not new_pos.entry_attribution:
                    new_pos.entry_attribution = getattr(po, "entry_attribution", None) or {}
            # Phase E: stamp the independent-model identity onto the Hunter position.
            if new_pos is not None:
                _attr = new_pos.entry_attribution or {}
                _eq = _attr.get("entry_quality") or {}
                new_pos.strategy = "hunter"
                new_pos.entry_profile = _attr.get("entry_profile")
                new_pos.entry_quality_grade = _eq.get("grade")
                new_pos.entry_quality_score = _eq.get("pct")
                new_pos.regime_at_entry = _attr.get("asset_regime")
            trade = TradeLog(
                symbol=po.symbol, side="BUY", quantity=po.quantity, price=our_bid,
                notional=notional, mode="PAPER", confidence=0.0,
                reasoning_id=po.reasoning_id, fee_usd=fee, slippage_usd=0.0,
                note=f"[POST-ONLY MAKER fill: {fill_reason}] resting bid {our_bid:.6f}",
                sector=po.sector, atr_at_entry=po.atr_at_entry,
                atr_percentile_at_entry=po.atr_percentile_at_entry, volatility_regime=po.volatility_regime,
                entry_extension_pct=po.entry_extension_pct,
            )
            await db.trades.insert_one(trade.model_dump())
            await db.pending_orders.delete_one({"id": po.id})
            dirty = True
            logger.info("PAPER POST-ONLY maker FILLED %s qty=%.8f @ %.6f (%s, maker fee $%.4f)",
                        po.symbol, po.quantity, our_bid, fill_reason, fee)
            try:
                from push_service import send_push_event
                _g = (getattr(new_pos, "entry_quality_grade", None) if new_pos else None)
                await send_push_event(
                    db, "trade_opened",
                    f"Hunter opened {po.symbol}" + (f" (grade {_g})" if _g else ""),
                )
            except Exception:
                pass
            results.append({"symbol": po.symbol, "outcome": "FILLED", "reason": fill_reason, "trade": trade.model_dump()})

    if dirty:
        await save_portfolio(db, portfolio)
        await log_friction_tally(db, settings)
    return results



# ---------- trade execution (PAPER) ----------
def _execute_buy(p: Portfolio, symbol: str, qty: float, price: float, fee_pct: float = 0.0) -> tuple[float, float]:
    """PAPER BUY. Returns (filled_notional, fee_usd). Fee is debited from cash on top of notional."""
    notional = qty * price
    fee = notional * (fee_pct / 100.0)
    total_cost = notional + fee
    if total_cost > p.cash:
        return 0.0, 0.0
    p.cash -= total_cost
    pos = next((x for x in p.positions if x.symbol == symbol), None)
    if pos is None:
        p.positions.append(
            Position(symbol=symbol, quantity=qty, avg_cost=price, peak_price=price, fee_paid_buy=fee)
        )
    else:
        total_basis = pos.cost_basis + notional
        total_qty = pos.quantity + qty
        pos.quantity = total_qty
        pos.avg_cost = total_basis / total_qty if total_qty > 0 else 0.0
        pos.fee_paid_buy += fee
    return notional, fee


def _execute_sell(p: Portfolio, symbol: str, price: float, fee_pct: float = 0.0) -> tuple[float, float, float, float]:
    """Close full position. Returns (qty, notional, realized_pnl_net, fee_usd).
    realized_pnl_net = gross P&L - sell-side fee - buy-side fees paid for this position."""
    pos = next((x for x in p.positions if x.symbol == symbol), None)
    if pos is None or pos.quantity <= 0:
        return 0.0, 0.0, 0.0, 0.0
    qty = pos.quantity
    notional = qty * price
    fee = notional * (fee_pct / 100.0)
    gross = (price - pos.avg_cost) * qty
    realized_net = gross - fee - pos.fee_paid_buy
    p.cash += notional - fee
    p.realized_pnl += realized_net
    p.positions = [x for x in p.positions if x.symbol != symbol]
    return qty, notional, realized_net, fee


def _execute_partial_sell(
    p: Portfolio, symbol: str, price: float, fraction: float, fee_pct: float = 0.0,
) -> tuple[float, float, float, float]:
    """Sell a fraction (0..1) of a position; keep the remainder open.
    Returns (qty_sold, notional, realized_pnl_net, fee_usd). Buy-side fees are
    allocated proportionally so the remaining lot keeps its share."""
    pos = next((x for x in p.positions if x.symbol == symbol), None)
    if pos is None or pos.quantity <= 0:
        return 0.0, 0.0, 0.0, 0.0
    fraction = max(0.0, min(1.0, fraction))
    qty = pos.quantity * fraction
    if qty <= 0:
        return 0.0, 0.0, 0.0, 0.0
    notional = qty * price
    fee = notional * (fee_pct / 100.0)
    gross = (price - pos.avg_cost) * qty
    buy_fee_alloc = pos.fee_paid_buy * fraction
    realized_net = gross - fee - buy_fee_alloc
    p.cash += notional - fee
    p.realized_pnl += realized_net
    pos.quantity -= qty
    pos.fee_paid_buy -= buy_fee_alloc
    if pos.quantity < 1e-12:
        p.positions = [x for x in p.positions if x.symbol != symbol]
    return qty, notional, realized_net, fee


# ---------- live execution bookkeeping ----------
async def _record_live_buy(
    db: AsyncIOMotorDatabase,
    portfolio: Portfolio,
    symbol: str,
    result: ExecutionResult,
    reasoning: AIReasoning,
    macro_confidence: float,
    fusion_summary: str,
    mode: str = "LIVE",
    sector: str | None = None,
    atr_at_entry: float | None = None,
    atr_percentile_at_entry: float | None = None,
    volatility_regime: str | None = None,
    entry_extension_pct: float | None = None,
) -> dict | None:
    """Persist a LIVE BUY using the actual fills returned by the exchange.
    Returns the trade doc, or None if nothing was filled."""
    if not result.is_fill:
        # Log a rejected/cancelled/aborted trade record so the operator can audit it.
        trade = TradeLog(
            symbol=symbol, side="BUY", quantity=0.0, price=result.limit_price,
            notional=0.0, mode=mode, confidence=macro_confidence,
            reasoning_id=reasoning.id, status="REJECTED",
            note=f"[{result.status}] {result.reason} | order={result.order_id}",
        )
        await db.trades.insert_one(trade.model_dump())
        logger.warning("%s BUY %s did not fill: %s (%s)", mode, symbol, result.status, result.reason)
        return trade.model_dump()

    # Update portfolio with the *actual* fill from the exchange
    portfolio.cash -= result.filled_notional
    pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
    if pos is None:
        portfolio.positions.append(
            Position(
                symbol=symbol, quantity=result.filled_qty, avg_cost=result.filled_price,
                peak_price=result.filled_price, sector=sector, atr_at_entry=atr_at_entry,
                atr_percentile_at_entry=atr_percentile_at_entry, volatility_regime=volatility_regime,
                entry_extension_pct=entry_extension_pct,
            )
        )
    else:
        total_cost = pos.cost_basis + result.filled_notional
        total_qty = pos.quantity + result.filled_qty
        pos.quantity = total_qty
        pos.avg_cost = (total_cost / total_qty) if total_qty > 0 else 0.0

    trade = TradeLog(
        symbol=symbol, side="BUY", quantity=result.filled_qty, price=result.filled_price,
        notional=result.filled_notional, mode=mode, confidence=macro_confidence,
        reasoning_id=reasoning.id,
        note=f"[{result.status}] limit={result.limit_price:.6f} order={result.order_id} | {fusion_summary}",
        sector=sector, atr_at_entry=atr_at_entry,
        atr_percentile_at_entry=atr_percentile_at_entry, volatility_regime=volatility_regime,
        entry_extension_pct=entry_extension_pct,
    )
    await db.trades.insert_one(trade.model_dump())
    await save_portfolio(db, portfolio)
    logger.info("%s BUY %s FILLED qty=%s @ %s (order %s)",
                mode, symbol, result.filled_qty, result.filled_price, result.order_id)
    return trade.model_dump()


async def _record_live_sell(
    db: AsyncIOMotorDatabase,
    portfolio: Portfolio,
    symbol: str,
    result: ExecutionResult,
    reasoning: AIReasoning,
    macro_confidence: float,
    fusion_summary: str,
    mode: str = "LIVE",
    exit_reason: str | None = None,
    expected_trigger_price: float | None = None,
    exit_module: str | None = None,
) -> dict | None:
    """Persist a LIVE SELL. Realised P/L is based on the actual fill, and the
    position is decremented by the exact filled amount (partials supported)."""
    if not result.is_fill:
        trade = TradeLog(
            symbol=symbol, side="SELL", quantity=0.0, price=result.limit_price,
            notional=0.0, mode=mode, confidence=macro_confidence,
            reasoning_id=reasoning.id, status="REJECTED",
            note=f"[{result.status}] {result.reason} | order={result.order_id}",
        )
        await db.trades.insert_one(trade.model_dump())
        logger.warning("%s SELL %s did not fill: %s (%s)", mode, symbol, result.status, result.reason)
        return trade.model_dump()

    pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
    if pos is None or pos.quantity <= 0:
        # Defensive: exchange filled a sell but we have no internal position. Log & continue.
        logger.warning("%s SELL %s filled but no internal position to debit", mode, symbol)
        avg_cost = result.filled_price  # P/L unknown
        entry_sector = entry_atr = entry_atr_pct = entry_regime = None
        entry_ext = None
        _strategy = _entry_profile = _regime_at_entry = _eq_grade = None
        _mfe = _mae = _best = _worst = None
        _attr = {}
    else:
        avg_cost = pos.avg_cost
        entry_sector = pos.sector
        entry_atr = pos.atr_at_entry
        entry_atr_pct = pos.atr_percentile_at_entry
        entry_regime = pos.volatility_regime
        entry_ext = pos.entry_extension_pct
        _strategy = pos.strategy
        _entry_profile = pos.entry_profile
        _regime_at_entry = pos.regime_at_entry
        _eq_grade = pos.entry_quality_grade
        _mfe = pos.mfe_pct
        _mae = pos.mae_pct
        _best = pos.peak_price or None
        _worst = pos.trough_price or None
        _attr = pos.entry_attribution or {}
    realized = (result.filled_price - avg_cost) * result.filled_qty
    portfolio.cash += result.filled_notional
    portfolio.realized_pnl += realized
    if pos is not None:
        pos.quantity -= result.filled_qty
        if pos.quantity < 1e-12:
            portfolio.positions = [p for p in portfolio.positions if p.symbol != symbol]

    # realized execution slippage: (expected_trigger - actual_fill) * qty (>=0 = cost)
    trigger = expected_trigger_price if expected_trigger_price is not None else result.filled_price
    slippage_usd = (trigger - result.filled_price) * result.filled_qty

    trade = TradeLog(
        symbol=symbol, side="SELL", quantity=result.filled_qty, price=result.filled_price,
        notional=result.filled_notional, mode=mode, confidence=macro_confidence,
        reasoning_id=reasoning.id, pnl=realized, slippage_usd=slippage_usd,
        note=f"[{result.status}] limit={result.limit_price:.6f} order={result.order_id} | {fusion_summary}",
        exit_reason=exit_reason, exit_module=exit_module,
        potential_best_exit=_best, potential_worst_exit=_worst,
        sector=entry_sector, atr_at_entry=entry_atr,
        atr_percentile_at_entry=entry_atr_pct, volatility_regime=entry_regime,
        entry_extension_pct=entry_ext,
        trade_result=("WIN" if realized > 0 else "LOSS" if realized < 0 else "BREAKEVEN"),
        mfe_pct=_mfe, mae_pct=_mae,
        strategy=_strategy, entry_profile=_entry_profile, regime_at_entry=_regime_at_entry,
        entry_quality_grade=_eq_grade, entry_attribution=_attr,
    )
    await db.trades.insert_one(trade.model_dump())
    await save_portfolio(db, portfolio)
    logger.info("%s SELL %s FILLED qty=%s @ %s, realised=%.4f",
                mode, symbol, result.filled_qty, result.filled_price, realized)
    return trade.model_dump()


# ---------- single evaluation cycle for one symbol ----------
async def evaluate_symbol(db: AsyncIOMotorDatabase, symbol: str) -> dict:
    settings = await load_settings(db)
    strategy_states = await load_strategy_states(db)
    # P3: per-strategy engine configs. Each strategy resolves its OWN entry/exit/lot
    # params from its active config, overlaid on the global account-level baseline.
    # With no active config the overlay is a no-op → identical behaviour.
    _cfg_params = await resolve_active_params(db)
    hunter_settings = overlay_settings(settings, _cfg_params.get("hunter"))
    squeeze_settings = overlay_settings(settings, _cfg_params.get("squeeze"))
    cont_settings = overlay_settings(settings, _cfg_params.get("continuation"))
    portfolio = _ensure_day_start(await load_portfolio(db))

    # Vault Engine: source deployable capital (live balance capped by override).
    vault_evidence = await apply_vault_sync(portfolio, settings)

    snapshot = await fetch_snapshot(symbol)
    if snapshot is None:
        logger.warning("No market snapshot for %s; skipping cycle", symbol)
        return {"symbol": symbol, "status": "no_market_data"}

    # Hard-kill pre-check (manual / spread / daily-loss): skip the costly news +
    # sector + Gemini calls entirely when trading is hard-blocked. Saves LLM credits
    # and keeps full-watchlist cycles fast.
    _pre_kill = compute_kill_switches(snapshot, portfolio, settings, 0.0)
    _hard_killed = _pre_kill.manual_kill or _pre_kill.spread_breach or _pre_kill.daily_loss_breach

    # CREDIT GUARD: the Hunter (pure compute) is the SOLE entry driver; Gemini only feeds
    # the dormant Circuit Breaker + soft sizing and can never turn a HOLD into a BUY. So
    # evaluate the Hunter FIRST and only spend an LLM call when a real setup triggers. On
    # idle scans (the vast majority) Gemini is skipped entirely -> ~99% credit reduction.
    # EXECUTION TIMEFRAME = 1h: all strategy + exit signals now process 1h candles.
    bars_1h: list[list[float]] = []
    try:
        bars_1h = await fetch_ohlcv_1h(symbol, limit=EXEC_BARS_LIMIT)
    except Exception as e:
        logger.warning("1h OHLCV fetch failed for %s: %s", symbol, e)
        bars_1h = []
    zones_cache: list[dict] | None = None
    hunter_triggered = False
    if not _hard_killed and getattr(settings, "level_entry_enabled", True):
        try:
            zones_cache = await get_levels(symbol, settings)
            _pp = evaluate_primary(symbol, snapshot.price, bars_1h, zones_cache, hunter_settings)
            hunter_triggered = bool(_pp.triggered)
        except Exception as e:
            logger.warning("Early Hunter pre-check failed for %s: %s", symbol, e)
            hunter_triggered = True  # fail-open: never silently suppress reasoning on error

    if _hard_killed:
        news = ""
        sector = {"prompt_block": "", "data": {}}
        macro = MacroBias(
            bias="NEUTRAL", confidence=0.0, model="skipped",
            reason="Hard kill-switch active; AI reasoning skipped to preserve credits.",
        )
    elif hunter_triggered:
        news = await get_current_summary(salt=symbol)
        sector = await get_sector_context(symbol)
        macro = await analyze_macro(symbol=symbol, news_summary=news, sector_context=sector.get("prompt_block", ""))
    else:
        news = ""
        sector = {"prompt_block": "", "data": {}}
        macro = MacroBias(
            bias="NEUTRAL", confidence=0.0, model="no-setup-skip",
            reason="Hunter found no qualifying setup; AI reasoning skipped to preserve credits.",
        )

    # --- adaptive setup classification (Layer 5b) ---
    setup_strength = "NONE"
    setup_evidence: dict = {}
    if settings.adaptive_sizing_enabled:
        setup_strength, setup_evidence = classify_setup(
            bars_1h,
            macro.confidence,
            macro.bias,
            min_strong_confidence=settings.strong_min_confidence,
            min_atr_percentile=settings.strong_min_atr_percentile,
            min_adx=settings.strong_min_adx,
        )

    # --- Systemic Breakout filter (Layer 5c) ---
    is_breakout, breakout_evidence = detect_breakout(
        bars_1h,
        macro_bias=macro.bias,
        macro_confidence=macro.confidence,
        spread_pct=snapshot.spread_pct,
        min_confidence=settings.breakout_min_confidence,
        volume_percentile_floor=settings.breakout_volume_percentile,
        max_spread_pct=settings.breakout_max_spread_pct,
    )

    # --- Higher-timeframe swing trend filter (1h EMA stack) ---
    htf_trend_aligned: bool | None = None
    htf_evidence: dict = {}
    entry_extension_pct: float | None = None  # how far above 1h EMA50 price sits at entry (chase-risk)
    if settings.htf_trend_enabled:
        closes_1h = [b[4] for b in bars_1h]
        if len(closes_1h) >= 200:
            ema50 = ema(closes_1h, 50)[-1]
            ema200 = ema(closes_1h, 200)[-1]
            last_close = closes_1h[-1]
            htf_trend_aligned = (last_close > ema50 > ema200)
            if ema50 > 0:
                entry_extension_pct = round((snapshot.price - ema50) / ema50 * 100.0, 3)
            htf_evidence = {
                "last_close_1h": round(last_close, 6),
                "ema50_1h": round(ema50, 6),
                "ema200_1h": round(ema200, 6),
                "aligned": htf_trend_aligned,
                "entry_extension_pct": entry_extension_pct,
            }
        else:
            htf_evidence = {"reason": f"need >= 200 1h bars (have {len(closes_1h)})"}
            htf_trend_aligned = False  # safer: no trade without confirmation

    kill = compute_kill_switches(snapshot, portfolio, settings, macro.confidence)
    has_position = any(p.symbol == symbol and p.quantity > 0 for p in portfolio.positions)

    # --- PRIMARY + SECONDARY layered architecture (Phase 2) ---
    support_zone: dict | None = None
    resistance_zone: dict | None = None
    at_support = False
    structural_stop: float | None = None
    rsi_4h: float | None = None
    volume_status: str | None = None
    rr_estimate: float | None = None
    level_evidence: dict = {}
    primary = None
    asset_regime = classify_regime(bars_1h) if bars_1h else None
    if getattr(settings, "level_entry_enabled", True):
        try:
            zones = zones_cache if zones_cache is not None else await get_levels(symbol, settings)
            primary = evaluate_primary(symbol, snapshot.price, bars_1h, zones, hunter_settings, regime=asset_regime, htf_trend_aligned=htf_trend_aligned)
            support_zone = primary.support_zone
            at_support = support_zone is not None
            structural_stop = primary.structural_stop
            resistance_zone = nearest_resistance(snapshot.price, zones, settings.level_proximity_pct)
            rsi_4h = primary.evidence.get("rsi_4h")
            vslope = primary.evidence.get("volume_slope")
            volume_status = None if vslope is None else ("EXHAUSTED" if vslope < 0 else "RISING")
            # SOFT R:R estimate (LOGGED, never gates): reward to nearest overhead zone / structural risk.
            if structural_stop and resistance_zone and snapshot.price > structural_stop:
                risk = snapshot.price - structural_stop
                reward = resistance_zone["mid"] - snapshot.price
                rr_estimate = round(reward / risk, 2) if risk > 0 and reward > 0 else None
            level_evidence = {
                "primary_triggered": primary.triggered,
                "primary_reason_codes": primary.reason_codes,
                "zone_count": len(zones),
                "resistance_zone": resistance_zone,
                "rr_estimate": rr_estimate,
                **primary.evidence,
            }
        except Exception as e:
            logger.warning("Primary layer failed for %s: %s", symbol, e)

    # --- SOFT context metrics (LOGGED, NEVER gating): BTC market regime + relative strength ---
    market_regime = "NEUTRAL"
    relative_strength_btc: float | None = None
    try:
        btc_bars = await fetch_ohlcv_1h("BTC/USD", limit=EXEC_BARS_LIMIT)
        btc_closes = [b[4] for b in btc_bars] if btc_bars else []
        market_regime = _market_regime(btc_closes)
        asset_closes = [b[4] for b in bars_1h] if bars_1h else []
        relative_strength_btc = 0.0 if symbol == "BTC/USD" else _rel_strength(asset_closes, btc_closes)
    except Exception:
        pass

    # --- SECONDARY: tri-state Circuit Breaker (PASS / CAUTION / VETO). VETO is
    # existential-only; sentiment/macro bearishness yields at most CAUTION (logged). ---
    breaker_state, breaker_reason = evaluate_breaker(macro.bias, macro.confidence, news_sentiment=None)

    # --- Phase B: 50% Rule / Fair-Value midpoint metric (DIAGNOSTIC only — never gates) ---
    fifty = fifty_pct_metric(bars_1h, snapshot.price)
    # Entry-feature snapshot carried onto any resulting position/trade (winner/loser analytics).
    entry_attribution = {
        "rsi_at_entry": rsi_4h,
        "volume_status": volume_status,
        "volume_score": level_evidence.get("volume_slope"),
        "support_zone_score": (support_zone or {}).get("touches"),
        "distance_from_midpoint_pct": fifty.get("distance_from_midpoint_pct"),
        "above_or_below_midpoint": fifty.get("above_or_below_midpoint"),
        "relative_strength_btc": relative_strength_btc,
        "market_regime": market_regime,
        "breaker_state": breaker_state,
        "rr_estimate": rr_estimate,
        # --- Phase E reason-chain (Hunter) ---
        "asset_regime": getattr(asset_regime, "regime", None),
        "entry_profile": (primary.entry_profile if primary is not None else None),
        "entry_quality": (primary.evidence.get("entry_quality") if primary is not None else None),
    }

    # --- Phase B Strategy Sandbox: 5 regime classifiers (pure compute; SHADOW except Hunter) ---
    strategy_signals = scan_strategies(
        snapshot.price, bars_1h, relative_strength_btc,
        bool(primary.triggered) if primary is not None else False, support_zone,
    )
    entry_attribution["support_low"] = (support_zone or {}).get("low")

    # --- Phase E2: full Reason Chain (additive log carried onto any resulting trade) ---
    routing = route(getattr(asset_regime, "regime", None))
    entry_attribution["reason_chain"] = {
        "schema": "v1",
        "regime": getattr(asset_regime, "regime", None),
        "regime_evidence": getattr(asset_regime, "evidence", {}),
        "routing": routing,
        "market_state_snapshot": [
            {"t": b[0], "o": b[1], "h": b[2], "l": b[3], "c": b[4], "v": b[5]}
            for b in (bars_1h[-12:] if bars_1h else [])
        ],
        "indicator_values": {
            "rsi_4h": rsi_4h,
            "adx": (asset_regime.evidence.get("adx") if asset_regime else None),
            "atr_percentile": (asset_regime.evidence.get("atr_percentile") if asset_regime else None),
            "bbwidth_percentile": (asset_regime.evidence.get("bbwidth_percentile") if asset_regime else None),
            "ema_stack": (asset_regime.evidence.get("ema_stack") if asset_regime else None),
            "relative_strength_btc": relative_strength_btc,
            "btc_macro_regime": market_regime,
            "volume_slope": level_evidence.get("volume_slope"),
        },
        "competing_hypotheses": [
            {"strategy": sid, "detected": v.get("detected"), "qualified": v.get("qualified")}
            for sid, v in (strategy_signals or {}).items()
        ],
        "breaker_state": breaker_state,
    }

    decision, blocked, fusion_summary = fuse_signals(
        snapshot=snapshot,
        macro_bias=macro.bias,
        macro_confidence=macro.confidence,
        settings=settings,
        kill=kill,
        has_position=has_position,
        htf_trend_aligned=htf_trend_aligned,
        at_support=at_support,
        support_zone=support_zone,
        primary_triggered=(primary.triggered if primary is not None else None),
        breaker_state=breaker_state,
    )

    # --- concurrent-position cap (queue: skip this cycle, retry next) ---
    if decision == "BUY" and not has_position:
        open_count = sum(1 for p in portfolio.positions if p.quantity > 0)
        pending_count = await db.pending_orders.count_documents({})
        total_committed = open_count + pending_count
        # PAXG anchor: reserve one slot for the lone uncorrelated hedge until it is in the book,
        # so 5 correlated crypto longs can never crowd gold out of the portfolio.
        is_paxg = symbol == "PAXG/USD"
        paxg_in_book = any(p.symbol == "PAXG/USD" and p.quantity > 0 for p in portfolio.positions) or (
            await db.pending_orders.count_documents({"symbol": "PAXG/USD"}) > 0
        )
        effective_cap = settings.max_concurrent_positions
        if not is_paxg and not paxg_in_book:
            effective_cap = max(1, settings.max_concurrent_positions - 1)
        if total_committed >= effective_cap:
            reserve_note = " (1 slot reserved for PAXG hedge)" if effective_cap < settings.max_concurrent_positions else ""
            blocked.append(
                f"MAX_POSITIONS_REACHED {total_committed}/{effective_cap}{reserve_note} "
                f"({open_count} open + {pending_count} resting maker)"
            )
            fusion_summary = (
                f"HOLD - {total_committed}/{effective_cap} concurrent slots already committed"
                f"{reserve_note}; queueing this signal for next cycle."
            )
            decision = "HOLD"

    # --- Strategy Center gate: the Hunter (primary entry driver) must be enabled ---
    # DISABLED/ERROR (or an explicit off-toggle) blocks NEW Hunter entries; open
    # positions are still managed by the exit engine. Set in the Strategy Center UI.
    if decision == "BUY" and not strategy_entry_allowed(strategy_states, "hunter"):
        _hstate = strategy_states.get("hunter", {}).get("status", "DISABLED")
        blocked.append(f"STRATEGY_DISABLED hunter status={_hstate}")
        fusion_summary = f"HOLD - Hunter strategy is {_hstate} in the Strategy Center; no new entries."
        decision = "HOLD"

    # --- per-symbol cooldown gate (no revenge trades after SL, momentum reset after trail) ---
    if decision == "BUY" and not has_position:
        cooldown = await get_symbol_cooldown(db, symbol)
        if cooldown:
            blocked.append(f"COOLDOWN_ACTIVE until={cooldown['unlock_at']} reason={cooldown.get('reason')}")
            fusion_summary = (
                f"HOLD - symbol on cooldown ({cooldown.get('reason')}) "
                f"until {cooldown['unlock_at']}."
            )
            decision = "HOLD"

    # --- per-tier liquidity / spread gate (pre-fire; 0.20% breakout / 0.50% standard) ---
    bid_spread_pct = ((snapshot.ask - snapshot.bid) / snapshot.bid * 100.0) if snapshot.bid > 0 else float("inf")
    if decision == "BUY":
        spread_cap = settings.breakout_max_spread_pct if is_breakout else settings.max_spread_pct
        if bid_spread_pct > spread_cap:
            tier = "breakout" if is_breakout else "standard"
            logger.warning(
                "Execution blocked due to insufficient liquidity: %s spread %.3f%% > %.2f%% cap (%s entry)",
                symbol, bid_spread_pct, spread_cap, tier,
            )
            blocked.append(
                f"LOW_LIQUIDITY spread {bid_spread_pct:.3f}% > {spread_cap:.2f}% cap — "
                "Execution blocked due to insufficient liquidity"
            )
            fusion_summary = (
                "HOLD - Execution blocked due to insufficient liquidity "
                f"(spread {bid_spread_pct:.3f}% > {spread_cap:.2f}% {tier} cap)."
            )
            decision = "HOLD"

    # --- Rejection-leaderboard reason codes (Phase 2) ---
    reason_codes: list[str] = []
    if decision == "BUY":
        reason_codes = ["GREENLIT"]
    else:
        if kill.manual_kill or kill.spread_breach or kill.daily_loss_breach:
            reason_codes.append("REJECTED_HARD_KILL")
        if breaker_state == "VETO":
            reason_codes.append("REJECTED_SECONDARY_VETO_EXISTENTIAL")
        if primary is not None:
            reason_codes.extend(primary.reason_codes)
        if any("MAX_POSITIONS" in b for b in blocked):
            reason_codes.append("REJECTED_MAX_POSITIONS")
        if any("COOLDOWN" in b for b in blocked):
            reason_codes.append("REJECTED_COOLDOWN")
        if any("LOW_LIQUIDITY" in b for b in blocked):
            reason_codes.append("REJECTED_LOW_LIQUIDITY")
        if not reason_codes:
            reason_codes.append("HOLD_NO_SIGNAL")
    reason_codes = list(dict.fromkeys(reason_codes))  # dedupe, preserve order

    reasoning = AIReasoning(
        symbol=symbol,
        bias=macro.bias,
        confidence=macro.confidence,
        reason=macro.reason,
        news_summary=news,
        model=macro.model,
        evidence={
            "price": snapshot.price,
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "spread_pct": round(snapshot.spread_pct, 4),
            "spread_pct_bid_based": round(bid_spread_pct, 4) if bid_spread_pct != float("inf") else None,
            "orderbook_imbalance": round(snapshot.orderbook_imbalance, 4),
            "exchange": snapshot.exchange,
            "kill_switch_details": kill.details,
            "fusion_summary": fusion_summary,
            "setup_strength": setup_strength,
            "setup_evidence": setup_evidence,
            "breakout": is_breakout,
            "breakout_evidence": breakout_evidence,
            "htf_trend_aligned": htf_trend_aligned,
            "htf_evidence": htf_evidence,
            "level": level_evidence,
            "breaker_state": breaker_state,
            "breaker_reason": breaker_reason,
            "market_regime": market_regime,
            "relative_strength_btc": relative_strength_btc,
            "vault": vault_evidence,
        },
        decision=decision,
        blocked_reasons=blocked,
    )
    await db.reasoning.insert_one(reasoning.model_dump())

    # --- Research Database (Phase 2): permanent, append-only decision log.
    # Additive + suppressed so logging can never disrupt the trading cycle. ---
    with contextlib.suppress(Exception):
        await log_evaluation_cycle(
            db,
            symbol=symbol,
            macro_confidence=macro.confidence,
            macro_bias=macro.bias,
            decision=decision,
            blocked_reasons=blocked,
            price=snapshot.price,
            setup_strength=setup_strength,
            breakout=is_breakout,
            htf_trend_aligned=htf_trend_aligned,
            reasoning_id=reasoning.id,
            news_source=get_cache_info().get("source"),
            min_confidence=settings.min_confidence,
            asset_class=get_asset_class(symbol),
            sector_data=sector.get("data") or {},
            reason_codes=reason_codes,
            support_zone=support_zone["mid"] if support_zone else None,
            resistance_zone=resistance_zone["mid"] if resistance_zone else None,
            rsi_4h=rsi_4h,
            volume_status=volume_status,
            market_regime=market_regime,
            breaker_state=breaker_state,
            relative_strength_btc=relative_strength_btc,
            rr_estimate=rr_estimate,
            fifty_pct=fifty,
            strategy_signals=strategy_signals,
        )

    # Phase B: normalized, queryable Strategy Lab log — one first-class row per
    # DETECTED opportunity per strategy (qualification + breaker recorded inline).
    # Unqualified / breaker-blocked rows resolve immediately; qualified+PASS rows are
    # left PENDING for the forward-return resolver. TTL-indexed so it can't grow unbounded.
    with contextlib.suppress(Exception):
        from uuid import uuid4
        detected_at = getattr(reasoning, "timestamp", None) or datetime.now(UTC).isoformat()
        lab_docs = []
        for d in STRATEGY_DEFS:
            sig = (strategy_signals or {}).get(d["id"]) or {}
            if not sig.get("detected"):
                continue
            qualified = bool(sig.get("qualified"))
            if not qualified:
                outcome, resolved = "UNQUALIFIED", True
            elif breaker_state != "PASS":
                outcome, resolved = "BREAKER_BLOCKED", True
            else:
                outcome, resolved = "PENDING", False
            lab_docs.append({
                "id": str(uuid4()),
                "strategy": d["id"], "strategy_name": d["name"],
                "scenario": d["scenario"], "mode": d["mode"],
                "symbol": symbol,
                "detected_at": detected_at,
                "created_at": datetime.now(UTC),  # BSON date -> TTL anchor
                "qualified": qualified,
                "qualification_result": "QUALIFIED" if qualified else "DETECTED_ONLY",
                "breaker_state": breaker_state,
                "entry_price": snapshot.price,
                "resolved": resolved,
                "resolved_at": detected_at if resolved else None,
                "return_pct": None,
                "max_drawdown_pct": None,
                "outcome": outcome,
            })
        if lab_docs:
            await db.strategy_lab_log.insert_many(lab_docs)

    # --- SHADOW Simulator (Phase 2.1): open a virtual trade for bullish
    # near-misses (0.70-0.79) so the exit engine is exercised without capital. ---
    with contextlib.suppress(Exception):
        await maybe_open_shadow(
            db,
            symbol=symbol,
            macro=macro,
            snapshot=snapshot,
            settings=settings,
            is_breakout=is_breakout,
            sector=sector_for_symbol(symbol),
        )

    # execute trade if BUY/SELL
    trade_doc: dict | None = None
    live_route = (
        settings.trading_mode == "LIVE"
        and LiveExecutor.is_live_gate_open()
    )
    dry_run_route = settings.trading_mode == "DRY_RUN"
    executor: LiveExecutor | None = None
    trade_mode: str = "PAPER"
    if live_route:
        executor, exec_err = get_default_executor()
        if executor is None:
            logger.warning("LIVE requested but executor unavailable: %s. Skipping trade.", exec_err)
            live_route = False
        else:
            trade_mode = "LIVE"
    elif dry_run_route:
        executor, exec_err = get_dry_run_executor()
        if executor is None:
            logger.warning("DRY_RUN requested but executor unavailable: %s. Falling back to PAPER.", exec_err)
            dry_run_route = False
        else:
            trade_mode = "DRY_RUN"
    routed = live_route or dry_run_route

    # --- entry-time analytics tagging (volatility regime + sector) ---
    entry_atr, entry_atr_pct, entry_regime = compute_entry_volatility(bars_1h)
    entry_sector = sector_for_symbol(symbol)

    if decision == "BUY":
        usd_lot: float | None = None
        if is_breakout:
            usd_lot = settings.breakout_lot_usd
        elif symbol == "PAXG/USD":
            # PAXG anchor: dedicated $30 lot for the uncorrelated hedge (reuses strong_lot_usd).
            usd_lot = settings.strong_lot_usd
        elif settings.adaptive_sizing_enabled and setup_strength != "NONE":
            usd_lot = settings.strong_lot_usd if setup_strength == "STRONG" else settings.normal_lot_usd
        if usd_lot is None and at_support:
            # Level-touch entry without a classified strong/breakout setup -> normal lot.
            usd_lot = hunter_settings.normal_lot_usd
        qty_desired = position_size_quantity(
            decision, snapshot, portfolio, settings, macro.confidence, usd_lot=usd_lot,
        )
        if qty_desired > 0:
            order_style = "MARKET" if is_breakout else "POST_ONLY"
            entry_spread_cap = settings.breakout_max_spread_pct if is_breakout else settings.max_spread_pct
            if routed and executor is not None:
                desired_notional = qty_desired * snapshot.ask
                max_cash = portfolio.cash * 0.95
                result = await executor.place_buy(
                    symbol=symbol,
                    desired_notional=desired_notional,
                    max_cash=max_cash,
                    ask=snapshot.ask,
                    max_spread_pct=entry_spread_cap,
                    order_style=order_style,
                )
                trade_doc = await _record_live_buy(
                    db, portfolio, symbol, result, reasoning, macro.confidence,
                    fusion_summary, mode=trade_mode,
                    sector=entry_sector, atr_at_entry=entry_atr,
                    atr_percentile_at_entry=entry_atr_pct, volatility_regime=entry_regime,
                    entry_extension_pct=entry_extension_pct,
                )
                # tag the position so the watcher uses wider trail params
                new_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
                if new_pos is not None:
                    if structural_stop is not None and new_pos.structural_stop is None:
                        new_pos.structural_stop = structural_stop
                    if is_breakout:
                        new_pos.breakout_mode = True
                    if not new_pos.entry_attribution:
                        new_pos.entry_attribution = entry_attribution
                    await save_portfolio(db, portfolio)
            elif is_breakout:
                # PAPER breakout: true taker MARKET fill with synthetic slippage.
                slip_pct = settings.breakout_paper_slippage_pct / 100.0
                fill_price = snapshot.ask * (1.0 + slip_pct)
                slippage_usd = (fill_price - snapshot.ask) * qty_desired
                notional, fee = _execute_buy(portfolio, symbol, qty_desired, fill_price, settings.taker_fee_pct)
                if notional > 0:
                    new_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
                    if new_pos is not None:
                        new_pos.breakout_mode = True
                        if new_pos.structural_stop is None and structural_stop is not None:
                            new_pos.structural_stop = structural_stop
                        if new_pos.sector is None:
                            new_pos.sector = entry_sector
                            new_pos.atr_at_entry = entry_atr
                            new_pos.atr_percentile_at_entry = entry_atr_pct
                            new_pos.volatility_regime = entry_regime
                            new_pos.entry_extension_pct = entry_extension_pct
                        if not new_pos.entry_attribution:
                            new_pos.entry_attribution = entry_attribution
                    trade = TradeLog(
                        symbol=symbol, side="BUY", quantity=qty_desired, price=fill_price,
                        notional=notional, mode="PAPER", confidence=macro.confidence,
                        reasoning_id=reasoning.id, fee_usd=fee, slippage_usd=slippage_usd,
                        note=f"[BREAKOUT MARKET taker, +{settings.breakout_paper_slippage_pct}% slip] {fusion_summary}",
                        sector=entry_sector, atr_at_entry=entry_atr,
                        atr_percentile_at_entry=entry_atr_pct, volatility_regime=entry_regime,
                        entry_extension_pct=entry_extension_pct,
                    )
                    await db.trades.insert_one(trade.model_dump())
                    trade_doc = trade.model_dump()
                    await save_portfolio(db, portfolio)
                    await log_friction_tally(db, settings)
            else:
                # PAPER Normal/Strong: Post-Only MAKER limit resting at best bid.
                # Filled later by the position watcher only if price crosses our bid
                # or stays flat for 2 ticks; else cancelled as MISSED_FILL_PRICE_RUN.
                existing_pending = await db.pending_orders.find_one({"symbol": symbol})
                if existing_pending is None:
                    pending = PendingOrder(
                        symbol=symbol, quantity=qty_desired, limit_price=snapshot.bid,
                        mode="PAPER", reasoning_id=reasoning.id, breakout=False,
                        sector=entry_sector, atr_at_entry=entry_atr,
                        atr_percentile_at_entry=entry_atr_pct, volatility_regime=entry_regime,
                        entry_extension_pct=entry_extension_pct, structural_stop=structural_stop,
                        entry_attribution=entry_attribution,
                    )
                    await db.pending_orders.insert_one(pending.model_dump())
                    logger.info(
                        "PAPER POST-ONLY maker BUY resting %s qty=%.8f @ bid %.6f (reasoning=%s)",
                        symbol, qty_desired, snapshot.bid, reasoning.id,
                    )
                    trade_doc = {
                        "symbol": symbol, "side": "BUY", "status": "PENDING_MAKER",
                        "quantity": qty_desired, "price": snapshot.bid,
                        "note": "Post-Only maker order resting at best bid",
                    }
                else:
                    logger.info("PAPER maker BUY skipped %s — order already resting", symbol)
    elif decision == "SELL":
        existing = next((p for p in portfolio.positions if p.symbol == symbol), None)
        if existing is not None and existing.quantity > 0:
            # capture entry-regime tags BEFORE the position is closed
            ex_sector = existing.sector
            ex_atr = existing.atr_at_entry
            ex_atr_pct = existing.atr_percentile_at_entry
            ex_regime = existing.volatility_regime
            ex_ext = existing.entry_extension_pct
            ex_entry_price = existing.avg_cost
            ex_entry_ts = existing.entry_timestamp
            if routed and executor is not None:
                result = await executor.place_sell(
                    symbol=symbol,
                    qty=existing.quantity,
                    bid=snapshot.bid,
                    max_spread_pct=settings.max_spread_pct,
                )
                trade_doc = await _record_live_sell(
                    db, portfolio, symbol, result, reasoning, macro.confidence,
                    fusion_summary, mode=trade_mode, exit_reason="MACRO_BEARISH",
                    expected_trigger_price=snapshot.price,
                )
            else:
                qty, notional, realized, fee = _execute_sell(portfolio, symbol, snapshot.bid, settings.taker_fee_pct)
                if qty > 0:
                    # slippage: expected trigger = last price; actual fill = bid
                    slippage_usd = (snapshot.price - snapshot.bid) * qty
                    trade = TradeLog(
                        symbol=symbol,
                        side="SELL",
                        quantity=qty,
                        price=snapshot.bid,
                        notional=notional,
                        mode="PAPER",
                        confidence=macro.confidence,
                        reasoning_id=reasoning.id,
                        pnl=realized,
                        fee_usd=fee,
                        slippage_usd=slippage_usd,
                        note=fusion_summary,
                        exit_reason="MACRO_BEARISH",
                        sector=ex_sector,
                        atr_at_entry=ex_atr,
                        atr_percentile_at_entry=ex_atr_pct,
                        volatility_regime=ex_regime,
                        entry_extension_pct=ex_ext,
                        entry_price=ex_entry_price,
                        entry_timestamp=ex_entry_ts,
                        return_pct=compute_return_and_hold(ex_entry_price, ex_entry_ts, snapshot.bid)[0],
                        hold_seconds=compute_return_and_hold(ex_entry_price, ex_entry_ts, snapshot.bid)[1],
                    )
                    await db.trades.insert_one(trade.model_dump())
                    trade_doc = trade.model_dump()
                    await save_portfolio(db, portfolio)
                    await log_friction_tally(db, settings)

    # --- INDEPENDENT TRADER: Volatility Squeeze (Phase E) ---
    # Runs SEPARATELY from the Hunter (different personality: "buy expansion").
    # Fires only when the Hunter did NOT take this symbol, the book has room, and a
    # CONFIRMED retest/continuation breakout exists (never chases the first candle).
    # PAPER/DRY_RUN only. Hard stop = 20-MA; ATR-flexed trail handled by the watcher.
    with contextlib.suppress(Exception):
        squeeze_eligible = (
            decision != "BUY"
            and not has_position
            and trade_doc is None
            and not _hard_killed
            and breaker_state != "VETO"
            and settings.trading_mode in ("PAPER", "DRY_RUN")
            and strategy_entry_allowed(strategy_states, "squeeze")
            and squeeze_allowed(getattr(asset_regime, "regime", None))
        )
        if squeeze_eligible:
            sq = evaluate_squeeze(bars_1h, vol_expansion_min=squeeze_settings.squeeze_vol_expansion_min)
            if sq.triggered and sq.stop_20ma and snapshot.price > sq.stop_20ma:
                open_count = sum(1 for p in portfolio.positions if p.quantity > 0)
                pending_count = await db.pending_orders.count_documents({})
                cooldown = await get_symbol_cooldown(db, symbol)
                spread_ok = bid_spread_pct <= settings.max_spread_pct
                if open_count + pending_count < settings.max_concurrent_positions and not cooldown and spread_ok:
                    from entry_quality import score_squeeze
                    sqev = sq.evidence or {}
                    _re = getattr(asset_regime, "evidence", {}) or {}
                    eq = score_squeeze(
                        bbwidth_percentile=_re.get("bbwidth_percentile"),
                        atr_percentile=_re.get("atr_percentile"),
                        volume_spike_ratio=sqev.get("volume_spike_ratio"),
                        breakout_strength_pct=sqev.get("breakout_strength_pct"),
                        entry_profile=sq.entry_profile or "",
                    )
                    qty_sq = position_size_quantity("BUY", snapshot, portfolio, settings, 0.0, usd_lot=squeeze_settings.normal_lot_usd)
                    if qty_sq > 0:
                        slip_pct = settings.breakout_paper_slippage_pct / 100.0
                        fill_price = snapshot.ask * (1.0 + slip_pct)
                        sq_slip = (fill_price - snapshot.ask) * qty_sq
                        notional, fee = _execute_buy(portfolio, symbol, qty_sq, fill_price, settings.taker_fee_pct)
                        if notional > 0:
                            sq_attr = {
                                **entry_attribution,
                                "strategy": "squeeze",
                                "entry_profile": sq.entry_profile,
                                "entry_quality": eq,
                                "squeeze_evidence": sqev,
                                "asset_regime": getattr(asset_regime, "regime", None),
                            }
                            new_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
                            if new_pos is not None:
                                new_pos.strategy = "squeeze"
                                new_pos.entry_profile = sq.entry_profile
                                new_pos.entry_quality_grade = eq.get("grade")
                                new_pos.entry_quality_score = eq.get("pct")
                                new_pos.regime_at_entry = getattr(asset_regime, "regime", None)
                                new_pos.structural_stop = sq.stop_20ma  # hard stop at 20-MA
                                new_pos.breakout_mode = True  # wider, ATR-flexed trail for expansion rides
                                new_pos.sector = entry_sector
                                new_pos.atr_at_entry = entry_atr
                                new_pos.atr_percentile_at_entry = entry_atr_pct
                                new_pos.volatility_regime = entry_regime
                                new_pos.entry_attribution = sq_attr
                            sq_trade = TradeLog(
                                symbol=symbol, side="BUY", quantity=qty_sq, price=fill_price,
                                notional=notional, mode="PAPER", confidence=0.0,
                                reasoning_id=reasoning.id, fee_usd=fee, slippage_usd=sq_slip,
                                note=f"[SQUEEZE {sq.entry_profile} | grade {eq.get('grade')} | stop20MA {sq.stop_20ma}]",
                                sector=entry_sector, atr_at_entry=entry_atr,
                                atr_percentile_at_entry=entry_atr_pct, volatility_regime=entry_regime,
                                entry_attribution=sq_attr,
                            )
                            await db.trades.insert_one(sq_trade.model_dump())
                            trade_doc = sq_trade.model_dump()
                            await save_portfolio(db, portfolio)
                            await log_friction_tally(db, settings)
                            logger.info(
                                "SQUEEZE entry %s qty=%.8f @ %.6f stop20MA=%.6f profile=%s grade=%s",
                                symbol, qty_sq, fill_price, sq.stop_20ma, sq.entry_profile, eq.get("grade"),
                            )
                            try:
                                from push_service import send_push_event
                                await send_push_event(
                                    db, "trade_opened",
                                    f"Squeeze opened {symbol} ({sq.entry_profile}, grade {eq.get('grade')})",
                                )
                            except Exception:
                                pass

    # --- WS2 Hunter Continuation (independent trend-pullback executor) ---
    # Fires only when neither Hunter nor Squeeze took the symbol, the book has room,
    # the regime is a trend, and a controlled pullback-to-20-EMA setup is confirmed.
    with contextlib.suppress(Exception):
        cont_eligible = (
            decision != "BUY"
            and not has_position
            and trade_doc is None
            and not _hard_killed
            and breaker_state != "VETO"
            and settings.trading_mode in ("PAPER", "DRY_RUN")
            and getattr(settings, "continuation_enabled", True)
            and strategy_entry_allowed(strategy_states, "continuation")
            and continuation_allowed(getattr(asset_regime, "regime", None))
        )
        if cont_eligible:
            ct = evaluate_continuation(bars_1h, cont_settings, regime=asset_regime)
            if ct.triggered and ct.structural_stop and snapshot.price > ct.structural_stop:
                open_count = sum(1 for p in portfolio.positions if p.quantity > 0)
                pending_count = await db.pending_orders.count_documents({})
                cooldown = await get_symbol_cooldown(db, symbol)
                spread_ok = bid_spread_pct <= settings.max_spread_pct
                if open_count + pending_count < settings.max_concurrent_positions and not cooldown and spread_ok:
                    qty_ct = position_size_quantity("BUY", snapshot, portfolio, settings, 0.0, usd_lot=cont_settings.normal_lot_usd)
                    if qty_ct > 0:
                        slip_pct = settings.breakout_paper_slippage_pct / 100.0
                        fill_price = snapshot.ask * (1.0 + slip_pct)
                        ct_slip = (fill_price - snapshot.ask) * qty_ct
                        notional, fee = _execute_buy(portfolio, symbol, qty_ct, fill_price, settings.taker_fee_pct)
                        if notional > 0:
                            ct_attr = {
                                **entry_attribution,
                                "strategy": "continuation",
                                "entry_profile": ct.entry_profile,
                                "continuation_evidence": ct.evidence,
                                "asset_regime": getattr(asset_regime, "regime", None),
                            }
                            new_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
                            if new_pos is not None:
                                new_pos.strategy = "continuation"
                                new_pos.entry_profile = ct.entry_profile
                                new_pos.regime_at_entry = getattr(asset_regime, "regime", None)
                                new_pos.structural_stop = ct.structural_stop
                                new_pos.sector = entry_sector
                                new_pos.atr_at_entry = entry_atr
                                new_pos.atr_percentile_at_entry = entry_atr_pct
                                new_pos.volatility_regime = entry_regime
                                new_pos.entry_attribution = ct_attr
                            ct_trade = TradeLog(
                                symbol=symbol, side="BUY", quantity=qty_ct, price=fill_price,
                                notional=notional, mode="PAPER", confidence=0.0,
                                reasoning_id=reasoning.id, fee_usd=fee, slippage_usd=ct_slip,
                                note=f"[CONTINUATION {ct.entry_profile} | pullback {ct.evidence.get('pullback_pct')}% | stop {ct.structural_stop}]",
                                sector=entry_sector, atr_at_entry=entry_atr,
                                atr_percentile_at_entry=entry_atr_pct, volatility_regime=entry_regime,
                                entry_attribution=ct_attr,
                            )
                            await db.trades.insert_one(ct_trade.model_dump())
                            trade_doc = ct_trade.model_dump()
                            await save_portfolio(db, portfolio)
                            await log_friction_tally(db, settings)
                            logger.info(
                                "CONTINUATION entry %s qty=%.8f @ %.6f stop=%.6f pullback=%s%%",
                                symbol, qty_ct, fill_price, ct.structural_stop, ct.evidence.get("pullback_pct"),
                            )

    return {
        "symbol": symbol,
        "snapshot": snapshot.model_dump(),
        "macro": macro.model_dump(),
        "kill_switches": kill.model_dump(),
        "decision": decision,
        "blocked_reasons": blocked,
        "fusion_summary": fusion_summary,
        "trade": trade_doc,
        "reasoning_id": reasoning.id,
    }


async def evaluate_all(db: AsyncIOMotorDatabase) -> list[dict]:
    settings = await load_settings(db)
    global _SCAN_CYCLE
    _SCAN_CYCLE += 1
    results: list[dict] = []
    for sym in settings.enabled_symbols:
        # Staggered scanning (credit control): majors every cycle; DeFi + gold every Nth cycle.
        interval = scan_interval(sym)
        if interval > 1 and (_SCAN_CYCLE % interval) != 0:
            continue
        try:
            r = await evaluate_symbol(db, sym)
            results.append(r)
        except Exception as e:
            logger.exception("evaluate_symbol failed for %s: %s", sym, e)
            results.append({"symbol": sym, "error": str(e)})
    return results


# ---------- background loop ----------
class TradingLoop:
    def __init__(self, db: AsyncIOMotorDatabase, interval_seconds: int = 60):
        self.db = db
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self):
        logger.info("TradingLoop started, interval=%ss", self.interval)
        while not self._stop.is_set():
            try:
                await evaluate_all(self.db)
            except Exception as e:
                logger.exception("Trading loop iteration error: %s", e)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
        logger.info("TradingLoop stopped")

    def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        if self._task:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, timeout=5)
