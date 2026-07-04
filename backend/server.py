"""
CryptoAtlas AI Trading Dashboard - FastAPI backend.

Endpoints (all prefixed with /api):
- /api/                       health
- /api/market/snapshots       live market data for all enabled symbols
- /api/market/snapshot/{sym}  single symbol snapshot
- /api/portfolio              current portfolio + day-P&L
- /api/portfolio/reset        reset to $100 (clears trades + reasoning)
- /api/trades                 trade history (paginated)
- /api/reasoning              AI reasoning log timeline
- /api/risk/status            current kill-switch status
- /api/settings               GET / PUT risk + operational settings
- /api/cycle/run              run one evaluation cycle now (returns full results)
"""
from __future__ import annotations

import logging
import asyncio
import contextlib
import os
import uuid
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

# ---- env / db ----
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# ---- logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---- imports that depend on env loaded ----
from analytics import compute_performance, graduation_readiness, regime_insight, sector_exposure
from auth import authenticate, is_owner_request, require_owner, seed_owner
from backtest import run_for_symbols_async, run_sweep_for_symbols_async
from live_execution import live_status as live_execution_status
from market_data import fetch_snapshot, fetch_snapshots, fetch_snapshots_cached, warm_snapshots
from models import MarketSnapshot
from news_source import get_cache_info, get_current_summary
from position_watcher import PositionWatcher
from research import ResearchResolverLoop, resolve_counterfactuals, summarize_breaker_accuracy, summarize_funnel, summarize_missed_opportunities, summarize_research, summarize_rejections, summarize_rsi_distribution, summarize_strategy_lab, summarize_winner_profile, summarize_zone_effectiveness
from shadow_sim import ShadowWatcherLoop, summarize_shadow, watch_shadow_once
from risk_engine import compute_kill_switches
from levels import get_levels, nearest_resistance, nearest_support
from trading_engine import (
    TradingLoop,
    evaluate_all,
    evaluate_symbol,
    load_portfolio,
    load_settings,
    reset_portfolio,
    save_settings,
)

# ---- app ----
app = FastAPI(title="Ananta AI Trading Dashboard")
api_router = APIRouter(prefix="/api")


# Kubernetes liveness/readiness probe — must be top-level (no /api prefix),
# must respond instantly and never touch the DB or any external service.
@app.get("/health")
async def health():
    return {"status": "ok"}

# background trading loop + faster position watcher
trading_loop = TradingLoop(db, interval_seconds=90)
position_watcher = PositionWatcher(db, default_interval=15)
research_resolver = ResearchResolverLoop(db, interval_seconds=600)
shadow_watcher = ShadowWatcherLoop(db, interval_seconds=30)

# Research Lab: async job queue worker (offline backtests / sweeps / walk-forward)
from lab.runner import LabDataAppender, LabWorker, create_run  # noqa: E402

lab_worker = LabWorker(db)
lab_appender = LabDataAppender(db)


# ---------- request/response models ----------
class SettingsUpdate(BaseModel):
    max_spread_pct: float | None = None
    max_daily_loss_pct: float | None = None
    min_confidence: float | None = None
    position_size_pct_min: float | None = None
    position_size_pct_max: float | None = None
    adaptive_sizing_enabled: bool | None = None
    normal_lot_usd: float | None = None
    strong_lot_usd: float | None = None
    strong_min_confidence: float | None = None
    strong_min_atr_percentile: float | None = None
    strong_min_adx: float | None = None
    max_concurrent_positions: int | None = None
    stop_loss_pct: float | None = None
    trail_arm_pct: float | None = None
    trail_distance_pct: float | None = None
    position_watcher_interval_seconds: int | None = None
    vault_sync_enabled: bool | None = None
    vault_max_override_usd: float | None = None
    htf_trend_enabled: bool | None = None
    taker_fee_pct: float | None = None
    maker_fee_pct: float | None = None
    breakout_paper_slippage_pct: float | None = None
    breakout_lot_usd: float | None = None
    breakout_min_confidence: float | None = None
    breakout_volume_percentile: float | None = None
    breakout_max_spread_pct: float | None = None
    breakout_trail_arm_pct: float | None = None
    breakout_trail_distance_pct: float | None = None
    sl_cooldown_seconds: int | None = None
    trail_cooldown_seconds: int | None = None
    trading_mode: str | None = None  # PAPER / DRY_RUN / LIVE
    manual_kill_switch: bool | None = None
    enabled_symbols: list[str] | None = None
    coinbase_api_key: str | None = None
    coinbase_api_secret: str | None = None
    kraken_api_key: str | None = None
    kraken_api_secret: str | None = None


# ---------- routes ----------
@api_router.get("/")
async def root():
    return {
        "name": "Ananta AI Trading Dashboard",
        "status": "running",
        "ts": datetime.now(UTC).isoformat(),
    }


@api_router.get("/market/snapshots")
async def market_snapshots():
    settings = await load_settings(db)
    snaps = await fetch_snapshots_cached(settings.enabled_symbols)
    return {"symbols": settings.enabled_symbols, "snapshots": [s.model_dump() for s in snaps]}


@api_router.get("/market/snapshot/{symbol_base}")
async def market_snapshot(symbol_base: str):
    # accept "BTC" or "BTC/USD"
    symbol = symbol_base if "/" in symbol_base else f"{symbol_base.upper()}/USD"
    snap = await fetch_snapshot(symbol)
    if snap is None:
        raise HTTPException(status_code=502, detail=f"No market data available for {symbol}")
    return snap.model_dump()


