"""
Position Watcher — lightweight loop that monitors OPEN positions every ~15s
and exits them on any of:

  * SL_HIT      hard stop-loss (drawdown >= settings.stop_loss_pct). Always
                active.
  * TRAIL_HIT   trailing take-profit (peak ran +trail_arm_pct, then pulled
                back trail_distance_pct from peak)

SWING PIVOT: the legacy MICRO_FLIP orderbook-imbalance exit has been removed
entirely. Open swings now exit only on SL or trailing take-profit, so
short-term orderbook noise can no longer shake the bot out of a trend.

Does NOT call Gemini — too slow, and we already have a macro read from the
main 90s cycle. The watcher exists to catch fast moves that the slow loop
would miss.

Persists peak_price on each tick so a restart doesn't reset the trailing stop.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from live_execution import LiveExecutor, get_default_executor, get_dry_run_executor
from market_data import fetch_snapshot
from models import AIReasoning, MarketSnapshot, Position, RiskSettings, TradeLog, compute_return_and_hold
from asset_profiles import eff_setting
from trading_engine import (
    _ensure_day_start,
    _execute_sell,
    _record_live_sell,
    load_portfolio,
    load_settings,
    log_friction_tally,
    process_pending_orders,
    save_portfolio,
    set_symbol_cooldown,
)

logger = logging.getLogger(__name__)

EXIT_SL = "SL_HIT"
EXIT_TRAIL = "TRAIL_HIT"


def trail_distance_for(pos: Position, settings: RiskSettings) -> float:
    """Effective trailing pullback distance (%) for a position.

    Volatility-adaptive model: ``dynamic_trail = clamp(k * ATR_percentile,
    min_trail, max_trail)``. Higher entry-time volatility (a richer ATR
    percentile) earns a wider leash so violent retracements don't shake the
    bot out; calm tape gets a tighter trail to lock gains.

    Falls back to the static ``trail_distance_pct`` (or breakout override) when
    the adaptive model is disabled or the position carries no ATR percentile.
    """
    static_dist = settings.breakout_trail_distance_pct if pos.breakout_mode else eff_setting(
        settings, pos.symbol, "trail_distance_pct",
    )
    atr_pct = pos.atr_percentile_at_entry
    if not settings.dynamic_trail_enabled or atr_pct is None:
        return static_dist
    raw = settings.dynamic_trail_k * float(atr_pct)
    lo = eff_setting(settings, pos.symbol, "dynamic_trail_min_pct")
    hi = eff_setting(settings, pos.symbol, "dynamic_trail_max_pct")
    return max(lo, min(hi, raw))


def _seconds_since(iso_ts: str) -> float:
    """Best-effort age in seconds. Returns +inf if parsing fails so the
    cooldown defaults to OFF for legacy positions without a timestamp."""
    if not iso_ts:
        return float("inf")
    try:
        # iso_ts is utc isoformat() output - may or may not carry tz
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return float("inf")


def evaluate_exit(
    pos: Position,
    snap: MarketSnapshot,
    settings: RiskSettings,
) -> tuple[str | None, dict]:
    """Pure decision function. Returns (exit_reason | None, details).

    SWING PIVOT: exits only on hard stop-loss or trailing take-profit.
    """
    entry = pos.avg_cost
    last = snap.price
    if entry <= 0 or last <= 0:
        return None, {"reason": "no entry/last price"}
    pnl_pct = (last - entry) / entry * 100.0
    peak = max(pos.peak_price or entry, last)
    age_s = _seconds_since(pos.entry_timestamp)

    # breakout positions get a wider arm (more room to run); the trailing
    # distance flexes with entry-time volatility via the adaptive envelope.
    # Per-asset-class overrides (e.g. PAXG/gold) tighten SL + arm for low-vol assets.
    sl_pct = eff_setting(settings, pos.symbol, "stop_loss_pct")
    arm_pct = settings.breakout_trail_arm_pct if pos.breakout_mode else eff_setting(
        settings, pos.symbol, "trail_arm_pct",
    )
    dist_pct = trail_distance_for(pos, settings)

    details = {
        "entry": round(entry, 6),
        "last": round(last, 6),
        "peak": round(peak, 6),
        "pnl_pct": round(pnl_pct, 3),
        "age_s": round(age_s, 1) if age_s != float("inf") else None,
        "breakout_mode": pos.breakout_mode,
        "trail_arm_pct": arm_pct,
        "trail_distance_pct": dist_pct,
        "stop_loss_pct": sl_pct,
        "structural_stop": pos.structural_stop,
    }

    # 0) STRUCTURAL stop (Phase 1.5) — hard stop just below the entry support
    # zone. The market trading through it confirms the level is broken. Takes
    # precedence over the % stop when a structural level was set at entry.
    if pos.structural_stop and last <= pos.structural_stop:
        return EXIT_SL, details

    # 1) Hard stop-loss — exits a losing trade fast. Always active.
    if pnl_pct <= -sl_pct:
        return EXIT_SL, details

    # 2) Trailing take-profit — only armed after the trade ran +arm_pct.
    run_up_pct = (peak - entry) / entry * 100.0
    if run_up_pct >= arm_pct:
        pullback_pct = (peak - last) / peak * 100.0 if peak > 0 else 0.0
        details["run_up_pct"] = round(run_up_pct, 3)
        details["pullback_pct"] = round(pullback_pct, 3)
        if pullback_pct >= dist_pct:
            return EXIT_TRAIL, details

    return None, details


async def _route_executor(settings: RiskSettings) -> tuple[LiveExecutor | None, str]:
    """Pick LIVE / DRY_RUN / PAPER executor based on settings, same rules as
    the main engine."""
    if settings.trading_mode == "LIVE" and LiveExecutor.is_live_gate_open():
        executor, _err = get_default_executor()
        if executor is not None:
            return executor, "LIVE"
    if settings.trading_mode == "DRY_RUN":
        executor, _err = get_dry_run_executor()
        if executor is not None:
            return executor, "DRY_RUN"
    return None, "PAPER"


async def watch_once(db: AsyncIOMotorDatabase) -> list[dict]:
    """One sweep of all open positions. Returns trade docs for any exits."""
    settings = await load_settings(db)
    portfolio = _ensure_day_start(await load_portfolio(db))
    if not portfolio.positions:
        return []

    executor, trade_mode = await _route_executor(settings)
    exits: list[dict] = []
    dirty = False

    for pos in list(portfolio.positions):
        if pos.quantity <= 0:
            continue
        snap = await fetch_snapshot(pos.symbol)
        if snap is None:
            continue

        # peak update (lazy init from entry on first tick)
        new_peak = max(pos.peak_price or pos.avg_cost, snap.price)
        if new_peak != pos.peak_price:
            pos.peak_price = new_peak
            dirty = True
        # trough update -> powers Max Adverse Excursion (Phase B research)
        new_trough = min(pos.trough_price or pos.avg_cost, snap.price)
        if new_trough != pos.trough_price:
            pos.trough_price = new_trough
            dirty = True
        if pos.avg_cost > 0:
            pos.mfe_pct = round((pos.peak_price - pos.avg_cost) / pos.avg_cost * 100, 4)
            pos.mae_pct = round((pos.trough_price - pos.avg_cost) / pos.avg_cost * 100, 4)

        reason, details = evaluate_exit(pos, snap, settings)
        if reason is None:
            continue

        logger.info("PositionWatcher EXIT %s reason=%s %s", pos.symbol, reason, details)

        # expected trigger price for realized-slippage accounting
        if reason == EXIT_SL:
            if pos.structural_stop and snap.price <= pos.structural_stop:
                expected_trigger = pos.structural_stop
            else:
                sl_pct = eff_setting(settings, pos.symbol, "stop_loss_pct")
                expected_trigger = pos.avg_cost * (1.0 - sl_pct / 100.0)
        elif reason == EXIT_TRAIL:
            dist = trail_distance_for(pos, settings)
            peak = max(pos.peak_price or pos.avg_cost, snap.price)
            expected_trigger = peak * (1.0 - dist / 100.0)
        else:
            expected_trigger = snap.price

        # Symmetric cooldown: lock the symbol so the bot doesn't immediately
        # re-buy a bleeding asset, and lets momentum reset after a winner.
        if reason == EXIT_SL:
            await set_symbol_cooldown(db, pos.symbol, settings.sl_cooldown_seconds, EXIT_SL)
        elif reason == EXIT_TRAIL:
            await set_symbol_cooldown(db, pos.symbol, settings.trail_cooldown_seconds, EXIT_TRAIL)

        # Persist a small reasoning row for traceability (no Gemini call).
        reasoning = AIReasoning(
            symbol=pos.symbol,
            bias="NEUTRAL",
            confidence=0.0,
            reason=f"Position watcher exit: {reason}",
            news_summary="(position-watcher; no Gemini call)",
            evidence={"exit_reason": reason, "exit_details": details, "source": "position_watcher"},
            decision="SELL",
        )
        await db.reasoning.insert_one(reasoning.model_dump())

        # Exit via the same path the main engine uses.
        if executor is not None:
            result = await executor.place_sell(
                symbol=pos.symbol,
                qty=pos.quantity,
                bid=snap.bid,
                max_spread_pct=settings.max_spread_pct,
            )
            trade_doc = await _record_live_sell(
                db, portfolio, pos.symbol, result, reasoning,
                macro_confidence=0.0,
                fusion_summary=f"WATCHER EXIT {reason} | {details}",
                mode=trade_mode,
                exit_reason=reason,
                expected_trigger_price=expected_trigger,
            )
            if trade_doc:
                exits.append(trade_doc)
                try:
                    from push_service import send_push_event
                    _evt = "stop_loss" if reason == EXIT_SL else "trailing_stop" if reason == EXIT_TRAIL else "trade_closed"
                    _pnl = trade_doc.get("pnl")
                    _m = f"{pos.symbol} exited ({reason})" + (f" · P&L ${_pnl:.2f}" if isinstance(_pnl, (int, float)) else "")
                    await send_push_event(db, _evt, _m)
                except Exception:
                    pass
            dirty = True  # _record_live_sell already saves portfolio, but be safe
        else:
            qty, notional, realized, fee = _execute_sell(portfolio, pos.symbol, snap.bid, settings.taker_fee_pct)
            if qty > 0:
                slippage_usd = (expected_trigger - snap.bid) * qty
                _ret_pct, _hold = compute_return_and_hold(pos.avg_cost, pos.entry_timestamp, snap.bid)
                trade = TradeLog(
                    symbol=pos.symbol,
                    side="SELL",
                    quantity=qty,
                    price=snap.bid,
                    notional=notional,
                    mode="PAPER",
                    confidence=0.0,
                    reasoning_id=reasoning.id,
                    pnl=realized,
                    fee_usd=fee,
                    slippage_usd=slippage_usd,
                    note=f"WATCHER EXIT {reason} | {details}",
                    exit_reason=reason,
                    sector=pos.sector,
                    atr_at_entry=pos.atr_at_entry,
                    atr_percentile_at_entry=pos.atr_percentile_at_entry,
                    volatility_regime=pos.volatility_regime,
                    entry_extension_pct=pos.entry_extension_pct,
                    trade_result=("WIN" if realized > 0 else "LOSS" if realized < 0 else "BREAKEVEN"),
                    mfe_pct=pos.mfe_pct,
                    mae_pct=pos.mae_pct,
                    entry_price=pos.avg_cost,
                    entry_timestamp=pos.entry_timestamp,
                    return_pct=_ret_pct,
                    hold_seconds=_hold,
                    entry_attribution=pos.entry_attribution or {},
                )
                await db.trades.insert_one(trade.model_dump())
                exits.append(trade.model_dump())
                dirty = True
                try:
                    from push_service import send_push_event
                    _evt = "stop_loss" if reason == EXIT_SL else "trailing_stop" if reason == EXIT_TRAIL else "trade_closed"
                    await send_push_event(
                        db, _evt,
                        f"{pos.symbol} exited ({reason}) · P&L ${realized:.2f} ({_ret_pct:+.2f}%)",
                    )
                except Exception:
                    pass

                # Phase B: structure-based staged-exit shadow sim (Actual vs 33/33/34).
                with contextlib.suppress(Exception):
                    from strategies import simulate_staged_exit
                    sim = simulate_staged_exit(
                        avg_cost=pos.avg_cost, qty=qty, trough_price=pos.trough_price,
                        structural_stop=pos.structural_stop,
                        support_low=(pos.entry_attribution or {}).get("support_low"),
                        actual_exit_price=snap.bid,
                    )
                    if sim:
                        sim.update({"symbol": pos.symbol, "timestamp": trade.timestamp,
                                    "exit_reason": reason, "trade_id": trade.id})
                        await db.stop_loss_simulation_logs.insert_one(sim)

    if dirty:
        await save_portfolio(db, portfolio)
        await log_friction_tally(db, settings)
    return exits


class PositionWatcher:
    def __init__(self, db: AsyncIOMotorDatabase, default_interval: int = 15):
        self.db = db
        self.default_interval = default_interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self):
        logger.info("PositionWatcher started")
        while not self._stop.is_set():
            try:
                await process_pending_orders(self.db)  # resolve resting maker orders first
                await watch_once(self.db)
                settings = await load_settings(self.db)
                interval = max(5, int(settings.position_watcher_interval_seconds or self.default_interval))
            except Exception as e:
                logger.exception("position watcher iter error: %s", e)
                interval = self.default_interval
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
        logger.info("PositionWatcher stopped")

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