@api_router.get("/portfolio")
async def get_portfolio():
    portfolio = await load_portfolio(db)
    settings = await load_settings(db)
    # compute live equity using latest prices
    snaps = await fetch_snapshots_cached([p.symbol for p in portfolio.positions]) if portfolio.positions else []
    price_map = {s.symbol: s.price for s in snaps}
    live_positions: list[dict] = []
    positions_value = 0.0
    for p in portfolio.positions:
        last = price_map.get(p.symbol, p.avg_cost)
        market_value = p.quantity * last
        positions_value += market_value
        live_positions.append({
            "symbol": p.symbol,
            "quantity": p.quantity,
            "avg_cost": p.avg_cost,
            "last_price": last,
            "market_value": market_value,
            "unrealized_pnl": (last - p.avg_cost) * p.quantity,
            "structural_stop": p.structural_stop,
            "peak_price": p.peak_price,
            "breakout_mode": p.breakout_mode,
            "sector": getattr(p, "sector", None),
            "entry_timestamp": getattr(p, "entry_timestamp", None),
        })
    equity = portfolio.cash + positions_value
    day_start = portfolio.day_start_equity or portfolio.starting_balance
    daily_pnl_pct = ((equity - day_start) / day_start * 100.0) if day_start > 0 else 0.0
    total_pnl = equity - portfolio.starting_balance
    total_pnl_pct = (total_pnl / portfolio.starting_balance * 100.0) if portfolio.starting_balance > 0 else 0.0
    slots_used = sum(1 for p in portfolio.positions if p.quantity > 0)
    return {
        "starting_balance": portfolio.starting_balance,
        "cash": round(portfolio.cash, 4),
        "equity": round(equity, 4),
        "positions_value": round(positions_value, 4),
        "realized_pnl": round(portfolio.realized_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "total_pnl_pct": round(total_pnl_pct, 4),
        "daily_pnl_pct": round(daily_pnl_pct, 4),
        "day_start_equity": round(day_start, 4),
        "day_start_date": portfolio.day_start_date,
        "positions": live_positions,
        "slots_used": slots_used,
        "max_concurrent_positions": settings.max_concurrent_positions,
        "updated_at": portfolio.updated_at,
    }


@api_router.post("/portfolio/reset", dependencies=[Depends(require_owner)])
async def portfolio_reset():
    fresh = await reset_portfolio(db)
    return {"ok": True, "portfolio": fresh.model_dump()}


@api_router.post("/positions/{base}/close", dependencies=[Depends(require_owner)])
async def manual_close_position(base: str):
    """Manual Emergency Exit (owner-only): immediately market-close a single open
    position. Routes a real sell in LIVE/DRY_RUN, simulates the fill in PAPER —
    the same path the position watcher uses. Tags the trade `exit_reason=MANUAL_EXIT`."""
    from trading_engine import _execute_sell, _record_live_sell, set_symbol_cooldown, save_portfolio
    from position_watcher import _route_executor
    from models import TradeLog, AIReasoning, compute_return_and_hold

    symbol = base if "/" in base else f"{base.upper()}/USD"
    portfolio = await load_portfolio(db)
    settings = await load_settings(db)
    pos = next((p for p in portfolio.positions if p.symbol == symbol and p.quantity > 0), None)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No open position for {symbol}")

    snap = await fetch_snapshot(symbol)
    if snap is None:
        raise HTTPException(status_code=503, detail=f"No live price for {symbol}; cannot route exit")

    reasoning = AIReasoning(
        symbol=symbol, bias="NEUTRAL", confidence=0.0,
        reason="Manual emergency exit (owner-triggered)",
        news_summary="(manual exit; no Gemini call)",
        evidence={"exit_reason": "MANUAL_EXIT", "source": "owner"},
        decision="SELL",
    )
    await db.reasoning.insert_one(reasoning.model_dump())

    executor, trade_mode = await _route_executor(settings)
    if executor is not None:
        result = await executor.place_sell(
            symbol=symbol, qty=pos.quantity, bid=snap.bid, max_spread_pct=settings.max_spread_pct,
        )
        trade_doc = await _record_live_sell(
            db, portfolio, symbol, result, reasoning,
            macro_confidence=0.0, fusion_summary="MANUAL EXIT (owner)",
            mode=trade_mode, exit_reason="MANUAL_EXIT", expected_trigger_price=snap.bid,
        )
    else:
        qty, notional, realized, fee = _execute_sell(portfolio, symbol, snap.bid, settings.taker_fee_pct)
        if qty <= 0:
            raise HTTPException(status_code=409, detail="Exit declined (rounding/empty position)")
        _m_ret, _m_hold = compute_return_and_hold(pos.avg_cost, pos.entry_timestamp, snap.bid)
        trade = TradeLog(
            symbol=symbol, side="SELL", quantity=qty, price=snap.bid, notional=notional,
            mode="PAPER", confidence=0.0, reasoning_id=reasoning.id, pnl=realized, fee_usd=fee,
            slippage_usd=0.0, note="MANUAL EXIT (owner)", exit_reason="MANUAL_EXIT",
            sector=pos.sector, atr_at_entry=pos.atr_at_entry,
            atr_percentile_at_entry=pos.atr_percentile_at_entry,
            volatility_regime=pos.volatility_regime, entry_extension_pct=pos.entry_extension_pct,
            trade_result=("WIN" if realized > 0 else "LOSS" if realized < 0 else "BREAKEVEN"),
            mfe_pct=pos.mfe_pct, mae_pct=pos.mae_pct,
            entry_price=pos.avg_cost, entry_timestamp=pos.entry_timestamp,
            return_pct=_m_ret, hold_seconds=_m_hold,
            entry_attribution=pos.entry_attribution or {},
        )
        await db.trades.insert_one(trade.model_dump())
        trade_doc = trade.model_dump()
        await save_portfolio(db, portfolio)

    # Cooldown so the bot doesn't immediately re-enter the symbol we just bailed on.
    await set_symbol_cooldown(db, symbol, settings.sl_cooldown_seconds, "MANUAL_EXIT")

    # Push alert (best-effort, mobile).
    try:
        from push_service import send_push_event
        _pnl = trade_doc.get("pnl") if isinstance(trade_doc, dict) else None
        _msg = f"{symbol} closed (manual exit)" + (f" · P&L ${_pnl:.2f}" if isinstance(_pnl, (int, float)) else "")
        await send_push_event(db, "trade_closed", _msg)
    except Exception:
        pass

    return {"ok": True, "symbol": symbol, "exit_reason": "MANUAL_EXIT", "trade": trade_doc}


@api_router.post("/history/clear", dependencies=[Depends(require_owner)])
async def clear_history(also_reset_portfolio: bool = False):
    """Wipe trade + reasoning history. Optionally reset portfolio too."""
    trades_del = await db.trades.delete_many({})
    reasoning_del = await db.reasoning.delete_many({})
    result = {
        "ok": True,
        "trades_deleted": trades_del.deleted_count,
        "reasoning_deleted": reasoning_del.deleted_count,
    }
    if also_reset_portfolio:
        fresh = await reset_portfolio(db)
        result["portfolio"] = fresh.model_dump()
    return result


@api_router.post("/admin/fresh-start", dependencies=[Depends(require_owner)])
async def admin_fresh_start():
    """Owner-only hard reset: wipe ALL trade/research/strategy history, reset the
    portfolio to a fresh $1200 paper book, and set flat $75 lot sizing. Use this to
    start a clean strategy-comparison run (preview AND production each reset separately).

    Uses collection ``drop()`` (an O(1) metadata op) instead of ``delete_many({})`` so it
    stays instant and cannot time out / hang on large production collections (25k+ docs)."""
    collections = [
        "trades", "reasoning", "research_log", "shadow_positions", "shadow_trades",
        "stop_loss_simulation_logs", "strategy_sandbox_logs", "strategy_lab_log",
        "cooldowns", "pending_orders",
    ]
    dropped = {}
    for c in collections:
        with contextlib.suppress(Exception):
            await db[c].drop()
        dropped[c] = "dropped"

    # Recreate the bounded indexes that drop() removed (TTL keeps the lab log from growing
    # unbounded even before the next restart).
    with contextlib.suppress(Exception):
        await db.strategy_lab_log.create_index([("strategy", 1), ("detected_at", -1)])
        await db.strategy_lab_log.create_index([("outcome", 1), ("detected_at", 1)])
        await db.strategy_lab_log.create_index("detected_at")
        await db.strategy_lab_log.create_index("created_at", expireAfterSeconds=30 * 24 * 3600)

    fresh = await reset_portfolio(db)  # fresh Portfolio() -> $1200 defaults

    settings = await load_settings(db)
    settings.normal_lot_usd = 75.0
    settings.strong_lot_usd = 75.0
    settings.breakout_lot_usd = 75.0
    await save_settings(db, settings)

    global _RESEARCH_CACHE, _RESEARCH_CACHE_TS
    _RESEARCH_CACHE = {}
    _RESEARCH_CACHE_TS = 0.0

    logger.info("Fresh-start reset performed by owner: %s", dropped)
    return {
        "ok": True,
        "dropped": dropped,
        "portfolio": fresh.model_dump(),
        "lot_usd": 75.0,
        "starting_balance": fresh.starting_balance,
    }


@api_router.get("/trades")
async def get_trades(limit: int = Query(50, le=500)):
    cursor = db.trades.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(limit)
    return {"items": docs, "count": len(docs)}


@api_router.get("/reasoning")
async def get_reasoning(
    limit: int = Query(50, le=500),
    symbol: str | None = None,
    executed_only: bool = False,
):
    q: dict[str, Any] = {}
    if symbol:
        q["symbol"] = symbol if "/" in symbol else f"{symbol.upper()}/USD"
    if executed_only:
        # Only entries that produced an actual order (BUY or SELL with no blocking reasons).
        q["decision"] = {"$in": ["BUY", "SELL"]}
        q["$or"] = [{"blocked_reasons": {"$exists": False}}, {"blocked_reasons": {"$size": 0}}]
    cursor = db.reasoning.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(limit)
    return {"items": docs, "count": len(docs)}


@api_router.get("/cooldowns")
async def get_cooldowns():
    """List active per-symbol cooldown locks (SL/TRAIL)."""
    docs = await db.cooldowns.find({}, {"_id": 1, "unlock_at": 1, "reason": 1, "started_at": 1}).to_list(50)
    now = datetime.now(UTC)
    out = []
    for d in docs:
        try:
            ts = datetime.fromisoformat(d["unlock_at"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            remaining = max(0, int((ts - now).total_seconds()))
        except Exception:
            remaining = 0
        out.append({
            "symbol": d["_id"],
            "unlock_at": d["unlock_at"],
            "reason": d.get("reason"),
            "started_at": d.get("started_at"),
            "remaining_seconds": remaining,
        })
    return {"items": [c for c in out if c["remaining_seconds"] > 0], "count": len(out)}


@api_router.delete("/cooldowns/{symbol_base}", dependencies=[Depends(require_owner)])
async def clear_cooldown(symbol_base: str):
    """Manually clear a symbol cooldown (useful when the bot is being too cautious)."""
    sym = symbol_base if "/" in symbol_base else symbol_base.upper()
    res = await db.cooldowns.delete_one({"_id": sym})
    return {"ok": True, "deleted": res.deleted_count}


@api_router.get("/market/candles")
async def market_candles(
    symbol: str = Query(...),
    timeframe: str = Query("1h"),
    limit: int = Query(48, le=750),
):
    """OHLCV candles for charting. Supports 1h / 4h / 1d via market_data fetchers."""
    from market_data import fetch_ohlcv_1d, fetch_ohlcv_1h, fetch_ohlcv_4h
    tf = timeframe if timeframe in ("1h", "4h", "1d") else "1h"
    if tf == "4h":
        bars = await fetch_ohlcv_4h(symbol, limit=max(limit, 24))
    elif tf == "1d":
        bars = await fetch_ohlcv_1d(symbol, limit=max(limit, 24))
    else:
        bars = await fetch_ohlcv_1h(symbol, limit=max(limit, 24))
    bars = bars[-limit:] if bars else []
    out = [
        {"t": int(b[0]), "open": b[1], "high": b[2], "low": b[3], "close": b[4], "volume": b[5]}
        for b in bars
    ]
    return {"symbol": symbol, "timeframe": tf, "candles": out}


@api_router.get("/risk/status")
async def risk_status():
    settings = await load_settings(db)
    portfolio = await load_portfolio(db)
    # use latest reasoning to estimate macro confidence; fallback to settings.min_confidence
    last = await db.reasoning.find({}, {"_id": 0}).sort("timestamp", -1).limit(1).to_list(1)
    macro_conf = float(last[0]["confidence"]) if last else 0.0
    # average spread across enabled symbols (or query primary)
    snap = await fetch_snapshot(settings.enabled_symbols[0]) if settings.enabled_symbols else None
    if snap is None:
        # synthesize a minimal snapshot to evaluate manual kill / daily-loss switches anyway
        snap = MarketSnapshot(symbol="BTC/USD", price=0, bid=0, ask=0, spread_pct=0.0, orderbook_imbalance=0.0, exchange="unknown")
    kill = compute_kill_switches(snap, portfolio, settings, macro_conf)
    return {
        "status": kill.model_dump(),
        "thresholds": {
            "max_spread_pct": settings.max_spread_pct,
            "max_daily_loss_pct": settings.max_daily_loss_pct,
            "min_confidence": settings.min_confidence,
        },
        "trading_mode": settings.trading_mode,
        "manual_kill_switch": settings.manual_kill_switch,
    }


@api_router.get("/pending_orders")
async def pending_orders():
    """Resting Post-Only maker BUY orders (PAPER) awaiting fill or cancellation."""
    docs = await db.pending_orders.find({}, {"_id": 0}).sort("placed_at", 1).to_list(100)
    return {"items": docs, "count": len(docs)}


@api_router.get("/analytics/performance")
async def analytics_performance(exclude_synthetic: bool = Query(False)):
    """Quantitative metrics over the trade log (Phase A research layer).

    Returns Statistical Expectancy, Profit Factor, friction (fees + slippage),
    per-volatility-regime breakdown — for BOTH a rolling trailing-24h window
    (primary live view) and a calendar-day snapshot (secondary). Also reports
    current sector exposure + the High Beta Exposure warning flag.

    When ``exclude_synthetic=true`` the 15 seeded ``DEMO_SEED`` trades are
    filtered out so the operator can isolate organic paper performance during a
    live dry run.
    """
    now = datetime.now(UTC)
    rolling_cutoff = (now - timedelta(hours=24)).isoformat()
    calendar_cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Optional synthetic filter: exclude DEMO_SEED docs from every window.
    synthetic_filter = {"note": {"$ne": "DEMO_SEED"}} if exclude_synthetic else {}

    rolling_trades = await db.trades.find(
        {"timestamp": {"$gte": rolling_cutoff}, **synthetic_filter}, {"_id": 0},
    ).sort("timestamp", 1).to_list(800)
    calendar_trades = await db.trades.find(
        {"timestamp": {"$gte": calendar_cutoff}, **synthetic_filter}, {"_id": 0},
    ).sort("timestamp", 1).to_list(800)

    portfolio = await load_portfolio(db)
    open_positions = [p.model_dump() for p in portfolio.positions if p.quantity > 0]
    exposure = sector_exposure(open_positions)

    # all-time closed trades power the "Best Regime to Trade" insight
    all_sells = await db.trades.find(
        {"side": "SELL", "status": "FILLED", **synthetic_filter}, {"_id": 0},
    ).sort("timestamp", 1).to_list(1000)
    insight = regime_insight(all_sells)

    synthetic_count = await db.trades.count_documents({"note": "DEMO_SEED"})

    return {
        "generated_at": now.isoformat(),
        "exclude_synthetic": exclude_synthetic,
        "synthetic_count": synthetic_count,
        "rolling_24h": compute_performance(rolling_trades),
        "calendar_day": compute_performance(calendar_trades),
        "regime_insight": insight,
        "sector_exposure": exposure,
        "high_beta_warning": exposure["high_beta_warning"],
        "open_positions": [
            {"symbol": p["symbol"], "sector": p.get("sector"),
             "volatility_regime": p.get("volatility_regime"),
             "atr_percentile_at_entry": p.get("atr_percentile_at_entry")}
            for p in open_positions
        ],
    }


@api_router.get("/analytics/graduation")
async def analytics_graduation():
    """Objective 10-gate paper→live graduation scorecard. Proves the system has
    a repeatable edge that survives fees, slippage and different regimes — NOT
    mere profitability. Excludes synthetic DEMO_SEED trades."""
    trades = await db.trades.find(
        {"note": {"$ne": "DEMO_SEED"}}, {"_id": 0},
    ).sort("timestamp", 1).to_list(1500)

    portfolio = await load_portfolio(db)
    settings = await load_settings(db)

    return graduation_readiness(
        trades,
        starting_equity=portfolio.starting_balance,
        account_max_drawdown_pct=settings.account_max_drawdown_pct,
    )


# ---- Research aggregation cache (precomputed every 60s -> instant tab loads, credit-free) ----
_RESEARCH_CACHE: dict = {}
_RESEARCH_CACHE_TS: float = 0.0
_RESEARCH_WINDOW_DAYS = 10  # cap scan window (counterfactuals resolve within 7d anyway)
# Exclude the heavy nested fields the aggregations never use -> big memory cut on large DBs.
_RESEARCH_PROJECTION = {"_id": 0, "evidence": 0, "sector_data": 0, "level": 0}


async def compute_research_cache() -> dict:
    """Single capped + projected scan of research_log -> all Phase-B aggregations in one
    pass. Capped window + field projection keep memory bounded so production containers
    don't OOM/crash-loop as the logs grow."""
    from strategies import summarize_staged_exit
    global _RESEARCH_CACHE, _RESEARCH_CACHE_TS
    cutoff = (datetime.now(UTC) - timedelta(days=_RESEARCH_WINDOW_DAYS)).isoformat()
    rows = await db.research_log.find(
        {"timestamp": {"$gte": cutoff}}, _RESEARCH_PROJECTION,
    ).sort("timestamp", -1).to_list(2000)
    sells = await db.trades.find({"side": "SELL"}, {"_id": 0}).sort("timestamp", -1).to_list(800)
    sl_logs = await db.stop_loss_simulation_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(800)
    rejections = await summarize_rejections(db)
    strategy_lab = await summarize_strategy_lab(db)

    # The summarize_* functions iterate up to ~8000 rows in pure Python — run them off
    # the event loop so the cache refresh (every 60s) never stalls login/health requests.
    def _sync_bundle():
        return {
            "funnel": {"funnel": summarize_funnel(rows), "breaker_accuracy": summarize_breaker_accuracy(rows)},
            "winner_profile": summarize_winner_profile(sells),
            "rsi_distribution": summarize_rsi_distribution(rows),
            "missed_opportunities": summarize_missed_opportunities(rows),
            "zone_effectiveness": summarize_zone_effectiveness(rows),
            "staged_exit": summarize_staged_exit(sl_logs),
        }
    sync_part = await asyncio.to_thread(_sync_bundle)
    bundle = {
        **sync_part,
        "rejections": rejections,
        "strategy_sandbox": strategy_lab,
        "strategy_lab": strategy_lab,
    }
    _RESEARCH_CACHE = bundle
    _RESEARCH_CACHE_TS = time.time()
    return bundle


async def get_research_cache() -> dict:
    """Return the cached bundle; compute lazily on a cold cache (first hit after boot)."""
    if not _RESEARCH_CACHE:
        await compute_research_cache()
    return _RESEARCH_CACHE


async def research_cache_loop():
    while True:
        try:
            await compute_research_cache()
        except Exception as e:
            logger.warning("research cache compute failed (non-fatal): %s", e)
        await asyncio.sleep(180)



@api_router.get("/research/log")
async def research_log(
    limit: int = Query(100, le=1000),
    symbol: str | None = None,
    tier: str | None = None,
    row_type: str | None = None,
    unresolved: bool = False,
):
    """Raw research_log rows (permanent, append-only decision history)."""
    q: dict[str, Any] = {}
    if symbol:
        q["symbol"] = symbol if "/" in symbol else f"{symbol.upper()}/USD"
    if tier:
        q["confidence_tier"] = tier.upper()
    if row_type:
        q["row_type"] = row_type.upper()
    if unresolved:
        q["cf_resolved_7d"] = False
    cursor = db.research_log.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(limit)
    total = await db.research_log.count_documents({})
    return {"items": docs, "count": len(docs), "total_rows": total}


@api_router.get("/research/summary")
async def research_summary(band_pct: float = Query(1.5, ge=0.0, le=20.0)):
    """Decision/tier distribution + per-confidence-bucket counterfactual stats +
    Near-Miss (0.70-0.79 BULLISH) analytics over the whole research log."""
    # Projection drops the heavy nested fields summarize_research never reads
    # (evidence/sector_data/level) + a capped recent window -> bounded memory so
    # large production DBs (25k+ rows) don't OOM/crash-loop the container.
    cutoff = (datetime.now(UTC) - timedelta(days=_RESEARCH_WINDOW_DAYS)).isoformat()
    rows = await db.research_log.find(
        {"timestamp": {"$gte": cutoff}}, _RESEARCH_PROJECTION,
    ).sort("timestamp", -1).to_list(2000)
    return summarize_research(rows, band_pct=band_pct)


@api_router.post("/research/resolve", dependencies=[Depends(require_owner)])
async def research_resolve_now():
    """Manually trigger counterfactual resolution (otherwise runs every 10 min)."""
    resolved = await resolve_counterfactuals(db)
    return {"resolved": resolved}


@api_router.get("/research/shadow")
async def research_shadow(limit: int = Query(200, le=2000)):
    """SHADOW simulator (Phase 2.1): open virtual near-miss trades + closed
    outcomes + win-rate/expectancy summary."""
    open_docs = await db.shadow_positions.find({}, {"_id": 0}).to_list(200)
    closed = await db.shadow_trades.find({}, {"_id": 0}).sort("closed_at", -1).to_list(limit)
    return {"open": open_docs, "closed": closed, "summary": summarize_shadow(open_docs, closed)}


@api_router.post("/research/shadow/tick", dependencies=[Depends(require_owner)])
async def research_shadow_tick():
    """Manually run one shadow exit-check pass (otherwise runs every 30s)."""
    closed = await watch_shadow_once(db)
    return {"closed": closed}


@api_router.get("/research/funnel")
async def research_funnel(since_hours: int | None = Query(None)):
    """Setup Funnel (Detected→Qualified→PASS/CAUTION/VETO→Executed) + Circuit-Breaker
    accuracy (forward outcomes per breaker state). Public/read-only. Served from the
    60s precomputed cache for instant tab loads."""
    if since_hours:
        cutoff = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
        rows = await db.research_log.find(
            {"timestamp": {"$gte": cutoff}}, _RESEARCH_PROJECTION,
        ).to_list(2000)
        return {"funnel": summarize_funnel(rows), "breaker_accuracy": summarize_breaker_accuracy(rows)}
    c = await get_research_cache()
    return c["funnel"]


@api_router.get("/research/rejections")
async def research_rejections(since_hours: int | None = Query(None)):
    """Rejection Leaderboard (Phase 2): reason-code distribution across evaluations."""
    if since_hours:
        return await summarize_rejections(db, since_hours=since_hours)
    return (await get_research_cache())["rejections"]


@api_router.get("/research/winner_profile")
async def research_winner_profile():
    """Phase B 'What Makes Winners?' — avg entry features of WIN vs LOSS closed trades."""
    return (await get_research_cache())["winner_profile"]


@api_router.get("/research/missed_opportunities")
async def research_missed_opportunities(since_hours: int | None = Query(None)):
    """Phase B 'Why Profitable Trades Were Rejected' — per-filter counterfactual outcomes."""
    if since_hours:
        cutoff = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
        rows = await db.research_log.find(
            {"timestamp": {"$gte": cutoff}}, _RESEARCH_PROJECTION,
        ).to_list(2000)
        return summarize_missed_opportunities(rows)
    return (await get_research_cache())["missed_opportunities"]


@api_router.get("/research/rsi_distribution")
async def research_rsi_distribution():
    """Phase B RSI bucket study from resolved counterfactuals."""
    return (await get_research_cache())["rsi_distribution"]


@api_router.get("/research/zone_effectiveness")
async def research_zone_effectiveness():
    """Phase B Support-Zone Effectiveness — bounces vs failures + avg return/drawdown."""
    return (await get_research_cache())["zone_effectiveness"]


@api_router.get("/research/strategy_sandbox")
async def research_strategy_sandbox():
    """Phase B Strategy Sandbox scoreboard — 5 regime strategies competing."""
    return (await get_research_cache())["strategy_sandbox"]


@api_router.get("/research/strategy_lab")
async def research_strategy_lab():
    """Phase B Strategy Research Laboratory — full pipeline (Detected→Qualified→Breaker
    Pass→Resolved→Wins) + research metrics (EV, Profit Factor, conversion, etc.) +
    deltas vs the Hunter benchmark. Sorted by Expected Value."""
    return (await get_research_cache())["strategy_lab"]


@api_router.get("/research/staged_exit")
async def research_staged_exit():
    """Phase B structure-staged exit simulation — Actual vs Theoretical cumulative P&L."""
    return (await get_research_cache())["staged_exit"]


@api_router.get("/research/entry_quality")
async def research_entry_quality():
    """Phase E Edge Discovery — does entry-quality grade / regime / profile predict
    outcomes? Aggregates graded closed trades (Hunter + Squeeze). Bounded query."""
    cursor = db.trades.find(
        {"side": "SELL", "trade_result": {"$in": ["WIN", "LOSS", "BREAKEVEN"]}},
        {"trade_result": 1, "return_pct": 1, "pnl": 1, "entry_attribution": 1, "_id": 0},
    ).sort("timestamp", -1).limit(600)
    rows = await cursor.to_list(length=600)

    def _bucket():
        return {"count": 0, "wins": 0, "sum_return": 0.0, "sum_pnl": 0.0}

    grades, regimes, profiles = {}, {}, {}
    total = 0
    for t in rows:
        attr = t.get("entry_attribution") or {}
        eq = attr.get("entry_quality") or {}
        grade = eq.get("grade")
        if not grade:
            continue  # only Phase-E graded trades
        total += 1
        regime = attr.get("asset_regime") or attr.get("regime_at_entry") or "UNKNOWN"
        profile = attr.get("entry_profile") or "UNKNOWN"
        ret = t.get("return_pct") or 0.0
        pnl = t.get("pnl") or 0.0
        win = t.get("trade_result") == "WIN"
        for d, key in ((grades, grade), (regimes, regime), (profiles, profile)):
            b = d.setdefault(key, _bucket())
            b["count"] += 1
            b["wins"] += 1 if win else 0
            b["sum_return"] += ret
            b["sum_pnl"] += pnl

    def _finalize(d):
        out = {}
        for k, b in d.items():
            c = b["count"] or 1
            out[k] = {
                "count": b["count"],
                "win_rate_pct": round(b["wins"] / c * 100, 1),
                "avg_return_pct": round(b["sum_return"] / c, 2),
                "net_pnl": round(b["sum_pnl"], 2),
            }
        return out

    grade_order = ["A+", "A", "B", "C"]
    gd = _finalize(grades)
    return {
        "total_graded": total,
        "grade_distribution": {g: gd[g] for g in grade_order if g in gd},
        "regime_distribution": _finalize(regimes),
        "profile_distribution": _finalize(profiles),
    }


@api_router.get("/levels/{base}")
async def get_levels_endpoint(base: str):
    """Historical horizontal support/resistance zones for a symbol (Phase 1.5a).
    Public/read-only. Credit-free (CCXT-only, cached)."""
    symbol = base if "/" in base else f"{base.upper()}/USD"
    settings = await load_settings(db)
    zones = await get_levels(symbol, settings)
    snap = await fetch_snapshot(symbol)
    price = snap.price if snap else None
    prox = settings.level_proximity_pct
    return {
        "symbol": symbol,
        "price": price,
        "zone_count": len(zones),
        "zones": zones,
        "support": nearest_support(price, zones, prox),
        "resistance": nearest_resistance(price, zones, prox),
    }


class LoginRequest(BaseModel):
    email: str
    password: str


@api_router.post("/auth/login")
async def auth_login(body: LoginRequest, request: Request):
    ident = f"{request.client.host if request.client else 'unknown'}:{body.email.strip().lower()}"
    token = await authenticate(db, body.email, body.password, ident)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"token": token, "email": os.environ.get("OWNER_EMAIL", "").strip().lower(), "role": "owner"}


@api_router.post("/auth/logout")
async def auth_logout():
    # Stateless Bearer tokens — client discards the token. Endpoint exists for symmetry.
    return {"ok": True}


@api_router.get("/auth/me")
async def auth_me(_owner: dict = Depends(require_owner)):
    return {"email": _owner.get("sub"), "role": _owner.get("role")}


# ---------- mobile push notifications ----------
class PushTokenBody(BaseModel):
    push_token: str
    platform: str = "unknown"
    prefs: dict | None = None


@api_router.post("/notifications/register", dependencies=[Depends(require_owner)])
async def register_push(body: PushTokenBody):
    """Store an Expo push token (+ per-event preferences) for the owner's device(s)."""
    from push_service import register_push_token
    await register_push_token(db, body.push_token, body.platform, body.prefs)
    return {"ok": True}


@api_router.post("/notifications/test", dependencies=[Depends(require_owner)])
async def test_push():
    """Owner-triggered test broadcast (validates device delivery on a real build)."""
    from push_service import send_push_event
    res = await send_push_event(db, "system_offline", "Test alert from Ananta — push is wired up.")
    return {"ok": True, **res}


@api_router.get("/settings")
async def get_settings(request: Request):
    s = await load_settings(db)
    d = s.model_dump()
    # Redact exchange credentials for non-owners (api keys AND secrets).
    if not is_owner_request(request):
        for k in ("coinbase_api_key", "coinbase_api_secret", "kraken_api_key", "kraken_api_secret"):
            if d.get(k):
                d[k] = "•" * 8
    return d


@api_router.put("/settings", dependencies=[Depends(require_owner)])
async def update_settings(update: SettingsUpdate):
    s = await load_settings(db)
    data = update.model_dump(exclude_unset=True)

    # validate trading_mode
    if "trading_mode" in data and data["trading_mode"] not in ("PAPER", "DRY_RUN", "LIVE"):
        raise HTTPException(status_code=400, detail="trading_mode must be PAPER, DRY_RUN, or LIVE")

    # clamp numeric fields
    for k, lo, hi in [
        ("max_spread_pct", 0.001, 5.0),
        ("max_daily_loss_pct", 0.1, 50.0),
        ("min_confidence", 0.0, 1.0),
        ("position_size_pct_min", 0.1, 10.0),
        ("position_size_pct_max", 0.1, 20.0),
        ("normal_lot_usd", 1.0, 1000.0),
        ("strong_lot_usd", 1.0, 1000.0),
        ("strong_min_confidence", 0.0, 1.0),
        ("strong_min_atr_percentile", 0.0, 100.0),
        ("strong_min_adx", 0.0, 100.0),
        ("stop_loss_pct", 0.1, 50.0),
        ("trail_arm_pct", 0.1, 50.0),
        ("trail_distance_pct", 0.1, 50.0),
        ("vault_max_override_usd", 1.0, 1000000.0),
        ("taker_fee_pct", 0.0, 5.0),
        ("maker_fee_pct", 0.0, 5.0),
        ("breakout_paper_slippage_pct", 0.0, 5.0),
        ("breakout_lot_usd", 1.0, 10000.0),
        ("breakout_min_confidence", 0.0, 1.0),
        ("breakout_volume_percentile", 0.0, 100.0),
        ("breakout_max_spread_pct", 0.0, 5.0),
        ("breakout_trail_arm_pct", 0.1, 50.0),
        ("breakout_trail_distance_pct", 0.1, 50.0),
    ]:
        if k in data and data[k] is not None:
            data[k] = max(lo, min(hi, float(data[k])))
    for k, lo, hi in [
        ("sl_cooldown_seconds", 0, 86400),
        ("trail_cooldown_seconds", 0, 86400),
    ]:
        if k in data and data[k] is not None:
            data[k] = max(int(lo), min(int(hi), int(data[k])))
    if "max_concurrent_positions" in data and data["max_concurrent_positions"] is not None:
        data["max_concurrent_positions"] = max(1, min(20, int(data["max_concurrent_positions"])))
    if "position_watcher_interval_seconds" in data and data["position_watcher_interval_seconds"] is not None:
        data["position_watcher_interval_seconds"] = max(5, min(300, int(data["position_watcher_interval_seconds"])))

    # ignore masked secrets (frontend re-sends "••••••••")
    for k in ("coinbase_api_secret", "kraken_api_secret"):
        if k in data and data[k] and set(str(data[k])) <= {"•"}:
            data.pop(k)

    _kill_was_on = bool(getattr(s, "manual_kill_switch", False))
    for k, v in data.items():
        setattr(s, k, v)
    saved = await save_settings(db, s)

    # Push alert when the kill switch is newly engaged (best-effort, mobile).
    if data.get("manual_kill_switch") is True and not _kill_was_on:
        try:
            from push_service import send_push_event
            await send_push_event(db, "kill_switch", "Manual kill switch engaged — all new entries halted.")
        except Exception:
            pass

    d = saved.model_dump()
    for k in ("coinbase_api_secret", "kraken_api_secret"):
        if d.get(k):
            d[k] = "•" * 8
    return d


@api_router.get("/watchlist/validate")
async def watchlist_validate():
    """Confirm whether this environment is scanning the canonical 10-asset watchlist.
    Lets you verify production never silently drifts from dev. Public/read-only."""
    from asset_profiles import DEFAULT_ASSETS
    s = await load_settings(db)
    current = list(s.enabled_symbols or [])
    expected = list(DEFAULT_ASSETS)
    return {
        "in_sync": sorted(current) == sorted(expected),
        "current": current,
        "expected": expected,
        "current_count": len(current),
        "expected_count": len(expected),
        "missing": [a for a in expected if a not in current],
        "extra": [a for a in current if a not in expected],
    }


@api_router.post("/watchlist/sync", dependencies=[Depends(require_owner)])
async def watchlist_sync():
    """Owner: write the canonical 10-asset watchlist into THIS environment's DB.
    Fixes prod/dev drift (e.g. production stuck on 5 assets) without a destructive reset."""
    from asset_profiles import DEFAULT_ASSETS
    s = await load_settings(db)
    s.enabled_symbols = list(DEFAULT_ASSETS)
    saved = await save_settings(db, s)
    return {"ok": True, "enabled_symbols": saved.enabled_symbols, "count": len(saved.enabled_symbols)}


@api_router.post("/cycle/run", dependencies=[Depends(require_owner)])
async def run_cycle():
    """Run one evaluation cycle synchronously and return full results.
    Useful for the 'Run Cycle Now' button on the dashboard."""
    results = await evaluate_all(db)
    return {"ran_at": datetime.now(UTC).isoformat(), "results": results}


@api_router.post("/cycle/run/{symbol_base}", dependencies=[Depends(require_owner)])
async def run_cycle_symbol(symbol_base: str):
    symbol = symbol_base if "/" in symbol_base else f"{symbol_base.upper()}/USD"
    r = await evaluate_symbol(db, symbol)
    return r


@api_router.get("/news/current")
async def current_news():
    text = await get_current_summary()
    return {
        "summary": text,
        "ts": datetime.now(UTC).isoformat(),
        "cache": get_cache_info(),
    }


@api_router.get("/live/status")
async def live_status_endpoint():
    """Diagnostic endpoint - tells the operator UI whether LIVE execution is
    actually wired (env gate, API keys, exchange selection). Does NOT leak
    the keys themselves."""
    return live_execution_status()


@api_router.get("/environment")
async def get_environment():
    """Master environment state for the header toggle: PAPER vs LIVE plus the
    live-gate readiness (env interlock + API keys) so the UI can warn if LIVE
    won't actually route real orders."""
    s = await load_settings(db)
    status = live_execution_status()
    is_live = s.trading_mode == "LIVE"
    return {
        "trading_mode": s.trading_mode,
        "is_live": is_live,
        "live_gate_open": status.get("live_gate_open", False),
        "ready_to_trade": status.get("ready_to_trade", False),
        "exchange": status.get("exchange"),
    }


@api_router.post("/environment/{mode}", dependencies=[Depends(require_owner)])
async def set_environment(mode: str):
    """One-click master switch. Drives the single source-of-truth `trading_mode`
    between PAPER (simulation) and LIVE (real Kraken routing). DRY_RUN remains
    available via the advanced Settings page but the header toggle is two-state."""
    mode = mode.upper()
    if mode not in ("PAPER", "LIVE"):
        raise HTTPException(status_code=400, detail="mode must be PAPER or LIVE")
    s = await load_settings(db)
    s.trading_mode = mode
    await save_settings(db, s)
    status = live_execution_status()
    logger.warning("TRADING ENVIRONMENT switched to %s by operator", mode)
    return {
        "trading_mode": mode,
        "is_live": mode == "LIVE",
        "live_gate_open": status.get("live_gate_open", False),
        "ready_to_trade": status.get("ready_to_trade", False) if mode == "LIVE" else False,
        "exchange": status.get("exchange"),
    }



class BacktestRequest(BaseModel):
    symbols: list[str] = ["BTC/USDC", "ETH/USDC"]
    days: int = 14
    stop_loss_pct: float = 1.0
    take_profit_pct: float = 2.0
    starting_balance: float = 100.0
    exchange: str = "kraken"
    min_confidence: float = 0.4  # CLI/backtest default; production engine uses 0.6


@api_router.post("/backtest/run", dependencies=[Depends(require_owner)])
async def backtest_run(req: BacktestRequest):
    """Run a backtest over the requested symbols. Synchronous from the
    client's view; internally CCXT + simulation run in a worker thread so
    the event loop stays responsive (the trading loop keeps ticking)."""
    # clamp inputs
    days = max(1, min(90, req.days))
    sl = max(0.1, min(20.0, req.stop_loss_pct))
    tp = max(0.1, min(50.0, req.take_profit_pct))
    starting = max(10.0, min(1_000_000.0, req.starting_balance))
    min_conf = max(0.0, min(1.0, req.min_confidence))
    if not req.symbols:
        raise HTTPException(status_code=400, detail="symbols must not be empty")
    try:
        out = await run_for_symbols_async(
            req.symbols,
            days=days,
            stop_loss_pct=sl,
            take_profit_pct=tp,
            starting_balance=starting,
            exchange_name=req.exchange,
            min_confidence=min_conf,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("backtest failed: %s", e)
        raise HTTPException(status_code=500, detail=f"backtest failed: {e}") from e
    out["params"] = {
        "days": days, "stop_loss_pct": sl, "take_profit_pct": tp,
        "starting_balance": starting, "exchange": req.exchange,
        "min_confidence": min_conf,
    }
    return out


class BacktestSweepRequest(BaseModel):
    symbols: list[str] = ["BTC/USDC", "ETH/USDC"]
    days: int = 14
    sl_pcts: list[float] = [0.5, 1.0, 1.5, 2.0]
    tp_pcts: list[float] = [1.5, 2.0, 3.0]
    starting_balance: float = 100.0
    min_confidence: float = 0.4
    exchange: str = "kraken"


@api_router.post("/backtest/sweep", dependencies=[Depends(require_owner)])
async def backtest_sweep(req: BacktestSweepRequest):
    """Cartesian-product sweep of (stop-loss, take-profit) per symbol. Each
    symbol's candles are fetched ONCE and the SL/TP grid is run against the
    cached data — so a 4×3 sweep over 2 symbols costs only 2 CCXT calls."""
    days = max(1, min(90, req.days))
    starting = max(10.0, min(1_000_000.0, req.starting_balance))
    min_conf = max(0.0, min(1.0, req.min_confidence))
    sl_pcts = sorted({max(0.1, min(20.0, x)) for x in req.sl_pcts})
    tp_pcts = sorted({max(0.1, min(50.0, x)) for x in req.tp_pcts})
    if not req.symbols:
        raise HTTPException(status_code=400, detail="symbols must not be empty")
    if not sl_pcts or not tp_pcts:
        raise HTTPException(status_code=400, detail="sl_pcts and tp_pcts must each have at least one value")
    if len(sl_pcts) * len(tp_pcts) > 50:
        raise HTTPException(status_code=400, detail="sweep too large (max 50 combinations)")
    try:
        out = await run_sweep_for_symbols_async(
            req.symbols,
            sl_pcts=sl_pcts,
            tp_pcts=tp_pcts,
            days=days,
            starting_balance=starting,
            exchange_name=req.exchange,
            min_confidence=min_conf,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("sweep failed: %s", e)
        raise HTTPException(status_code=500, detail=f"sweep failed: {e}") from e
    return out


# ---- public read-only snapshot for the Judge View link ----
@api_router.get("/public/snapshot")
async def public_snapshot():
    """Single endpoint exposing everything the read-only Judge View needs.
    Excludes API key material entirely."""
    settings = await load_settings(db)
    portfolio_doc = await get_portfolio()  # already serialized
    risk = await risk_status()
    trades = await db.trades.find({}, {"_id": 0}).sort("timestamp", -1).limit(100).to_list(100)
    reasoning = await db.reasoning.find({}, {"_id": 0}).sort("timestamp", -1).limit(100).to_list(100)
    snaps = await fetch_snapshots(settings.enabled_symbols)

    # whitelist - never expose secrets, ids or internal mongo fields
    s_full = settings.model_dump()
    public_settings = {
        k: s_full[k] for k in (
            "max_spread_pct",
            "max_daily_loss_pct",
            "min_confidence",
            "position_size_pct_min",
            "position_size_pct_max",
            "adaptive_sizing_enabled",
            "normal_lot_usd",
            "strong_lot_usd",
            "strong_min_confidence",
            "strong_min_atr_percentile",
            "strong_min_adx",
            "max_concurrent_positions",
            "stop_loss_pct",
            "trail_arm_pct",
            "trail_distance_pct",
            "position_watcher_interval_seconds",
            "vault_sync_enabled",
            "vault_max_override_usd",
            "htf_trend_enabled",
            "taker_fee_pct",
            "maker_fee_pct",
            "breakout_paper_slippage_pct",
            "breakout_lot_usd",
            "breakout_min_confidence",
            "breakout_volume_percentile",
            "breakout_max_spread_pct",
            "breakout_trail_arm_pct",
            "breakout_trail_distance_pct",
            "sl_cooldown_seconds",
            "trail_cooldown_seconds",
            "trading_mode",
            "manual_kill_switch",
            "enabled_symbols",
        ) if k in s_full
    }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "portfolio": portfolio_doc,
        "risk": risk,
        "settings": public_settings,
        "snapshots": [s.model_dump() for s in snaps],
        "trades": trades,
        "reasoning": reasoning,
    }


@api_router.get("/report/full.pdf")
async def report_full_pdf():
    """Generate a clean PDF report containing portfolio, risk, trades, and AI reasoning."""
    from pdf_report import build_report
    portfolio_doc = await get_portfolio()
    risk = await risk_status()
    trades = await db.trades.find({}, {"_id": 0}).sort("timestamp", -1).limit(200).to_list(200)
    reasoning = await db.reasoning.find({}, {"_id": 0}).sort("timestamp", -1).limit(200).to_list(200)
    settings = (await load_settings(db)).model_dump()
    try:
        pdf_bytes = await asyncio.to_thread(
            build_report,
            portfolio=portfolio_doc,
            risk=risk,
            reasoning_items=reasoning,
            trades=trades,
            settings=settings,
        )
    except Exception as e:
        logger.exception("PDF build failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to build PDF: {e}") from e
    filename = f"ananta-report-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/report/trades.pdf")
async def report_trades_pdf(
    start: str | None = Query(None, description="Inclusive start date YYYY-MM-DD (UTC)"),
    end: str | None = Query(None, description="Inclusive end date YYYY-MM-DD (UTC)"),
):
    """Unified Trade-History export: a clean, chronological printout of EXECUTED
    (FILLED) trades, optionally filtered to an inclusive calendar date range."""
    from pdf_report import build_trades_report

    query: dict = {"status": {"$in": ["FILLED", None]}}
    ts_filter: dict = {}
    if start:
        ts_filter["$gte"] = f"{start}T00:00:00+00:00"
    if end:
        ts_filter["$lte"] = f"{end}T23:59:59.999999+00:00"
    if ts_filter:
        query["timestamp"] = ts_filter

    trades = await db.trades.find(query, {"_id": 0}).sort("timestamp", 1).to_list(5000)
    # only real executions (defensive: drop any cancelled/aborted rows if present)
    trades = [t for t in trades if (t.get("status", "FILLED") or "FILLED") == "FILLED"]
    summary = compute_performance(trades)
    try:
        pdf_bytes = await asyncio.to_thread(
            build_trades_report, trades, start_label=start, end_label=end, summary=summary,
        )
    except Exception as e:
        logger.exception("Trade-history PDF build failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to build PDF: {e}") from e
    suffix = f"{start or 'all'}_{end or 'now'}"
    filename = f"ananta-trades-{suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/report/reasoning.pdf")
async def report_reasoning_pdf(limit: int = Query(200, le=1000)):
    """Generate a PDF with the AI Reasoning timeline + Phase-B research analytics."""
    from pdf_report import build_report
    portfolio_doc = await get_portfolio()
    risk = await risk_status()
    reasoning = await db.reasoning.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    settings = (await load_settings(db)).model_dump()
    # Phase B: assemble the research & analytics bundle for offline analysis.
    research = {}
    try:
        research = await get_research_cache()
    except Exception as e:
        logger.warning("Research bundle for PDF failed (non-fatal): %s", e)
    try:
        pdf_bytes = await asyncio.to_thread(
            build_report,
            portfolio=portfolio_doc,
            risk=risk,
            reasoning_items=reasoning,
            trades=[],  # reasoning-only report
            settings=settings,
            research=research,
        )
    except Exception as e:
        logger.exception("PDF build failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to build PDF: {e}") from e
    filename = f"ananta-research-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- Research Lab: async validation queue ----
class LabRunCreate(BaseModel):
    kind: str  # backtest | grid_search | sensitivity | walk_forward
    symbols: list[str]
    period: str = "3m"  # 1m|2m|3m|quarter|6m|1y|2y|custom
    start_ms: int | None = None
    end_ms: int | None = None
    metric: str = "return_over_dd"
    folds: int = 5
    min_trades: int = 8
    grid: dict | None = None
    setting_overrides: dict | None = None
    profile_overrides: dict | None = None
    preset: str | None = None  # WS3 Mode C: named preset id (expands to setting_overrides)
    target: str | None = None
    values: list | None = None
    label: str | None = None


@api_router.get("/lab/data/coverage", dependencies=[Depends(require_owner)])
async def lab_data_coverage():
    """What history is seeded locally (drives the Research Lab asset/period pickers)."""
    from lab import data_store
    from lab.runner import _PERIOD_MONTHS  # noqa
    watch = (await load_settings(db)).enabled_symbols or []
    default = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "XRP/USD",
               "PAXG/USD", "LINK/USD", "AAVE/USD", "ARB/USD", "RENDER/USD"]
    syms = watch or default
    out = []
    for s in syms:
        c1h = data_store.coverage(s, "1h")
        c4 = data_store.coverage(s, "4h")
        c1 = data_store.coverage(s, "1d")
        out.append({"symbol": s, "bars_1h": c1h["count"], "bars_4h": c4["count"], "bars_1d": c1["count"],
                    "from": c1h["min_ts"] or c4["min_ts"], "to": c1h["max_ts"] or c4["max_ts"]})
    return {"symbols": out, "periods": list(_PERIOD_MONTHS.keys()) + ["custom"]}


@api_router.get("/lab/presets", dependencies=[Depends(require_owner)])
async def lab_presets():
    """WS3 Mode C: named parameter presets the operator can validate in one click."""
    from lab.presets import PRESETS
    return {"presets": PRESETS}


@api_router.post("/lab/runs", dependencies=[Depends(require_owner)])
async def lab_create_run(body: LabRunCreate):
    try:
        payload = body.model_dump()
        # Mode C: expand a named preset into concrete setting_overrides.
        if payload.get("preset"):
            from lab.presets import get_preset
            preset = get_preset(payload["preset"])
            if not preset:
                raise HTTPException(status_code=400, detail=f"unknown preset '{payload['preset']}'")
            payload["setting_overrides"] = {**(preset.get("setting_overrides") or {}), **(payload.get("setting_overrides") or {})}
            payload["kind"] = "backtest"
            payload["label"] = payload.get("label") or f"Preset: {preset['label']}"
        doc = await create_run(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": doc["id"], "status": doc["status"], "kind": doc["kind"]}


@api_router.get("/lab/runs", dependencies=[Depends(require_owner)])
async def lab_list_runs(limit: int = Query(30, le=100)):
    cur = db.lab_runs.find({}, {"_id": 0, "result": 0}).sort("created_at", -1).limit(limit)
    return {"runs": await cur.to_list(length=limit)}


@api_router.get("/lab/runs/{run_id}", dependencies=[Depends(require_owner)])
async def lab_get_run(run_id: str):
    run = await db.lab_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@api_router.delete("/lab/runs/{run_id}", dependencies=[Depends(require_owner)])
async def lab_delete_run(run_id: str):
    """Remove a single validation-run record (frees storage after the user downloads it)."""
    res = await db.lab_runs.delete_one({"id": run_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="run not found")
    return {"ok": True, "deleted": run_id}


@api_router.get("/lab/runs/{run_id}/pdf", dependencies=[Depends(require_owner)])
async def lab_run_pdf(run_id: str):
    run = await db.lab_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if run.get("status") != "DONE":
        raise HTTPException(status_code=409, detail=f"run not finished (status={run.get('status')})")
    from lab.lab_report import build_lab_report
    pdf_bytes = build_lab_report(run)
    fname = f"ananta_lab_{run['kind']}_{run_id[:8]}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@api_router.post("/lab/runs/{run_id}/propose", dependencies=[Depends(require_owner)])
async def lab_propose(run_id: str):
    """Build a production-settings proposal from a completed run's best params (diff only)."""
    run = await db.lab_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if run.get("status") != "DONE":
        raise HTTPException(status_code=409, detail="run not finished")
    from lab.proposals import best_params_from_run, build_diff
    params = best_params_from_run(run)
    if not params:
        raise HTTPException(status_code=400, detail="this run kind has no tunable params to promote")
    settings = await load_settings(db)
    doc = {
        "id": str(uuid.uuid4()), "run_id": run_id, "kind": run["kind"],
        "label": run.get("label"), "params": params, "diff": build_diff(params, settings),
        "status": "PROPOSED", "git_hash": run.get("git_hash"),
        "created_at": datetime.now(UTC).isoformat(), "applied_at": None,
    }
    await db.lab_param_proposals.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/lab/proposals", dependencies=[Depends(require_owner)])
async def lab_list_proposals(limit: int = Query(20, le=100)):
    cur = db.lab_param_proposals.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return {"proposals": await cur.to_list(length=limit)}


@api_router.post("/lab/proposals/{prop_id}/apply", dependencies=[Depends(require_owner)])
async def lab_apply_proposal(prop_id: str):
    """MANUAL APPROVAL GATE: push a proposal's params into the live production settings."""
    prop = await db.lab_param_proposals.find_one({"id": prop_id}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="proposal not found")
    if prop.get("status") == "APPLIED":
        raise HTTPException(status_code=409, detail="proposal already applied")
    from lab.proposals import apply_to_settings
    settings = await load_settings(db)
    changed = apply_to_settings(settings, prop["params"])
    await save_settings(db, settings)
    await db.lab_param_proposals.update_one(
        {"id": prop_id}, {"$set": {"status": "APPLIED", "applied_at": datetime.now(UTC).isoformat(),
                                   "applied_changes": changed}})
    return {"status": "APPLIED", "applied": changed,
            "note": "Live settings updated. Redeploy the backend to push to production."}


@api_router.post("/lab/proposals/{prop_id}/reject", dependencies=[Depends(require_owner)])
async def lab_reject_proposal(prop_id: str):
    r = await db.lab_param_proposals.update_one({"id": prop_id}, {"$set": {"status": "REJECTED"}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="proposal not found")
    return {"status": "REJECTED"}


# ---- mount router and CORS ----
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- lifecycle ----
@app.on_event("startup")
async def on_startup():
    # ensure singletons exist
    await load_settings(db)
    await load_portfolio(db)
    await seed_owner(db)
    await db.users.create_index("email", unique=True)
    trading_loop.start()
    position_watcher.start()
    research_resolver.start()
    shadow_watcher.start()
    lab_worker.start()
    lab_appender.start()
    # Heavy index builds + first cache compute run OFF the boot path so the backend
    # becomes healthy instantly even on a large production DB (avoids boot-probe timeouts).
    asyncio.create_task(_background_warmup())
    logger.info("Ananta backend started.")


async def _background_warmup():
    """Build performance indexes and warm the research cache asynchronously, after boot."""
    try:
        await db.research_log.create_index("timestamp")
        await db.research_log.create_index([("symbol", 1), ("timestamp", -1)])
        await db.research_log.create_index("rsi_4h")
        await db.research_log.create_index("support_zone")
        await db.trades.create_index([("timestamp", -1)])
        await db.trades.create_index("side")
        await db.reasoning.create_index([("timestamp", -1)])
        await db.reasoning.create_index([("symbol", 1), ("timestamp", -1)])
        await db.stop_loss_simulation_logs.create_index([("timestamp", -1)])
        await db.strategy_sandbox_logs.create_index([("timestamp", -1)])
        # Strategy Lab: query indexes + 30-day TTL so the detection log can't grow unbounded.
        await db.strategy_lab_log.create_index([("strategy", 1), ("detected_at", -1)])
        await db.strategy_lab_log.create_index([("outcome", 1), ("detected_at", 1)])
        await db.strategy_lab_log.create_index("detected_at")
        await db.strategy_lab_log.create_index("created_at", expireAfterSeconds=30 * 24 * 3600)
    except Exception as e:
        logger.warning("Index creation warning (non-fatal): %s", e)
    with contextlib.suppress(Exception):
        await compute_research_cache()
    asyncio.create_task(research_cache_loop())
    # Warm the market-snapshot cache immediately + keep it fresh so /portfolio and
    # /market/snapshots serve from memory (<5ms) instead of blocking on exchange calls.
    with contextlib.suppress(Exception):
        settings = await load_settings(db)
        await warm_snapshots(settings.enabled_symbols)
    asyncio.create_task(_snapshot_warm_loop())


async def _snapshot_warm_loop():
    """Refresh enabled + open-position symbols every few seconds so the API fast path
    always has warm ticker data. Runs off the request path — purely credit-free public data."""
    while True:
        try:
            settings = await load_settings(db)
            portfolio = await load_portfolio(db)
            syms = list({*settings.enabled_symbols, *[p.symbol for p in portfolio.positions]})
            await warm_snapshots(syms)
        except Exception as e:  # noqa: BLE001
            logger.debug("snapshot warm loop tick failed: %s", e)
        await asyncio.sleep(5)


@app.on_event("shutdown")
async def on_shutdown():
    await trading_loop.stop()
    await position_watcher.stop()
    await research_resolver.stop()
    await shadow_watcher.stop()
    await lab_worker.stop()
    await lab_appender.stop()
    client.close()
