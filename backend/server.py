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
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

# ---- env / db ----
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
# Fail fast instead of hanging on the driver's 30s default when Atlas is briefly slow /
# unreachable — a hung Mongo op must never be able to stall the health probe or a request.
client = AsyncIOMotorClient(
    mongo_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    retryWrites=True,
)
db = client[os.environ["DB_NAME"]]

# ---- logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---- imports that depend on env loaded ----
from analytics import compute_performance, graduation_readiness, regime_insight, sector_exposure
import ai_analyst
from auth import authenticate, is_owner_request, require_owner, seed_owner, seed_demo, _valid_owner_payload
import tenancy
from tenant_ctx import OWNER_TENANT, current_tenant, tenant_trade_filter
from backtest import run_for_symbols_async, run_sweep_for_symbols_async
from live_execution import live_status as live_execution_status
from market_data import fetch_snapshot, fetch_snapshots, fetch_snapshots_cached, get_cached_snapshot, warm_snapshots
from models import MarketSnapshot, Portfolio, RiskSettings
import strategy_profiles as sprofiles
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


# ---------- multi-tenant request context ----------
async def tenant_context(request: Request) -> dict:
    """Require ANY authenticated principal (owner/demo JWT or Google session) and
    bind the active tenant for this request so the persistence layer isolates data.
    403 for anonymous public visitors."""
    p = await tenancy.resolve_principal(request, db)
    if not p:
        raise HTTPException(status_code=403, detail="Authentication required.")
    current_tenant.set(p["tenant_id"])
    if p["tenant_id"] != OWNER_TENANT:
        await tenancy.ensure_provisioned(db, p["tenant_id"])
    return p


async def optional_tenant(request: Request) -> dict | None:
    """Bind the tenant for read endpoints: authenticated users see THEIR book;
    anonymous visitors (and owner/demo) fall back to the shared owner/house book."""
    p = await tenancy.resolve_principal(request, db)
    tid = p["tenant_id"] if p else OWNER_TENANT
    current_tenant.set(tid)
    if p and tid != OWNER_TENANT:
        await tenancy.ensure_provisioned(db, tid)
    return p

# background trading loop + faster position watcher
trading_loop = TradingLoop(db, interval_seconds=90)
position_watcher = PositionWatcher(db, default_interval=15)
research_resolver = ResearchResolverLoop(db, interval_seconds=600)
shadow_watcher = ShadowWatcherLoop(db, interval_seconds=30)

# Research Lab: async job queue worker (offline backtests / sweeps / walk-forward)
from lab.runner import HealthSweepScheduler, LabDataAppender, LabWorker, create_run  # noqa: E402

lab_worker = LabWorker(db)
lab_appender = LabDataAppender(db)
health_scheduler = HealthSweepScheduler(db)


# ---------- request/response models ----------
class SettingsUpdate(BaseModel):
    max_spread_pct: float | None = None
    max_daily_loss_pct: float | None = None
    min_confidence: float | None = None
    allowed_regimes: list[str] | None = None
    level_entry_enabled: bool | None = None
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
    profit_protection_enabled: bool | None = None
    structural_stop_enabled: bool | None = None
    ema_trend_loss_enabled: bool | None = None
    structure_failure_enabled: bool | None = None
    strat_exit_enabled: bool | None = None
    exit_method_pref: str | None = None
    fixed_target_pct: float | None = None
    asset_exit_overrides: dict | None = None
    dynamic_trail_enabled: bool | None = None
    profile_overrides: dict | None = None
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
    ask_ananta_enabled: bool | None = None
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


@api_router.get("/health/selfcheck")
async def health_selfcheck():
    """Consolidated, fast, credit-free health probe for the Cockpit first-run self-check.
    One call replaces several: backend, MongoDB (bounded ping), market-data freshness
    (from the in-memory cache, no network), and the trading engine loop status."""
    import market_data as _md  # noqa: PLC0415
    out = {"backend": {"ok": True}, "ts": datetime.now(UTC).isoformat()}

    # MongoDB — bounded ping so a DB stall can't hang the probe.
    t0 = time.time()
    try:
        await asyncio.wait_for(db.command("ping"), timeout=2.0)
        out["database"] = {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 1)}
    except Exception:  # noqa: BLE001
        out["database"] = {"ok": False, "latency_ms": None}

    # Market data — freshness from the warm cache (no exchange call).
    stats = _md.cache_stats()
    fresh = stats["freshest_age_s"] is not None and stats["freshest_age_s"] < 60
    out["market_data"] = {"ok": fresh, **stats}

    # Engine loop status + last activity age (most recent reasoning row as proxy).
    running = trading_loop.is_running
    last_age = None
    try:
        last = await asyncio.wait_for(
            db.reasoning.find({}, {"_id": 0, "timestamp": 1}).sort("timestamp", -1).limit(1).to_list(1),
            timeout=1.5)
        if last and last[0].get("timestamp"):
            dt = datetime.fromisoformat(last[0]["timestamp"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            last_age = round((datetime.now(UTC) - dt).total_seconds(), 0)
    except Exception:  # noqa: BLE001
        last_age = None
    out["engine"] = {"ok": running, "running": running, "last_activity_age_s": last_age}

    out["ok"] = out["backend"]["ok"] and out["database"]["ok"]
    return out


# ---------------------------------------------------------------------------- #
# ACCESS WAITLIST (MVP lead capture). Public visitors can request access to gated
# features; the owner reviews/approves later. Kept intentionally separate from the
# auth layer so we can upgrade to full public accounts later without refactoring.
# ---------------------------------------------------------------------------- #
class AccessRequestReq(BaseModel):
    name: str
    email: str
    feature: str | None = None
    platform: str | None = None


def _valid_email(email: str) -> bool:
    if not email or email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


@api_router.post("/access/request")
async def access_request(body: AccessRequestReq):
    """PUBLIC: capture a Name + Email waitlist lead when a visitor hits a gated feature.
    Idempotent per email (re-submits update the record + bump attempts, never duplicate)."""
    name = (body.name or "").strip()
    email = (body.email or "").strip().lower()
    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email are required.")
    if not _valid_email(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    now = datetime.now(UTC).isoformat()
    existing = await db.access_requests.find_one({"email": email}, {"_id": 0, "status": 1})
    if existing:
        await db.access_requests.update_one(
            {"email": email},
            {"$set": {"name": name, "last_feature": body.feature, "platform": body.platform, "updated_at": now},
             "$inc": {"attempts": 1}})
        return {"ok": True, "status": existing.get("status", "pending"), "already_on_list": True}
    doc = {"id": uuid.uuid4().hex, "name": name, "email": email, "status": "pending",
           "feature": body.feature, "platform": body.platform, "attempts": 1,
           "created_at": now, "updated_at": now}
    await db.access_requests.insert_one({**doc})
    import asyncio as _asyncio  # noqa: PLC0415
    import email_service  # noqa: PLC0415
    _asyncio.create_task(email_service.notify_owner_new_lead(name, email, body.feature, body.platform))
    return {"ok": True, "status": "pending", "already_on_list": False}


@api_router.get("/access/requests", dependencies=[Depends(require_owner)])
async def access_requests_list(status: str | None = Query(None)):
    """OWNER: review captured waitlist leads (newest first)."""
    q = {"status": status} if status else {}
    docs = await db.access_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"requests": docs, "count": len(docs)}


@api_router.post("/access/requests/{rid}/{action}", dependencies=[Depends(require_owner)])
async def access_request_action(rid: str, action: str):
    """OWNER: approve or reject a waitlist lead. (Approval is recorded now; wiring it to a
    real account happens in the future accounts upgrade — the schema is ready.)"""
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be approve or reject")
    status = "approved" if action == "approve" else "rejected"
    lead = await db.access_requests.find_one({"id": rid}, {"_id": 0, "name": 1, "email": 1})
    r = await db.access_requests.update_one(
        {"id": rid}, {"$set": {"status": status, "updated_at": datetime.now(UTC).isoformat()}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="access request not found")
    if lead and lead.get("email"):
        import asyncio as _asyncio  # noqa: PLC0415
        import email_service  # noqa: PLC0415
        _asyncio.create_task(email_service.notify_user_decision(
            lead.get("name", ""), lead["email"], approved=(action == "approve")))
    return {"ok": True, "id": rid, "status": status}



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
async def get_portfolio(_t: dict | None = Depends(optional_tenant)):
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


@api_router.post("/portfolio/reset")
async def portfolio_reset(_t: dict = Depends(tenant_context)):
    fresh = await reset_portfolio(db)
    return {"ok": True, "portfolio": fresh.model_dump()}


class PaperSetup(BaseModel):
    capital: float = 25000.0
    allocation_type: str = "fixed"  # "fixed" (USD per trade) | "percent" (% of portfolio)
    allocation_value: float = 1000.0
    strategies: list[str] = []


@api_router.post("/onboarding/paper-setup")
async def onboarding_paper_setup(cfg: PaperSetup, auth: dict = Depends(tenant_context)):
    """First-run Paper Trading wizard → drives the tenant's paper engine.

    1. Virtual Capital  → fresh paper book at the chosen starting balance.
    2. Per-Trade Allocation → position-sizing settings (fixed USD lot or % of portfolio).
    3. Strategy Selection → enable the chosen strategies for PAPER execution.
    Fully tenant-scoped: each user configures their OWN isolated book + settings."""
    from tenant_ctx import tenant_doc_id  # noqa: PLC0415
    tenant_id = auth["tenant_id"]
    pid = tenant_doc_id(tenant_id)

    # 1. virtual capital → fresh tenant book
    cap = max(100.0, float(cfg.capital))
    fresh = Portfolio(starting_balance=cap, cash=cap, day_start_equity=cap)
    fresh.id = pid
    await db.portfolio.replace_one({"id": pid}, fresh.model_dump(), upsert=True)
    await db.trades.delete_many(tenant_trade_filter(tenant_id))
    await db.pending_orders.delete_many(tenant_trade_filter(tenant_id))

    # 2. per-trade allocation → sizing
    s = await load_settings(db)
    s.trading_mode = "PAPER"
    if cfg.allocation_type == "percent":
        pct = max(0.1, min(100.0, float(cfg.allocation_value)))
        s.adaptive_sizing_enabled = False
        s.position_size_pct_min = pct
        s.position_size_pct_max = pct
    else:
        lot = max(1.0, float(cfg.allocation_value))
        s.adaptive_sizing_enabled = True
        s.normal_lot_usd = lot
        s.strong_lot_usd = lot
        s.breakout_lot_usd = lot

    # 3. strategy selection → per-tenant enable/disable via profile_overrides.
    enabled = []
    selected = {k for k in cfg.strategies if get_schema(k)}
    if selected:
        overrides = dict(s.profile_overrides or {})
        for key in [sch.key for sch in list_schemas()]:
            entry = dict(overrides.get(key.lower()) or {})
            entry["enabled"] = key in selected
            overrides[key.lower()] = entry
            if key in selected:
                enabled.append(key)
        s.profile_overrides = overrides
        # Owner keeps the global strategy_meta lifecycle in sync (house engine).
        if tenant_id == OWNER_TENANT:
            for key in selected:
                await db.strategy_meta.update_one(
                    {"key": key}, {"$set": {"key": key, "enabled": True, "status": "PAPER"}}, upsert=True,
                )
    await save_settings(db, s)

    # Demo / App-Review account → overlay a realistic paper history on the fresh book.
    if auth.get("role") == "demo":
        import demo_seed  # noqa: PLC0415
        await demo_seed.seed_demo_history(db, cap, enable_strategies=False)

    return {"ok": True, "portfolio": fresh.model_dump(), "strategies_enabled": enabled}


@api_router.post("/positions/{base}/close")
async def manual_close_position(base: str, _t: dict = Depends(tenant_context)):
    """Manual Emergency Exit: immediately market-close a single open position in
    the caller's own book. Routes a real sell in LIVE/DRY_RUN, simulates the fill
    in PAPER — the same path the position watcher uses. Tags `exit_reason=MANUAL_EXIT`."""
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


class ManualOrderReq(BaseModel):
    symbol: str                       # base ("BTC") or pair ("BTC/USD")
    side: str                         # BUY | SELL
    order_type: str = "MARKET"        # MARKET | LIMIT
    notional_usd: float | None = None  # BUY sizing (USD to deploy)
    quantity: float | None = None      # explicit units (BUY or SELL)
    limit_price: float | None = None   # required for LIMIT
    fraction: float | None = None      # partial SELL, 0..1 (PAPER)


@api_router.post("/orders/manual")
async def place_manual_order(order: ManualOrderReq, _t: dict = Depends(tenant_context)):
    """Manual order — real paper BUY/SELL (market or limit) against the caller's own
    book; routes a live order in LIVE/DRY_RUN once the exchange gate is armed. Reuses
    the same sizing and execution primitives as the engine so fills/fees/P&L stay consistent."""
    from trading_engine import (
        _execute_buy, _execute_sell, _execute_partial_sell,
        _record_live_buy, _record_live_sell, save_portfolio,
    )
    from position_watcher import _route_executor
    from models import TradeLog, AIReasoning, PendingOrder, compute_return_and_hold

    side = (order.side or "").upper()
    otype = (order.order_type or "MARKET").upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")
    if otype not in ("MARKET", "LIMIT"):
        raise HTTPException(status_code=400, detail="order_type must be MARKET or LIMIT")
    if otype == "LIMIT" and not (order.limit_price and order.limit_price > 0):
        raise HTTPException(status_code=400, detail="limit_price required for LIMIT orders")

    symbol = order.symbol if "/" in order.symbol else f"{order.symbol.upper()}/USD"
    settings = await load_settings(db)
    if symbol not in settings.enabled_symbols:
        raise HTTPException(status_code=400, detail=f"{symbol} is not an enabled symbol")

    snap = await fetch_snapshot(symbol)
    if snap is None:
        raise HTTPException(status_code=503, detail=f"No live price for {symbol}; cannot route order")

    portfolio = await load_portfolio(db)
    executor, trade_mode = await _route_executor(settings)

    reasoning = AIReasoning(
        symbol=symbol, bias="NEUTRAL", confidence=0.0,
        reason=f"Manual {side} order (owner-triggered, {otype})",
        news_summary="(manual order; no AI call)",
        evidence={"source": "owner", "order_type": otype, "manual": True},
        decision=side,
    )
    await db.reasoning.insert_one(reasoning.model_dump())

    if side == "BUY":
        ref_price = order.limit_price if (otype == "LIMIT" and order.limit_price) else snap.ask
        if order.quantity and order.quantity > 0:
            qty = float(order.quantity)
        elif order.notional_usd and order.notional_usd > 0:
            qty = float(order.notional_usd) / ref_price if ref_price > 0 else 0.0
        else:
            raise HTTPException(status_code=400, detail="provide notional_usd or quantity for BUY")
        if qty <= 0:
            raise HTTPException(status_code=400, detail="computed quantity is zero")

        # LIMIT below market → rest a maker order (PAPER path uses the pending-order engine)
        if otype == "LIMIT" and order.limit_price < snap.ask and executor is None:
            pending = PendingOrder(
                symbol=symbol, side="BUY", quantity=qty, limit_price=float(order.limit_price),
                mode="PAPER", reasoning_id=reasoning.id,
            )
            await db.pending_orders.insert_one(pending.model_dump())
            return {"ok": True, "resting": True, "order": pending.model_dump()}

        if executor is not None:
            result = await executor.place_buy(
                symbol=symbol, desired_notional=qty * snap.ask, max_cash=portfolio.cash,
                ask=snap.ask, max_spread_pct=settings.max_spread_pct,
                order_style="POST_ONLY" if otype == "LIMIT" else "MARKET",
            )
            trade_doc = await _record_live_buy(
                db, portfolio, symbol, result, reasoning,
                macro_confidence=0.0, fusion_summary="MANUAL BUY (owner)", mode=trade_mode,
            )
        else:
            fill_price = snap.ask
            notional, fee = _execute_buy(portfolio, symbol, qty, fill_price, settings.taker_fee_pct)
            if notional <= 0:
                raise HTTPException(status_code=409, detail="Order declined — insufficient cash")
            trade = TradeLog(
                symbol=symbol, side="BUY", quantity=qty, price=fill_price, notional=notional,
                mode="PAPER", confidence=0.0, reasoning_id=reasoning.id, fee_usd=fee,
                slippage_usd=0.0, note="MANUAL BUY (owner)", strategy="manual",
            )
            await db.trades.insert_one(trade.model_dump())
            await save_portfolio(db, portfolio)
            trade_doc = trade.model_dump()
        return {"ok": True, "resting": False, "trade": trade_doc}

    # ---- SELL ----
    pos = next((p for p in portfolio.positions if p.symbol == symbol and p.quantity > 0), None)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No open position for {symbol} to sell")
    if otype == "LIMIT" and order.limit_price > snap.bid:
        raise HTTPException(
            status_code=400,
            detail="Resting sell-limit above market isn't supported yet — use Market or a marketable limit.",
        )
    fraction = order.fraction
    if order.quantity and order.quantity > 0:
        fraction = max(0.0, min(1.0, float(order.quantity) / pos.quantity))
    fraction = 1.0 if fraction is None else max(0.0, min(1.0, fraction))
    sell_qty = pos.quantity * fraction

    if executor is not None:
        result = await executor.place_sell(
            symbol=symbol, qty=sell_qty, bid=snap.bid, max_spread_pct=settings.max_spread_pct,
        )
        trade_doc = await _record_live_sell(
            db, portfolio, symbol, result, reasoning,
            macro_confidence=0.0, fusion_summary="MANUAL SELL (owner)",
            mode=trade_mode, exit_reason="MANUAL_ORDER", expected_trigger_price=snap.bid,
        )
    else:
        if fraction >= 1.0:
            qty, notional, realized, fee = _execute_sell(portfolio, symbol, snap.bid, settings.taker_fee_pct)
        else:
            qty, notional, realized, fee = _execute_partial_sell(portfolio, symbol, snap.bid, fraction, settings.taker_fee_pct)
        if qty <= 0:
            raise HTTPException(status_code=409, detail="Sell declined (rounding/empty position)")
        _ret, _hold = compute_return_and_hold(pos.avg_cost, pos.entry_timestamp, snap.bid)
        trade = TradeLog(
            symbol=symbol, side="SELL", quantity=qty, price=snap.bid, notional=notional,
            mode="PAPER", confidence=0.0, reasoning_id=reasoning.id, pnl=realized, fee_usd=fee,
            slippage_usd=0.0, note="MANUAL SELL (owner)", exit_reason="MANUAL_ORDER",
            strategy=pos.strategy, sector=pos.sector, entry_price=pos.avg_cost,
            entry_timestamp=pos.entry_timestamp, return_pct=_ret, hold_seconds=_hold,
            trade_result=("WIN" if realized > 0 else "LOSS" if realized < 0 else "BREAKEVEN"),
        )
        await db.trades.insert_one(trade.model_dump())
        await save_portfolio(db, portfolio)
        trade_doc = trade.model_dump()
    return {"ok": True, "resting": False, "trade": trade_doc}


@api_router.post("/history/clear")
async def clear_history(also_reset_portfolio: bool = False, _t: dict = Depends(tenant_context)):
    """Wipe the caller's own trade history. Optionally reset their portfolio too."""
    trades_del = await db.trades.delete_many(tenant_trade_filter())
    result = {
        "ok": True,
        "trades_deleted": trades_del.deleted_count,
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


@api_router.get("/admin/demo/status")
async def admin_demo_status():
    import demo_seed  # noqa: PLC0415
    return await demo_seed.demo_status(db)


@api_router.post("/admin/demo/load", dependencies=[Depends(require_owner)])
async def admin_demo_load():
    """Owner-only: load the curated Competition Demo Workspace (rich preview data
    across the 3 real strategies) so judges see every screen alive instantly."""
    import demo_seed  # noqa: PLC0415
    out = await demo_seed.load_demo(db)
    global _RESEARCH_CACHE, _RESEARCH_CACHE_TS
    _RESEARCH_CACHE = {}
    _RESEARCH_CACHE_TS = 0.0
    logger.info("Competition Demo loaded by owner: %s", out)
    return {"ok": True, **out}


@api_router.post("/admin/demo/reset", dependencies=[Depends(require_owner)])
async def admin_demo_reset():
    """Owner-only: clear the demo (and any) data back to a clean $1200 paper book."""
    return await admin_fresh_start()



@api_router.get("/trades")
async def get_trades(limit: int = Query(50, le=500), _t: dict | None = Depends(optional_tenant)):
    cursor = db.trades.find(tenant_trade_filter(), {"_id": 0}).sort("timestamp", -1).limit(limit)
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
async def get_cooldowns(_t: dict | None = Depends(optional_tenant)):
    """List active per-symbol cooldown locks (SL/TRAIL) for the caller's book."""
    docs = await db.cooldowns.find(
        {"tenant": current_tenant.get()},
        {"_id": 1, "symbol": 1, "unlock_at": 1, "reason": 1, "started_at": 1},
    ).to_list(50)
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
            "symbol": d.get("symbol") or str(d["_id"]).split(":", 1)[-1],
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
async def risk_status(_t: dict | None = Depends(optional_tenant)):
    settings = await load_settings(db)
    portfolio = await load_portfolio(db)
    # use latest reasoning to estimate macro confidence; fallback to settings.min_confidence
    last = await db.reasoning.find({}, {"_id": 0}).sort("timestamp", -1).limit(1).to_list(1)
    macro_conf = float(last[0]["confidence"]) if last else 0.0
    # Spread kill-switch needs a market snapshot. Serve the warm cache instantly
    # (kept fresh by the background warmer + frequent /market/snapshots polling); only
    # cold-fetch when nothing is cached, bounded by a timeout so an exchange hang can
    # never stall the risk panel. The critical daily-loss + manual kill-switches don't
    # depend on the live spread, so a synthesized fallback stays safe.
    snap = None
    sym = settings.enabled_symbols[0] if settings.enabled_symbols else "BTC/USD"
    snap = get_cached_snapshot(sym)
    if snap is None:
        try:
            snap = await asyncio.wait_for(fetch_snapshot(sym), timeout=1.5)
        except Exception:  # noqa: BLE001
            snap = None
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
async def pending_orders(_t: dict | None = Depends(optional_tenant)):
    """Resting Post-Only maker BUY orders (PAPER) awaiting fill or cancellation."""
    docs = await db.pending_orders.find(tenant_trade_filter(), {"_id": 0}).sort("placed_at", 1).to_list(100)
    return {"items": docs, "count": len(docs)}


@api_router.get("/analytics/performance")
async def analytics_performance(exclude_synthetic: bool = Query(False), _t: dict | None = Depends(optional_tenant)):
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
    tf = tenant_trade_filter()

    rolling_trades = await db.trades.find(
        {"timestamp": {"$gte": rolling_cutoff}, **synthetic_filter, **tf}, {"_id": 0},
    ).sort("timestamp", 1).to_list(800)
    calendar_trades = await db.trades.find(
        {"timestamp": {"$gte": calendar_cutoff}, **synthetic_filter, **tf}, {"_id": 0},
    ).sort("timestamp", 1).to_list(800)

    portfolio = await load_portfolio(db)
    open_positions = [p.model_dump() for p in portfolio.positions if p.quantity > 0]
    exposure = sector_exposure(open_positions)

    # all-time closed trades power the "Best Regime to Trade" insight
    all_sells = await db.trades.find(
        {"side": "SELL", "status": "FILLED", **synthetic_filter, **tf}, {"_id": 0},
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


class AiQuery(BaseModel):
    question: str
    session_id: str | None = None
    strategy: str | None = None


@api_router.post("/analytics/ai_query", dependencies=[Depends(require_owner)])
async def analytics_ai_query(payload: AiQuery):
    """AI Quant Analyst — answers a plain-English question grounded in the app's own
    reasoning log, trade ledger and analytics. Owner-only (consumes LLM credits)."""
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    session_id = payload.session_id or f"analyst-{uuid.uuid4().hex[:12]}"
    try:
        answer = await ai_analyst.answer_question(db, session_id, question, payload.strategy)
    except Exception as e:  # noqa: BLE001
        logger.error("ai_query failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI analyst error: {e}")
    return {"session_id": session_id, "answer": answer}


ANANTA_TAB_CONTEXT = {
    "cockpit": "This tab answers 'What is happening?' — portfolio value, market watchlist, engine status and recent AI decisions.",
    "trade": "This tab answers 'What should I do?' — manual orders, active-strategy toggles, open positions and trade history.",
    "strategy": "This tab answers 'What do I own?' — the strategy library, leaderboard and add/import flows.",
    "research": "This tab answers 'Does it work?' — validation, analytics and closed-trade analysis.",
    "workspace": "This tab answers 'How is my system configured?' — engine, risk, exchange connections and settings.",
}


def _parse_ananta_intents(question: str, schemas) -> list[dict]:
    """Deterministic keyword intent parser → suggested actions the UI renders as
    confirm buttons that call EXISTING endpoints. Never mutates anything itself."""
    ql = question.lower()
    actions: list[dict] = []
    for s in schemas:
        name = (s.name or "").lower()
        key = (s.key or "").lower()
        if not name and not key:
            continue
        if name in ql or (key and key in ql):
            if any(w in ql for w in ["pause", "stop", "disable", "turn off", "halt", "shut"]):
                actions.append({"type": "strategy_disable", "label": f"Pause {s.name}", "params": {"key": s.key}})
            elif any(w in ql for w in ["enable", "resume", "turn on", "activate", "deploy"]):
                actions.append({"type": "strategy_enable", "label": f"Enable {s.name}", "params": {"key": s.key}})
            elif any(w in ql for w in ["research", "validate", "backtest", "test"]):
                actions.append({"type": "open_research", "label": f"Validate {s.name}", "params": {"key": s.key}})
    if any(w in ql for w in ["paper trading", "start paper", "start trading", "begin trading", "trading wizard"]):
        actions.append({"type": "open_wizard", "label": "Open Trading Wizard", "params": {}})
    if "stop loss" in ql or "stop-loss" in ql:
        actions.append({"type": "open_workspace_setting", "label": "Adjust Stop Loss", "params": {"setting": "stop_loss_pct"}})
    if any(w in ql for w in ["add strategy", "import strategy", "build a strategy", "create a strategy"]):
        actions.append({"type": "open_strategy_add", "label": "Add / Import Strategy", "params": {}})
    seen: set = set()
    uniq: list[dict] = []
    for a in actions:
        k = (a["type"], a["params"].get("key") or a["params"].get("setting") or a["type"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(a)
    return uniq[:4]


class AnantaAsk(BaseModel):
    question: str
    session_id: str | None = None
    tab: str | None = None
    strategy: str | None = None


@api_router.post("/ananta/ask", dependencies=[Depends(require_owner)])
async def ananta_ask(payload: AnantaAsk):
    """Ask Ananta — embedded, context-aware trading copilot. Gated by the
    ask_ananta_enabled owner toggle; LLM is only invoked on send. Returns a
    grounded answer plus suggested action buttons (executed by the client
    against existing endpoints, always behind a confirmation)."""
    settings = await load_settings(db)
    if not getattr(settings, "ask_ananta_enabled", False):
        raise HTTPException(status_code=403, detail="Ask Ananta is disabled. Enable it in Workspace.")
    q = (payload.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")
    session_id = payload.session_id or f"ananta-{uuid.uuid4().hex[:12]}"
    tab = (payload.tab or "").lower()
    tab_ctx = ANANTA_TAB_CONTEXT.get(tab, "")
    scoped_q = (f"[Operator is on the {tab.upper()} tab. {tab_ctx}] " if tab_ctx else "") + q
    try:
        answer = await ai_analyst.answer_question(db, session_id, scoped_q, payload.strategy)
    except Exception as e:  # noqa: BLE001
        logger.error("ananta_ask failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Ask Ananta error: {e}")
    actions = _parse_ananta_intents(q, list_schemas())
    return {"session_id": session_id, "answer": answer, "actions": actions, "enabled": True}


class CoachApply(BaseModel):
    setting_key: str
    value: float


class TradesReviewReq(BaseModel):
    mode: str = "paper"


@api_router.post("/coach/trades-review", dependencies=[Depends(require_owner)])
async def coach_trades_review(payload: TradesReviewReq):
    """AI-written review of closed paper or live trades. Owner-only (consumes LLM credits)."""
    import coach  # noqa: PLC0415
    try:
        return await coach.trades_review(db, payload.mode)
    except Exception as e:  # noqa: BLE001
        logger.error("trades review failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI coach error: {e}")


@api_router.get("/coach/headline")
async def coach_headline():
    """Credit-free headline for the Cockpit banner (reads the last stored review)."""
    import coach  # noqa: PLC0415
    return await coach.latest_headline(db)


@api_router.post("/coach/weekly-review", dependencies=[Depends(require_owner)])
async def coach_weekly_review():
    """AI Trading Coach — a proactive 7-day performance review + one applyable tweak.
    Owner-only (consumes LLM credits)."""
    import coach  # noqa: PLC0415
    settings = await load_settings(db)
    try:
        review = await coach.weekly_review(db, settings)
    except Exception as e:  # noqa: BLE001
        logger.error("coach review failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI coach error: {e}")
    return review


@api_router.post("/coach/apply", dependencies=[Depends(require_owner)])
async def coach_apply(payload: CoachApply):
    """Apply a Coach-recommended parameter change (clamped to a safe whitelist)."""
    import coach  # noqa: PLC0415
    try:
        clamped = coach.validate_apply(payload.setting_key, payload.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    settings = await load_settings(db)
    setattr(settings, payload.setting_key, clamped)
    await save_settings(db, settings)
    return {"ok": True, "setting_key": payload.setting_key, "applied_value": clamped}



class MonteCarloRequest(BaseModel):
    source: str = "live"          # "live" (closed trades) | "run" (a lab backtest run)
    run_id: str | None = None
    iterations: int = 2000
    ruin_threshold_pct: float = 25.0
    starting_equity: float | None = None
    exclude_synthetic: bool = True


@api_router.post("/lab/monte_carlo")
async def lab_monte_carlo(req: MonteCarloRequest):
    """Monte Carlo risk-of-ruin: bootstrap thousands of randomised trade-order sequences over
    the realised per-trade P&L and summarise the outcome distribution (risk-of-ruin, prob-profit,
    percentile bands, drawdown distribution). Source = live closed trades, or a lab backtest run."""
    from lab.monte_carlo import run_monte_carlo  # noqa: PLC0415

    pnls: list[float] = []
    if req.source == "run" and req.run_id:
        run = await db.lab_runs.find_one({"id": req.run_id}, {"_id": 0})
        if not run or not run.get("result"):
            raise HTTPException(status_code=404, detail="run not found or has no result")
        for m in (run["result"].get("per_symbol") or {}).values():
            for t in (m.get("trades") or []):
                if t.get("pnl") is not None:
                    pnls.append(float(t["pnl"]))
    else:
        synthetic_filter = {"note": {"$ne": "DEMO_SEED"}} if req.exclude_synthetic else {}
        docs = await db.trades.find(
            {"pnl": {"$ne": None}, **synthetic_filter}, {"_id": 0, "pnl": 1},
        ).sort("timestamp", 1).to_list(2000)
        pnls = [float(d["pnl"]) for d in docs if d.get("pnl") is not None]

    start_eq = req.starting_equity
    if start_eq is None:
        portfolio = await load_portfolio(db)
        start_eq = float(getattr(portfolio, "starting_balance", 1000.0) or 1000.0)

    result = run_monte_carlo(
        pnls, iterations=req.iterations, starting_equity=start_eq,
        ruin_threshold_pct=req.ruin_threshold_pct,
    )
    result["source"] = req.source
    return result




@api_router.get("/analytics/graduation")
async def analytics_graduation(_t: dict | None = Depends(optional_tenant)):
    """Objective 10-gate paper→live graduation scorecard. Proves the system has
    a repeatable edge that survives fees, slippage and different regimes — NOT
    mere profitability. Excludes synthetic DEMO_SEED trades."""
    trades = await db.trades.find(
        {"note": {"$ne": "DEMO_SEED"}, **tenant_trade_filter()}, {"_id": 0},
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
    p = _valid_owner_payload(token) or {}
    return {"token": token, "email": p.get("sub"), "role": p.get("role", "owner")}


class GoogleSessionReq(BaseModel):
    session_id: str


@api_router.post("/auth/google/session")
async def auth_google_session(body: GoogleSessionReq, response: Response):
    """Exchange an Emergent OAuth session_id for a persistent session. Upserts the
    Google user (role='user', own isolated tenant), stores the session, sets the
    httpOnly cookie (web) AND returns the session_token (mobile)."""
    sid = (body.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        out = await tenancy.exchange_session_id(db, sid)
    except Exception as e:  # noqa: BLE001
        logger.warning("google session exchange failed: %s", e)
        raise HTTPException(status_code=401, detail="Google sign-in failed. Please try again.")
    principal, token = out["principal"], out["session_token"]
    # web transport: httpOnly cookie
    response.set_cookie(
        key="session_token", value=token, httponly=True, secure=True,
        samesite="none", path="/", max_age=tenancy.SESSION_TTL_DAYS * 24 * 3600,
    )
    return {
        "session_token": token,  # mobile stores this (Bearer)
        "user": {
            "user_id": principal["user_id"], "email": principal["email"],
            "role": principal["role"], "name": principal.get("name"),
            "picture": principal.get("picture"),
        },
    }


@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    bearer, cookie = tenancy._bearer_and_cookie(request)
    # only delete a session_token (not an owner JWT); owner JWT is stateless.
    for tok in (cookie, bearer):
        if tok and not _valid_owner_payload(tok):
            await tenancy.logout_session(db, tok)
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me")
async def auth_me(request: Request):
    p = await tenancy.resolve_principal(request, db)
    if not p:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "email": p.get("email"), "role": p.get("role"),
        "user_id": p.get("user_id"), "name": p.get("name"),
        "picture": p.get("picture"), "tenant_id": p.get("tenant_id"),
    }


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
async def get_settings(request: Request, _t: dict | None = Depends(optional_tenant)):
    s = await load_settings(db)
    d = s.model_dump()
    # Redact exchange credentials for non-owners (api keys AND secrets).
    if not is_owner_request(request):
        for k in ("coinbase_api_key", "coinbase_api_secret", "kraken_api_key", "kraken_api_secret"):
            if d.get(k):
                d[k] = "•" * 8
    return d


@api_router.put("/settings")
async def update_settings(update: SettingsUpdate, _t: dict = Depends(tenant_context)):
    s = await load_settings(db)
    data = update.model_dump(exclude_unset=True)
    # Drop explicit nulls — Optional update fields use None as "no change". A null must never
    # overwrite a stored value; a null numeric would poison the settings singleton and 500
    # every subsequent read (load_settings / position_watcher / portfolio).
    data = {k: v for k, v in data.items() if v is not None}

    # validate trading_mode
    if "trading_mode" in data and data["trading_mode"] not in ("PAPER", "DRY_RUN", "LIVE"):
        raise HTTPException(status_code=400, detail="trading_mode must be PAPER, DRY_RUN, or LIVE")

    # clamp numeric fields to their hard bounds (single source: settings_spec)
    from settings_spec import clamp_settings_dict  # noqa: PLC0415
    clamp_settings_dict(data)

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


# Curated searchable universe for the Cockpit "Active Watchlist" add flow.
_WATCHLIST_UNIVERSE = [
    ("BTC/USD", "Bitcoin"), ("ETH/USD", "Ethereum"), ("SOL/USD", "Solana"), ("XRP/USD", "Ripple"),
    ("ADA/USD", "Cardano"), ("AVAX/USD", "Avalanche"), ("LINK/USD", "Chainlink"), ("AAVE/USD", "Aave"),
    ("ARB/USD", "Arbitrum"), ("RENDER/USD", "Render"), ("PAXG/USD", "PAX Gold"), ("DOGE/USD", "Dogecoin"),
    ("MATIC/USD", "Polygon"), ("DOT/USD", "Polkadot"), ("LTC/USD", "Litecoin"), ("ATOM/USD", "Cosmos"),
    ("UNI/USD", "Uniswap"), ("NEAR/USD", "NEAR Protocol"), ("OP/USD", "Optimism"), ("INJ/USD", "Injective"),
    ("APT/USD", "Aptos"), ("SUI/USD", "Sui"), ("FIL/USD", "Filecoin"), ("ETC/USD", "Ethereum Classic"),
    ("BCH/USD", "Bitcoin Cash"), ("ALGO/USD", "Algorand"), ("XLM/USD", "Stellar"), ("TIA/USD", "Celestia"),
]


def _norm_symbol(raw: str) -> str:
    raw = (raw or "").strip().upper()
    return raw if "/" in raw else f"{raw}/USD"


@api_router.get("/watchlist/search")
async def watchlist_search(q: str = Query("")):
    """Search the crypto universe to add to the Active Watchlist (excludes already-added)."""
    s = await load_settings(db)
    current = set(s.enabled_symbols or [])
    ql = q.strip().lower()
    out = [{"symbol": sym, "name": name} for sym, name in _WATCHLIST_UNIVERSE
           if sym not in current and (not ql or ql in sym.lower() or ql in name.lower())]
    return {"results": out[:20], "count": len(out)}


@api_router.post("/watchlist/add", dependencies=[Depends(require_owner)])
async def watchlist_add(payload: dict):
    """Add a crypto to the Active Watchlist. Validates it is tradable, then the bot begins
    tracking it (it also appears on the Trade page)."""
    symbol = _norm_symbol(payload.get("symbol", ""))
    if not symbol or "/" not in symbol:
        raise HTTPException(status_code=422, detail="symbol required, e.g. DOGE or DOGE/USD")
    s = await load_settings(db)
    current = list(s.enabled_symbols or [])
    if symbol in current:
        return {"ok": True, "enabled_symbols": current, "note": "already in watchlist"}
    snap = await fetch_snapshot(symbol)
    if not snap:
        raise HTTPException(status_code=400, detail=f"{symbol} is not tradable / price unavailable")
    current.append(symbol)
    s.enabled_symbols = current
    saved = await save_settings(db, s)
    return {"ok": True, "symbol": symbol, "enabled_symbols": saved.enabled_symbols, "count": len(saved.enabled_symbols)}


@api_router.post("/watchlist/remove", dependencies=[Depends(require_owner)])
async def watchlist_remove(payload: dict):
    symbol = _norm_symbol(payload.get("symbol", ""))
    s = await load_settings(db)
    current = list(s.enabled_symbols or [])
    if symbol not in current:
        raise HTTPException(status_code=404, detail="symbol not in watchlist")
    if len(current) <= 1:
        raise HTTPException(status_code=400, detail="watchlist must keep at least one asset")
    current.remove(symbol)
    s.enabled_symbols = current
    saved = await save_settings(db, s)
    return {"ok": True, "symbol": symbol, "enabled_symbols": saved.enabled_symbols, "count": len(saved.enabled_symbols)}




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



class PromoWaitlistReq(BaseModel):
    email: str | None = None
    feature: str = "coming-soon"


@api_router.get("/promo/coming-soon")
async def promo_coming_soon_get():
    """Promo state for the 'Coming Soon to Ananta' banner. View-count/dismiss are tracked
    client-side (per-device UX nudge); the backend only persists the waitlist opt-in."""
    doc = await db.promo_state.find_one({"key": "coming-soon"}, {"_id": 0}) or {}
    return {"waitlist_joined": bool(doc.get("waitlist_joined")), "joined_at": doc.get("joined_at")}


@api_router.post("/promo/coming-soon/waitlist")
async def promo_coming_soon_waitlist(req: PromoWaitlistReq):
    await db.promo_state.update_one(
        {"key": "coming-soon"},
        {"$set": {"key": "coming-soon", "waitlist_joined": True,
                  "joined_at": datetime.now(UTC).isoformat(), "email": req.email}},
        upsert=True)
    logger.info("Promo waitlist opt-in recorded (coming-soon)")
    return {"waitlist_joined": True}


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
    mode: str | None = Query(None, description="Filter by book: 'paper' | 'live' | 'all'"),
    inline: bool = Query(False, description="Open in-browser instead of downloading"),
):
    """Unified Trade-History export: a clean, chronological printout of EXECUTED
    (FILLED) trades, optionally filtered to a date range and a paper/live book."""
    from pdf_report import build_trades_report

    query: dict = {"status": {"$in": ["FILLED", None]}}
    ts_filter: dict = {}
    if start:
        ts_filter["$gte"] = f"{start}T00:00:00+00:00"
    if end:
        ts_filter["$lte"] = f"{end}T23:59:59.999999+00:00"
    if ts_filter:
        query["timestamp"] = ts_filter
    m = (mode or "all").lower()
    if m == "paper":
        query["mode"] = {"$in": ["PAPER", "DRY_RUN"]}
    elif m == "live":
        query["mode"] = "LIVE"

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
    suffix = f"{m}_{start or 'all'}_{end or 'now'}"
    filename = f"ananta-trades-{suffix}.pdf"
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
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
    strategies: list[str] | None = None  # subset of hunter|squeeze|continuation (None = all)
    timeframe: str = "1h"  # primary execution timeframe: 1h (default) | 30m | 15m
    compare_timeframes: bool = False  # off = 1h-only (fast); on = add 30m/15m comparison
    exit_method: str = "fixed"  # "native" (Universal Engine) | "atr" (pure ATR) | "fixed" ($ target)
    target_profit: float = 5.0  # fixed-exit take-profit ($, net)
    target_loss: float = 4.0  # fixed-exit stop-loss ($, net)
    atr_params: dict | None = None  # atr-exit: {multiplier, period, trail_activation_pct, trail_distance}
    use_live_exit_settings: bool = False  # replay via the deployed Exit Engine config (method + per-strategy/per-coin overrides)


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


class HealthSweepRequest(BaseModel):
    scope: str = "full"          # "full" = all strategies | "scoped" = core + enabled
    period: str = "3m"           # 3m | 6m | 1y


async def _active_health_sweep():
    """The sweep to surface: a RUNNING one takes precedence over a QUEUED one."""
    proj = {"_id": 0, "id": 1, "status": 1, "progress_pct": 1, "label": 1}
    return (await db.lab_runs.find_one({"kind": "health_sweep", "status": "RUNNING"}, proj,
                                       sort=[("created_at", -1)])
            or await db.lab_runs.find_one({"kind": "health_sweep", "status": "QUEUED"}, proj,
                                          sort=[("created_at", 1)]))


@api_router.get("/lab/health")
async def lab_health_latest():
    """Latest pre-computed Strategy Health snapshot (fast read for the dashboard).
    Read-only / public — returns {ready:false} until the first sweep completes."""
    doc = await db.strategy_health.find_one({"id": "latest"}, {"_id": 0})
    if not doc:
        return {"ready": False, "active": await _active_health_sweep()}
    return {"ready": True, "active": await _active_health_sweep(), **doc}


@api_router.get("/lab/health/status")
async def lab_health_status():
    """Poll the in-flight sweep (if any) — {active|null}. Read-only."""
    return {"active": await _active_health_sweep()}


@api_router.post("/lab/health/run", dependencies=[Depends(require_owner)])
async def lab_health_run(body: HealthSweepRequest):
    """Manually trigger a full / scoped Strategy Health sweep (runs in the background)."""
    from lab.runner import daily_scope_strategies, enqueue_health_sweep
    from strategy.core import list_schemas
    existing = await db.lab_runs.find_one(
        {"kind": "health_sweep", "status": {"$in": ["QUEUED", "RUNNING"]}}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="a Strategy Health sweep is already running")
    if body.period not in ("3m", "6m", "1y"):
        raise HTTPException(status_code=400, detail="period must be 3m, 6m or 1y")
    if body.scope == "scoped":
        strategies = await daily_scope_strategies(db)
    else:
        strategies = [s.key for s in list_schemas()]
    doc = await enqueue_health_sweep(db, strategies=strategies, period=body.period, mode="manual")
    return {"id": doc["id"], "status": doc["status"], "strategy_count": len(strategies)}



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


class ConsolidatedReportReq(BaseModel):
    run_ids: list[str]
    period_label: str | None = None


@api_router.post("/lab/reports/consolidated", dependencies=[Depends(require_owner)])
async def lab_consolidated_report(body: ConsolidatedReportReq):
    """Render one side-by-side comparison PDF from several completed single-strategy backtest runs."""
    if not body.run_ids:
        raise HTTPException(status_code=400, detail="run_ids required")
    runs = await db.lab_runs.find({"id": {"$in": body.run_ids}}, {"_id": 0}).to_list(length=len(body.run_ids))
    done = [r for r in runs if r.get("status") == "DONE" and r.get("result")]
    if not done:
        raise HTTPException(status_code=409, detail="no completed runs among run_ids")
    # Preserve the caller's ordering.
    order = {rid: i for i, rid in enumerate(body.run_ids)}
    done.sort(key=lambda r: order.get(r["id"], 999))
    syms = done[0].get("symbols") or []
    from lab.lab_report import build_multi_strategy_report
    pdf_bytes = build_multi_strategy_report(done, symbols=syms, period_label=body.period_label)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="ananta_consolidated_strategies.pdf"'})


class DeployExitConfigReq(BaseModel):
    strategy: str  # hunter | squeeze | continuation
    method: str = "fixed_pct"  # fixed_pct | atr_trailing | chandelier | native
    target_pct: float | None = None  # fixed_pct take-profit %
    stop_pct: float | None = None    # fixed_pct / trailing hard stop %
    trail_arm: float | None = None   # atr/chandelier trail arm %
    trail_dist: float | None = None  # atr/chandelier trail distance %
    set_paper_active: bool = True    # also enable the strategy for PAPER trading


@api_router.post("/lab/deploy-exit-config", dependencies=[Depends(require_owner)])
async def lab_deploy_exit_config(body: DeployExitConfigReq):
    """One-click: deploy a per-strategy exit config to the live (paper) engine — writes the
    profile_overrides entry the Exit Engine uses, so a winning Lab config skips the manual step."""
    valid_strats = {"hunter", "squeeze", "continuation"}
    if body.strategy not in valid_strats:
        raise HTTPException(status_code=400, detail=f"strategy must be one of {sorted(valid_strats)}")
    valid_methods = {"fixed_pct", "atr_trailing", "chandelier", "native"}
    if body.method not in valid_methods:
        raise HTTPException(status_code=400, detail=f"method must be one of {sorted(valid_methods)}")

    s = await load_settings(db)
    overrides = dict(getattr(s, "profile_overrides", {}) or {})
    if body.method == "native":
        # "native" == no per-strategy exit override; drop any existing one for this strategy.
        overrides.pop(body.strategy, None)
    else:
        entry = dict(overrides.get(body.strategy) or {})
        entry["method"] = body.method
        if body.method == "fixed_pct":
            if body.target_pct is not None:
                entry["target_pct"] = float(body.target_pct)
            if body.stop_pct is not None:
                entry["stop_pct"] = float(body.stop_pct)
        else:  # atr_trailing / chandelier
            if body.trail_arm is not None:
                entry["trail_arm"] = float(body.trail_arm)
            if body.trail_dist is not None:
                entry["trail_dist"] = float(body.trail_dist)
            if body.stop_pct is not None:
                entry["stop_pct"] = float(body.stop_pct)
        overrides[body.strategy] = entry
    s.profile_overrides = overrides
    saved = await save_settings(db, s)

    if body.set_paper_active:
        await db.strategy_meta.update_one(
            {"key": body.strategy},
            {"$set": {"key": body.strategy, "enabled": True, "status": "PAPER"}}, upsert=True)

    return {"ok": True, "strategy": body.strategy,
            "profile_overrides": saved.profile_overrides,
            "paper_active": body.set_paper_active}


# Fields never included in a portable config bundle: secrets + safety flags + metadata.
# This keeps import idempotent-safe: it can NEVER flip live/paper, trip the kill-switch,
# or leak/overwrite exchange API keys across environments.
_CONFIG_BUNDLE_EXCLUDE = {
    "id", "updated_at", "trading_mode", "manual_kill_switch",
    "coinbase_api_key", "coinbase_api_secret", "kraken_api_key", "kraken_api_secret",
}
_BUNDLE_STRATS = ["hunter", "squeeze", "continuation"]


@api_router.get("/settings/config-bundle", dependencies=[Depends(require_owner)])
async def export_config_bundle():
    """Export the portable trading-config bundle (settings + strategy toggles) for copying
    between environments. Excludes secrets, trading_mode and the kill-switch."""
    s = await load_settings(db)
    raw = s.model_dump()
    settings_out = {k: v for k, v in raw.items() if k not in _CONFIG_BUNDLE_EXCLUDE}
    states = []
    for key in _BUNDLE_STRATS:
        m = await db.strategy_meta.find_one({"key": key}, {"_id": 0, "key": 1, "enabled": 1, "status": 1})
        if m:
            states.append({"key": key, "enabled": m.get("enabled", True), "status": m.get("status", "PAPER")})
    return {"kind": "ananta_config_bundle", "version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "settings": settings_out, "strategy_states": states}


class ConfigBundleIn(BaseModel):
    kind: str | None = None
    version: int | None = None
    settings: dict = {}
    strategy_states: list[dict] = []


@api_router.post("/settings/config-bundle", dependencies=[Depends(require_owner)])
async def import_config_bundle(bundle: ConfigBundleIn):
    """Apply a config bundle exported from another environment. Silently drops any excluded
    keys (secrets / trading_mode / kill-switch) so it can never change safety-critical state."""
    if bundle.kind and bundle.kind != "ananta_config_bundle":
        raise HTTPException(status_code=400, detail="not an ananta_config_bundle")
    s = await load_settings(db)
    applied = []
    valid = set(RiskSettings.model_fields.keys())
    for k, v in (bundle.settings or {}).items():
        if k in _CONFIG_BUNDLE_EXCLUDE or k not in valid:
            continue
        setattr(s, k, v)
        applied.append(k)
    saved = await save_settings(db, s)
    states_applied = []
    for st in (bundle.strategy_states or []):
        key = st.get("key")
        if key not in _BUNDLE_STRATS:
            continue
        await db.strategy_meta.update_one(
            {"key": key},
            {"$set": {"key": key, "enabled": bool(st.get("enabled", True)),
                      "status": st.get("status", "PAPER")}}, upsert=True)
        states_applied.append(key)
    return {"ok": True, "settings_applied": applied, "strategy_states_applied": states_applied,
            "allowed_regimes": saved.allowed_regimes, "normal_lot_usd": saved.normal_lot_usd,
            "profile_overrides": saved.profile_overrides,
            "note": "trading_mode, kill-switch and exchange keys are intentionally NOT changed by import."}




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


# ============================================================================ #
# PLATFORM PHASE 1 — Strategy Registry + Parameter Schema + Strategy Configs
# ---------------------------------------------------------------------------- #
# OWNERSHIP: this `strategy_configs` collection is a DESIGN & VERSIONING layer
# (Architect-authored, sparse overrides with inheritance + validation + rating).
# It is NOT the live source of truth and is NOT read by the trading engine yet.
# The engine reads ONLY RiskSettings (see settings_spec.py + CONFIG_ARCHITECTURE.md).
#
# PHASE 2 MIGRATION PATH (kept compatible on purpose): to make per-strategy configs
# drive the engine, resolve each active config (resolve_config: schema defaults <-
# parent chain <- self) and merge the resolved params into the RiskSettings passed
# to the engine per strategy — RiskSettings stays the read interface, so no engine
# module needs to change. Until then these endpoints are purely additive.
# ============================================================================ #
from strategy import (  # noqa: E402
    StrategyConfig,
    engine_backed_params,
    get_schema,
    list_schemas,
    now_iso as _strat_now_iso,
    resolve_config,
    validate_params,
)

_OWNER_TENANT = "owner"  # single-tenant today; every row is already tenant-scoped for the future.


def _health_breakdown(ts: list[dict], win_rate: float, roi: float, trades: int, stars: int) -> list[dict]:
    """Transparent sub-scores behind the single Health number — each 0-100 so the
    Strategy Center can render 'why' cards (win rate / risk / consistency / form / …)."""
    import statistics  # noqa: PLC0415

    recent = ts[-10:]
    rwins = sum(1 for t in recent if (t.get("pnl") or 0) > 0)
    recent_wr = round(100 * rwins / len(recent), 0) if recent else 0.0

    rets = [t.get("return_pct") for t in ts if t.get("return_pct") is not None]
    consistency = None
    if len(rets) >= 3:
        mean = statistics.mean(rets)
        sd = statistics.pstdev(rets)
        cv = abs(sd / mean) if mean else 999.0
        consistency = round(max(0.0, min(100.0, 100.0 - cv * 20.0)), 0)

    risk_adj = round(max(0.0, min(100.0, 50.0 + roi * 2.0)), 0)
    sample = round(min(100.0, trades * 5.0), 0)
    rating_score = round(min(100.0, stars * 20.0), 0)

    comps = [
        {"key": "win_rate", "label": "Win Rate", "score": round(min(100.0, win_rate), 0),
         "detail": f"{win_rate}% of trades profitable"},
        {"key": "risk", "label": "Risk-Adjusted", "score": risk_adj, "detail": f"ROI {roi}%"},
        {"key": "recent", "label": "Recent Form", "score": recent_wr,
         "detail": f"last {len(recent)} trades" if recent else "no recent trades"},
        {"key": "sample", "label": "Sample Confidence", "score": sample, "detail": f"{trades} closed trades"},
        {"key": "rating", "label": "Owner Rating", "score": rating_score, "detail": f"{stars}/5 stars"},
    ]
    if consistency is not None:
        comps.insert(3, {"key": "consistency", "label": "Consistency", "score": consistency,
                         "detail": "per-trade return stability"})
    return comps


def _strategy_timeline(schema, cfgs: list[dict], ts: list[dict], status: str) -> list[dict]:
    """Lifecycle milestones (Created → Optimized → Validated → Paper → Live → Latest)
    derived from configs, the validation gate and the live trade ledger."""
    created_at = None
    if cfgs:
        created_at = min((c.get("created_at") for c in cfgs if c.get("created_at")), default=None)
    events = [{"key": "created", "label": "Created", "ts": created_at, "done": True,
               "detail": f"{getattr(schema, 'name', 'Strategy')} registered"}]
    if cfgs:
        latest = max(cfgs, key=lambda c: c.get("updated_at") or "")
        events.append({"key": "optimized", "label": "Last Optimized", "ts": latest.get("updated_at"),
                       "done": True, "detail": f"{len(cfgs)} saved config(s)"})
        validated = any((c.get("validation_status") == "passed") for c in cfgs)
        events.append({"key": "validated", "label": "Validation Passed", "ts": None, "done": validated,
                       "detail": "Walk-forward / backtest gate" if validated else "Not yet validated"})
    else:
        events.append({"key": "validated", "label": "Validation Passed", "ts": None, "done": False,
                       "detail": "Run a backtest in the Research Lab"})
    if ts:
        events.append({"key": "paper", "label": "First Paper Trade", "ts": ts[0].get("timestamp"),
                       "done": True, "detail": "Paper-traded live"})
    else:
        events.append({"key": "paper", "label": "First Paper Trade", "ts": None, "done": False,
                       "detail": "Awaiting first entry"})
    events.append({"key": "live", "label": "Live Trading", "ts": None, "done": status == "LIVE",
                   "detail": "Deployed to live" if status == "LIVE" else "Not deployed live"})
    if ts:
        events.append({"key": "last_trade", "label": "Latest Trade", "ts": ts[-1].get("timestamp"),
                       "done": True, "detail": f"{len(ts)} trades total"})
    return events


async def _compute_strategy_metrics() -> dict:
    """Derive per-strategy live metrics from the closed-trade ledger + config ratings + state."""
    portfolio = await load_portfolio(db)
    start_eq = float(getattr(portfolio, "starting_balance", 1000.0) or 1000.0)
    trades = await db.trades.find(
        {"pnl": {"$ne": None}, "note": {"$ne": "DEMO_SEED"}},
        {"_id": 0, "strategy": 1, "pnl": 1, "return_pct": 1, "timestamp": 1},
    ).sort("timestamp", 1).to_list(4000)
    configs = await db.strategy_configs.find(
        {"tenant_id": _OWNER_TENANT},
        {"_id": 0, "strategy_key": 1, "rating": 1, "created_at": 1, "updated_at": 1, "validation_status": 1},
    ).to_list(1000)
    meta = {m["key"]: m for m in await db.strategy_meta.find({}, {"_id": 0}).to_list(200)}

    by_strat: dict[str, list[dict]] = {}
    for t in trades:
        by_strat.setdefault(t.get("strategy") or "unknown", []).append(t)
    stars_by: dict[str, int] = {}
    for c in configs:
        s = (c.get("rating") or {}).get("stars") or 0
        stars_by[c["strategy_key"]] = max(stars_by.get(c["strategy_key"], 0), int(s))

    out = {}
    for schema in list_schemas():
        key = schema.key
        ts = by_strat.get(key, [])
        n = len(ts)
        wins = sum(1 for t in ts if (t.get("pnl") or 0) > 0)
        total_pnl = round(sum((t.get("pnl") or 0) for t in ts), 2)
        win_rate = round(100 * wins / n, 1) if n else 0.0
        roi = round(100 * total_pnl / start_eq, 2) if start_eq else 0.0
        # profit factor + max drawdown + recent form, derived from this strategy's trade ledger
        gross_p = sum((t.get("pnl") or 0) for t in ts if (t.get("pnl") or 0) > 0)
        gross_l = abs(sum((t.get("pnl") or 0) for t in ts if (t.get("pnl") or 0) < 0))
        profit_factor = (round(gross_p / gross_l, 2) if gross_l > 0 else (999.0 if gross_p > 0 else None))
        eq, peak, max_dd = start_eq, start_eq, 0.0
        for t in ts:
            eq += (t.get("pnl") or 0)
            peak = max(peak, eq)
            if peak > 0:
                max_dd = max(max_dd, (peak - eq) / peak * 100.0)
        max_drawdown_pct = round(max_dd, 2) if n else 0.0
        recent = ts[-8:]
        recent_form = ["W" if (t.get("pnl") or 0) > 0 else "L" for t in recent]
        recent_form_pct = round(100 * sum(1 for f in recent_form if f == "W") / len(recent_form), 0) if recent_form else 0.0
        stars = stars_by.get(key, 0)
        last_ts = ts[-1]["timestamp"] if ts else None
        m = meta.get(key, {})
        status = m.get("status", "PAPER")
        cfgs = [c for c in configs if c["strategy_key"] == key]
        breakdown = _health_breakdown(ts, win_rate, roi, n, stars)
        health = int(round(sum(c["score"] for c in breakdown) / len(breakdown))) if breakdown else 0
        out[key] = {
            "key": key, "name": schema.name, "category": (schema.dna or {}).get("family") if isinstance(schema.dna, dict) else None,
            "status": status, "enabled": m.get("enabled", True),
            "trades": n, "win_rate": win_rate, "roi": roi, "total_pnl": total_pnl,
            "profit_factor": profit_factor, "max_drawdown_pct": max_drawdown_pct,
            "recent_form": recent_form, "recent_form_pct": recent_form_pct,
            "stars": stars, "confidence": min(99, int(win_rate)) if n else 0,
            "health": health,
            "health_breakdown": breakdown,
            "timeline": _strategy_timeline(schema, cfgs, ts, status),
            "last_trade": last_ts, "config_count": len(cfgs),
            "active_config_id": m.get("active_config_id"),
            "active_config_name": m.get("active_config_name"),
            "deployed_at": m.get("deployed_at") or m.get("updated_at") or m.get("created_at"),
        }
    return out


@api_router.get("/strategy/metrics")
async def strategy_metrics():
    """Live scoreboard for every built-in strategy — powers the Strategy Center cards."""
    return {"metrics": await _compute_strategy_metrics()}


class StrategyState(BaseModel):
    status: str | None = None
    enabled: bool | None = None


@api_router.put("/strategy/{key}/state", dependencies=[Depends(require_owner)])
async def strategy_set_state(key: str, payload: StrategyState):
    if not get_schema(key):
        raise HTTPException(status_code=404, detail=f"strategy '{key}' not found")
    valid = {"LIVE", "PAPER", "DISABLED", "TESTING", "OPTIMIZING", "ERROR"}
    updates: dict = {}
    if payload.status is not None:
        if payload.status not in valid:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(valid)}")
        updates["status"] = payload.status
    if payload.enabled is not None:
        updates["enabled"] = payload.enabled
    if not updates:
        raise HTTPException(status_code=400, detail="no state fields provided")

    # Enforce the enabled↔status invariant so the two can't drift out of sync:
    #  - DISABLED/ERROR status ⇒ not enabled
    #  - enabling while status is off ⇒ promote to PAPER
    current = await db.strategy_meta.find_one({"key": key}, {"_id": 0}) or {}
    merged = {**current, **updates}
    status = merged.get("status", "PAPER")
    enabled = merged.get("enabled", False)
    # promote first: enabling a currently-off strategy (without an explicit status) ⇒ PAPER
    if payload.enabled and payload.status is None and status in ("DISABLED", "ERROR"):
        status = "PAPER"
    # then clamp: an off status can never be enabled
    if status in ("DISABLED", "ERROR"):
        enabled = False
    updates["status"] = status
    updates["enabled"] = enabled

    await db.strategy_meta.update_one({"key": key}, {"$set": {"key": key, **updates}}, upsert=True)
    doc = await db.strategy_meta.find_one({"key": key}, {"_id": 0})
    return doc


# ---------------------------------------------------------------------------
# Strategy Profile — the per-strategy identity (allowed regimes + default exit) applied
# identically across Live, Paper and the Research Lab. Stored in settings.profile_overrides.
# ---------------------------------------------------------------------------
class StrategyProfileIn(BaseModel):
    enabled: bool = True
    allowed_regimes: list[str] = []
    exit_method: str = "native"
    exit_params: dict = {}


def _current_profile(settings, key: str) -> dict | None:
    ov = getattr(settings, "profile_overrides", None) or {}
    raw = ov.get(key) or ov.get(key.lower())
    if not raw:
        return None
    # Only treat it as a configured profile when it actually carries profile fields.
    if not any(k in raw for k in ("enabled", "allowed_regimes", "exit_method", "exit_params")):
        return None
    return sprofiles.normalize_profile(raw)


@api_router.get("/strategy/{key}/profile")
async def get_strategy_profile(key: str):
    """Effective Strategy Profile + the shipped recommendation + selectable regimes/exit methods."""
    if not get_schema(key):
        raise HTTPException(status_code=404, detail=f"strategy '{key}' not found")
    s = await load_settings(db)
    current = _current_profile(s, key)
    eff = current or {"enabled": True, "allowed_regimes": [], "exit_method": "native",
                      "exit_params": {}, "source": "default"}
    return {"key": key, "profile": eff, "configured": current is not None,
            "recommended": sprofiles.recommended_profile(key),
            "regimes": sprofiles.REGIMES, "exit_methods": sprofiles.EXIT_METHODS,
            "status": sprofiles.profile_status(current)}


def _write_profile(ov: dict, key: str, prof: dict) -> dict:
    """Merge a normalized profile into profile_overrides[key], preserving any existing
    exit-engine field patches (structural_stop_enabled, trail_arm_r, …) already stored there."""
    existing = dict(ov.get(key) or {})
    existing.update(prof)
    ov = dict(ov)
    ov.pop(key.lower(), None)
    ov[key] = existing
    return ov


@api_router.put("/strategy/{key}/profile", dependencies=[Depends(require_owner)])
async def put_strategy_profile(key: str, body: StrategyProfileIn):
    if not get_schema(key):
        raise HTTPException(status_code=404, detail=f"strategy '{key}' not found")
    prof = sprofiles.normalize_profile(body.model_dump())
    s = await load_settings(db)
    s.profile_overrides = _write_profile(dict(getattr(s, "profile_overrides", {}) or {}), key, prof)
    await save_settings(db, s)
    return {"ok": True, "key": key, "profile": prof, "status": sprofiles.profile_status(prof)}


@api_router.post("/strategy/{key}/profile/apply-recommended", dependencies=[Depends(require_owner)])
async def apply_recommended_profile(key: str):
    rec = sprofiles.recommended_profile(key)
    if not rec:
        raise HTTPException(status_code=404, detail=f"no recommended profile for '{key}'")
    prof = sprofiles.normalize_profile(rec)
    s = await load_settings(db)
    s.profile_overrides = _write_profile(dict(getattr(s, "profile_overrides", {}) or {}), key, prof)
    await save_settings(db, s)
    return {"ok": True, "key": key, "profile": prof, "status": sprofiles.profile_status(prof)}


@api_router.post("/strategy/{key}/profile/reset", dependencies=[Depends(require_owner)])
async def reset_strategy_profile(key: str):
    """Clear the user's profile so the strategy reverts to defaults (trades all regimes, native exit)."""
    s = await load_settings(db)
    ov = dict(getattr(s, "profile_overrides", {}) or {})
    ov.pop(key, None)
    ov.pop(key.lower(), None)
    s.profile_overrides = ov
    await save_settings(db, s)
    return {"ok": True, "key": key, "profile": None, "status": sprofiles.profile_status(None)}




@api_router.get("/strategy/registry")
async def strategy_registry():
    """All built-in strategies with their DNA + full parameter schema (latest version each)."""
    return {"strategies": [s.model_dump() for s in list_schemas()]}


@api_router.get("/strategy/{key}/schema")
async def strategy_schema_endpoint(key: str, version: str | None = Query(None)):
    s = get_schema(key, version)
    if not s:
        raise HTTPException(status_code=404, detail=f"strategy '{key}' not found")
    return s.model_dump()


class ArchitectChat(BaseModel):
    message: str
    session_id: str | None = None
    history: list[dict] = []


@api_router.post("/strategy/architect/chat", dependencies=[Depends(require_owner)])
async def strategy_architect_chat(payload: ArchitectChat):
    """AI Strategy Architect turn — interviews the user and finally emits a validated,
    deployable strategy design. Owner-only (consumes LLM credits)."""
    import architect  # noqa: PLC0415
    msg = (payload.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message is required")
    session_id = payload.session_id or f"architect-{uuid.uuid4().hex[:12]}"
    try:
        data = await architect.architect_reply(session_id, payload.history or [], msg)
    except Exception as e:  # noqa: BLE001
        logger.error("architect chat failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Architect error: {e}")
    return {"session_id": session_id, **data}



@api_router.get("/strategy/configs")
async def strategy_list_configs(strategy_key: str | None = Query(None)):
    q: dict = {"tenant_id": _OWNER_TENANT}
    if strategy_key:
        q["strategy_key"] = strategy_key
    rows = await db.strategy_configs.find(q, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return {"configs": rows}


@api_router.get("/strategy/configs/{config_id}")
async def strategy_get_config(config_id: str):
    row = await db.strategy_configs.find_one({"id": config_id, "tenant_id": _OWNER_TENANT}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="config not found")
    all_rows = await db.strategy_configs.find({"tenant_id": _OWNER_TENANT}, {"_id": 0}).to_list(2000)
    by_id = {r["id"]: r for r in all_rows}
    schema = get_schema(row["strategy_key"], row.get("strategy_version"))
    return {"config": row, "resolved_params": resolve_config(row, by_id, schema)}


@api_router.post("/strategy/configs", dependencies=[Depends(require_owner)])
async def strategy_create_config(payload: dict):
    key = payload.get("strategy_key")
    schema = get_schema(key, payload.get("strategy_version"))
    if not schema:
        raise HTTPException(status_code=400, detail=f"unknown strategy '{key}'")
    params = payload.get("params") or {}
    ok, errs = validate_params(schema, params)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errs})
    parent_id = payload.get("parent_config_id")
    if parent_id and not await db.strategy_configs.find_one({"id": parent_id, "tenant_id": _OWNER_TENANT}):
        raise HTTPException(status_code=400, detail="parent_config_id not found")
    cfg = StrategyConfig(
        tenant_id=_OWNER_TENANT, strategy_key=key, strategy_version=schema.version,
        name=(payload.get("name") or f"{schema.name} config"),
        params=params, parent_config_id=parent_id, origin=payload.get("origin", "user"),
        meta=payload.get("meta") or {},
    )
    await db.strategy_configs.insert_one(cfg.model_dump())
    return {"config": cfg.model_dump()}


@api_router.put("/strategy/configs/{config_id}", dependencies=[Depends(require_owner)])
async def strategy_update_config(config_id: str, payload: dict):
    row = await db.strategy_configs.find_one({"id": config_id, "tenant_id": _OWNER_TENANT})
    if not row:
        raise HTTPException(status_code=404, detail="config not found")
    schema = get_schema(row["strategy_key"], row.get("strategy_version"))
    updates: dict = {}
    if "params" in payload:
        ok, errs = validate_params(schema, payload["params"] or {})
        if not ok:
            raise HTTPException(status_code=422, detail={"errors": errs})
        updates["params"] = payload["params"] or {}
    for f in ("name", "parent_config_id", "rating", "validation_status"):
        if f in payload:
            updates[f] = payload[f]
    if not updates:
        raise HTTPException(status_code=400, detail="no updatable fields provided")
    updates["updated_at"] = _strat_now_iso()
    await db.strategy_configs.update_one({"id": config_id}, {"$set": updates})
    return {"config": await db.strategy_configs.find_one({"id": config_id}, {"_id": 0})}


@api_router.delete("/strategy/configs/{config_id}", dependencies=[Depends(require_owner)])
async def strategy_delete_config(config_id: str):
    row = await db.strategy_configs.find_one({"id": config_id, "tenant_id": _OWNER_TENANT})
    if not row:
        raise HTTPException(status_code=404, detail="config not found")
    if row.get("origin") == "builtin":
        raise HTTPException(status_code=400, detail="cannot delete a built-in default config")
    children = await db.strategy_configs.count_documents(
        {"tenant_id": _OWNER_TENANT, "parent_config_id": config_id})
    if children:
        raise HTTPException(status_code=400, detail=f"config has {children} child config(s); delete those first")
    await db.strategy_configs.delete_one({"id": config_id})
    return {"deleted": config_id}


@api_router.post("/strategy/seed-defaults", dependencies=[Depends(require_owner)])
async def strategy_seed_defaults():
    """Create one 'Default' built-in config per strategy (idempotent) — the root of every inheritance chain."""
    created: list[str] = []
    for s in list_schemas():
        exists = await db.strategy_configs.find_one(
            {"tenant_id": _OWNER_TENANT, "strategy_key": s.key, "origin": "builtin"})
        if exists:
            continue
        cfg = StrategyConfig(
            tenant_id=_OWNER_TENANT, strategy_key=s.key, strategy_version=s.version,
            name=f"{s.name} · Default", params={}, origin="builtin", validation_status="passed",
        )
        await db.strategy_configs.insert_one(cfg.model_dump())
        created.append(cfg.id)
    return {"created": created, "count": len(created)}


def _stars_from_metrics(m: dict) -> int:
    """Rough 1-5 institutional star rating from a config's headline metrics."""
    pf = m.get("profit_factor") or 0.0
    dd = abs(m.get("max_drawdown_pct") or 0.0)
    ret = m.get("total_return_pct") or 0.0
    score = 0
    score += 2 if pf >= 1.8 else 1 if pf >= 1.2 else 0
    score += 1 if ret > 0 else 0
    score += 2 if dd <= 5 else 1 if dd <= 12 else 0
    return max(1, min(5, score))


@api_router.post("/strategy/configs/from-lab-run", dependencies=[Depends(require_owner)])
async def strategy_config_from_lab_run(payload: dict):
    """Bridge: promote the winning exit engine from a Research Lab exit-comparison into a saved
    StrategyConfig (origin='optimizer') — turns research findings into a reusable, rateable config."""
    from lab.backtest import EXIT_COMPARISON_CONFIGS  # noqa: PLC0415

    run_id = payload.get("run_id")
    key = payload.get("strategy_key")
    schema = get_schema(key, payload.get("strategy_version"))
    if not schema:
        raise HTTPException(status_code=400, detail=f"unknown strategy '{key}'")
    run = await db.lab_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="lab run not found")
    ec = ((run.get("result") or {}).get("exit_comparison")) or {}
    if not ec:
        raise HTTPException(status_code=400, detail="run has no exit_comparison (re-run to generate one)")
    symbol = payload.get("symbol") or next(iter(ec), None)
    by_tf = ec.get(symbol) or {}
    timeframe = payload.get("timeframe") or ("1h" if "1h" in by_tf else next(iter(by_tf), None))
    block = by_tf.get(timeframe) or {}
    winner_key = block.get("winner_key")
    if not winner_key:
        raise HTTPException(status_code=400, detail=f"no winning config for {symbol} · {timeframe}")

    cfg_def = next((c for c in EXIT_COMPARISON_CONFIGS if c["key"] == winner_key), None)
    if not cfg_def:
        raise HTTPException(status_code=400, detail=f"unknown exit config '{winner_key}'")
    params: dict = {"exit_method": cfg_def["exit_method"]}
    if cfg_def["exit_method"] == "fixed":
        params["target_profit"] = float(cfg_def.get("target_profit", 5.0))
        params["target_loss"] = float(cfg_def.get("target_loss", 4.0))
    elif cfg_def["exit_method"] == "atr":
        params["atr_multiplier"] = float((cfg_def.get("atr_params") or {}).get("multiplier", 2.5))

    ok, errs = validate_params(schema, params)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errs})

    metrics = (block.get("rows") or {}).get(winner_key) or {}
    rating = {
        "stars": _stars_from_metrics(metrics),
        "profit_factor": metrics.get("profit_factor"),
        "win_rate_pct": metrics.get("win_rate_pct"),
        "total_return_pct": metrics.get("total_return_pct"),
        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
        "recommended": True,
        "source": f"lab_run:{run_id}",
    }
    cfg = StrategyConfig(
        tenant_id=_OWNER_TENANT, strategy_key=key, strategy_version=schema.version,
        name=(payload.get("name") or f"{schema.name} · {cfg_def['label']} ({symbol} {timeframe})"),
        params=params, origin="optimizer", rating=rating,
    )
    await db.strategy_configs.insert_one(cfg.model_dump())
    return {"config": cfg.model_dump(), "source": {"run_id": run_id, "symbol": symbol,
            "timeframe": timeframe, "winner_key": winner_key}}


# ---------------------------------------------------------------------------- #
# PHASE 2 — activate / import / export a strategy config.
# ACTIVATION is the one compatible bridge from a StrategyConfig to the live engine:
# it resolves the config, keeps only engine-backed params, and writes them into the
# RiskSettings singleton (clamped via settings_spec). The engine still reads ONLY
# RiskSettings — see CONFIG_ARCHITECTURE.md. No activation ⇒ behaviour is unchanged.
# ---------------------------------------------------------------------------- #
def _config_export_blob(row: dict) -> dict:
    return {
        "ananta_config": 1,
        "strategy_key": row.get("strategy_key"),
        "strategy_version": row.get("strategy_version"),
        "name": row.get("name"),
        "params": row.get("params") or {},
        "origin": row.get("origin"),
        "meta": row.get("meta") or {},
    }


@api_router.get("/strategy/configs/{config_id}/export")
async def strategy_export_config(config_id: str):
    """Portable JSON for a config — copy it to share or re-import elsewhere."""
    row = await db.strategy_configs.find_one({"id": config_id, "tenant_id": _OWNER_TENANT}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="config not found")
    return _config_export_blob(row)


@api_router.post("/strategy/configs/import", dependencies=[Depends(require_owner)])
async def strategy_import_config(payload: dict):
    """Import a strategy as STRUCTURED JSON (schema-validated). No code execution.

    Accepts either a flat body `{strategy_key, name, params, parent_config_id?}` or an
    exported blob `{ananta_config, strategy_key, params, ...}`. Params are validated
    against the strategy schema, so an import can never introduce unknown/out-of-range
    knobs. Stored as a normal versioned config with origin='imported'.
    """
    blob = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    key = blob.get("strategy_key")
    schema = get_schema(key, blob.get("strategy_version"))
    if not schema:
        raise HTTPException(status_code=400, detail=f"unknown strategy '{key}'")
    params = blob.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(status_code=422, detail={"errors": ["'params' must be an object"]})
    ok, errs = validate_params(schema, params)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errs})
    parent_id = blob.get("parent_config_id")
    if parent_id and not await db.strategy_configs.find_one({"id": parent_id, "tenant_id": _OWNER_TENANT}):
        raise HTTPException(status_code=400, detail="parent_config_id not found")
    cfg = StrategyConfig(
        tenant_id=_OWNER_TENANT, strategy_key=key, strategy_version=schema.version,
        name=(blob.get("name") or f"{schema.name} · imported"),
        params=params, parent_config_id=parent_id, origin="imported",
        meta={**(blob.get("meta") or {}), "imported_at": _strat_now_iso()},
    )
    await db.strategy_configs.insert_one(cfg.model_dump())
    return {"config": cfg.model_dump(), "resolved_params": resolve_config(cfg.model_dump(), {}, schema)}


@api_router.post("/strategy/configs/{config_id}/activate", dependencies=[Depends(require_owner)])
async def strategy_activate_config(config_id: str):
    """Make a config the ACTIVE config for its strategy (P3 per-strategy resolution).

    Resolves the config (defaults ← parent chain ← self) and keeps only engine-backed,
    strategy-level params. Records the active config on strategy_meta; the live/paper
    engine then resolves these params per strategy at evaluation time (strategy_runtime),
    WITHOUT touching the global account-level RiskSettings. Requires a validated config.
    """
    from strategy_runtime import ACCOUNT_LEVEL_FIELDS  # noqa: PLC0415
    from settings_spec import clamp_value  # noqa: PLC0415

    row = await db.strategy_configs.find_one({"id": config_id, "tenant_id": _OWNER_TENANT}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="config not found")
    if row.get("validation_status") != "passed":
        raise HTTPException(status_code=400, detail="config must pass validation before activation")

    key = row["strategy_key"]
    schema = get_schema(key, row.get("strategy_version"))
    all_rows = await db.strategy_configs.find({"tenant_id": _OWNER_TENANT}, {"_id": 0}).to_list(2000)
    by_id = {r["id"]: r for r in all_rows}
    resolved = resolve_config(row, by_id, schema)
    engine_params = engine_backed_params(schema, resolved)

    # Split: strategy-level params drive THIS strategy; account-level ones are ignored
    # (they stay owned by the global RiskSettings). Report both so the UI is transparent.
    applied = {f: clamp_value(f, v) for f, v in engine_params.items()
               if f not in ACCOUNT_LEVEL_FIELDS and v is not None}
    ignored = [f for f in engine_params if f in ACCOUNT_LEVEL_FIELDS]

    await db.strategy_meta.update_one(
        {"key": key},
        {"$set": {"key": key, "active_config_id": config_id,
                  "active_config_name": row.get("name"),
                  "activated_at": _strat_now_iso()}},
        upsert=True,
    )
    return {"activated": config_id, "strategy_key": key, "applied": len(applied),
            "applied_params": applied, "ignored_account_level": ignored,
            "note": "This strategy now trades on its own config params (per-strategy). "
                    "Account-level risk stays global; account-level fields in the config are ignored."}


@api_router.post("/strategy/{key}/deactivate", dependencies=[Depends(require_owner)])
async def strategy_deactivate_config(key: str):
    """Clear a strategy's active config → it reverts to the global RiskSettings baseline."""
    await db.strategy_meta.update_one(
        {"key": key},
        {"$set": {"active_config_id": None, "active_config_name": None,
                  "deactivated_at": _strat_now_iso()}},
        upsert=True,
    )
    return {"deactivated": key}


@api_router.get("/strategy/{key}/effective")
async def strategy_effective_params(key: str):
    """The params the live/paper engine is actually using for this strategy right now:
    global RiskSettings baseline overlaid with its active config (if any)."""
    from strategy_runtime import resolve_active_params  # noqa: PLC0415
    cfg = await resolve_active_params(db)
    meta = await db.strategy_meta.find_one({"key": key}, {"_id": 0}) or {}
    return {"strategy_key": key,
            "active_config_id": meta.get("active_config_id"),
            "active_config_name": meta.get("active_config_name"),
            "overrides": cfg.get(key, {}),
            "using_config": bool(cfg.get(key))}


@api_router.get("/analytics/leaderboard")
async def analytics_leaderboard(sort: str = Query("health"), source: str = Query("all")):
    """Ranked strategy scoreboard with a selectable sort metric (Part 12).

    Ranks over the Strategy Library (which carries full seeded metrics) overlaid with
    the real live metrics for the internal engine strategies. `sort` picks the metric;
    `source` = all | live | library.
    """
    live = await _compute_strategy_metrics()
    lib = await db.strategy_library.find({}, {"_id": 0}).to_list(500)

    rows: list[dict] = []
    for s in lib:
        hist = s.get("historical_results") or {}
        internal = bool(s.get("internal"))
        lm = live.get(s.get("engine_key")) if internal else None
        row = {
            "key": s["id"], "name": s["name"], "source": s.get("source"),
            "internal": internal, "style": s.get("style"),
            "status": (lm or {}).get("status") if lm else "CATALOG",
            "roi": (lm or {}).get("roi", hist.get("roi", 0)),
            "win_rate": (lm or {}).get("win_rate", hist.get("win_rate", 0)),
            "net_pnl": (lm or {}).get("total_pnl", 0) if lm else hist.get("roi", 0),
            "trades": (lm or {}).get("trades", hist.get("trade_count", 0)),
            "health": (lm or {}).get("health", s.get("ai_health_score", 0)),
            "ai_health_score": s.get("ai_health_score", 0),
            "ai_grade": s.get("ai_grade"),
            "profit_factor": hist.get("profit_factor", 0),
            "sharpe": hist.get("sharpe", 0),
            "sortino": hist.get("sortino", 0),
            "max_drawdown": hist.get("max_drawdown", 0),
            "avg_trade": hist.get("avg_trade", 0),
            "rating": s.get("rating", 0),
            "active_config_id": (lm or {}).get("active_config_id") if lm else None,
        }
        rows.append(row)

    if source == "live":
        rows = [r for r in rows if r["internal"]]
    elif source == "library":
        rows = [r for r in rows if not r["internal"]]

    ascending = {"max_drawdown"}
    key = sort if sort in {"net_pnl", "roi", "win_rate", "health", "ai_health_score", "sharpe",
                           "sortino", "profit_factor", "max_drawdown", "avg_trade", "trades", "rating"} else "health"
    rows.sort(key=lambda r: r.get(key, 0) or 0, reverse=key not in ascending)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return {"leaderboard": rows, "count": len(rows), "sort": key, "source": source,
            "sort_options": ["net_pnl", "roi", "win_rate", "ai_health_score", "sharpe", "sortino",
                             "profit_factor", "max_drawdown", "avg_trade", "trades", "rating"]}


# ---------------------------------------------------------------------------- #
# STRATEGY LIBRARY (P1) — curated catalog with rich metadata, seeded results and
# AI grading. Public read; owner-only mutations. See library_seed.py.
# ---------------------------------------------------------------------------- #
async def _seed_library_if_empty():
    if await db.strategy_library.count_documents({}) == 0:
        from library_seed import library  # noqa: PLC0415
        await db.strategy_library.insert_many(library())


async def _purge_orphan_import_drafts(ttl_hours: int = 48):
    """TTL cleanup for the `strategy_imports` collection: delete abandoned import drafts
    (never approved) older than ttl_hours so orphan / non-compilable AI extractions can't
    bloat the DB. Approved drafts (already copied into strategy_library) are always kept.
    created_at is stored as a UTC ISO string, so lexicographic `$lt` == chronological."""
    cutoff = (datetime.now(UTC) - timedelta(hours=ttl_hours)).isoformat()
    r = await db.strategy_imports.delete_many(
        {"status": {"$ne": "approved"}, "created_at": {"$lt": cutoff}})
    if r.deleted_count:
        logger.info("Purged %d orphan import draft(s) older than %dh.", r.deleted_count, ttl_hours)



async def _bootstrap_declarative():
    """Idempotent Phase B bootstrap: (1) seed strategy_meta for each wireable declarative
    strategy so only the default-enabled batch trades (others start DISABLED); owner
    changes are preserved. (2) backfill engine_key/wireable on existing library docs."""
    from strategy.declarative_defs import DECLARATIVE  # noqa: PLC0415
    from library_seed import REFERENCE_ONLY, WIRED_ENGINE_KEYS  # noqa: PLC0415
    for key, d in DECLARATIVE.items():
        existing = await db.strategy_meta.find_one({"key": key}, {"_id": 1})
        if not existing:
            await db.strategy_meta.update_one(
                {"key": key},
                {"$set": {"key": key, "status": "PAPER" if d.get("default_enabled") else "DISABLED",
                          "enabled": bool(d.get("default_enabled")), "active_config_id": None}},
                upsert=True)
    for lib_id, ekey in WIRED_ENGINE_KEYS.items():
        await db.strategy_library.update_one(
            {"id": lib_id}, {"$set": {"engine_key": ekey, "wireable": True}})
    for lib_id, note in REFERENCE_ONLY.items():
        await db.strategy_library.update_one(
            {"id": lib_id}, {"$set": {"reference_only": True, "reference_note": note}})

    # (3) rehydrate IMPORTED declarative strategies into the runtime registry (P2).
    from strategy.declarative_defs import register_imported  # noqa: PLC0415
    cursor = db.strategy_library.find(
        {"imported": True, "wireable": True, "declarative_spec": {"$exists": True}}, {"_id": 0})
    async for d in cursor:
        ekey = d.get("engine_key")
        spec = d.get("declarative_spec")
        if ekey and spec and (spec.get("entry")):
            register_imported(ekey, d.get("name") or ekey, d.get("description") or "",
                              spec, d.get("engine_params") or {})


@api_router.post("/library/seed", dependencies=[Depends(require_owner)])
async def library_seed_endpoint(force: bool = Query(False)):
    from library_seed import library  # noqa: PLC0415
    if force:
        await db.strategy_library.delete_many({})
    if await db.strategy_library.count_documents({}) == 0:
        docs = library()
        await db.strategy_library.insert_many(docs)
        return {"seeded": len(docs)}
    return {"seeded": 0, "note": "library already populated (use force=true to reseed)"}


@api_router.get("/library/facets")
async def library_facets():
    """Available filter options for the Strategy Center filter drawer."""
    docs = await db.strategy_library.find({}, {"_id": 0}).to_list(500)
    regimes, styles, mtypes, tfs, risks, grades, sources = (set() for _ in range(7))
    for d in docs:
        regimes.update(d.get("market_regimes") or [])
        styles.add(d.get("style"))
        mtypes.update(d.get("market_type") or [])
        tfs.update(d.get("timeframes") or [])
        risks.add(d.get("risk"))
        grades.add(d.get("ai_grade"))
        sources.add(d.get("source"))
    def _s(x):
        return sorted(v for v in x if v)
    return {"market_regime": _s(regimes), "style": _s(styles), "market_type": _s(mtypes),
            "timeframe": _s(tfs), "risk": _s(risks), "ai_grade": _s(grades), "source": _s(sources)}


@api_router.get("/library")
async def library_list(
    market_regime: str | None = Query(None), market_type: str | None = Query(None),
    style: str | None = Query(None), timeframe: str | None = Query(None),
    risk: str | None = Query(None), ai_grade: str | None = Query(None),
    source: str | None = Query(None), favorite: bool | None = Query(None),
    min_health: int | None = Query(None), chip: str | None = Query(None),
    sort: str = Query("health"), q: str | None = Query(None),
):
    """List library strategies with multi-select filters + quick chips + sort.
    Comma-separated values are OR'd within a field; fields are AND'd together."""
    docs = await db.strategy_library.find({}, {"_id": 0}).to_list(500)

    def _multi(val, field, list_field=False):
        nonlocal docs
        if not val:
            return
        wanted = {v.strip() for v in val.split(",") if v.strip()}
        if list_field:
            docs = [d for d in docs if wanted & set(d.get(field) or [])]
        else:
            docs = [d for d in docs if d.get(field) in wanted]

    _multi(market_regime, "market_regimes", list_field=True)
    _multi(market_type, "market_type", list_field=True)
    _multi(timeframe, "timeframes", list_field=True)
    _multi(style, "style")
    _multi(risk, "risk")
    _multi(ai_grade, "ai_grade")
    _multi(source, "source")
    if favorite:
        docs = [d for d in docs if d.get("favorite")]
    if min_health is not None:
        docs = [d for d in docs if (d.get("ai_health_score") or 0) >= min_health]
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in (d.get("name", "") + " " + d.get("description", "")).lower()]

    # quick chips
    if chip == "top_rated":
        docs.sort(key=lambda d: (d.get("rating", 0), d.get("ai_health_score", 0)), reverse=True)
    elif chip == "top_internal":
        docs = [d for d in docs if d.get("internal")]
        docs.sort(key=lambda d: d.get("ai_health_score", 0), reverse=True)
    elif chip == "healthiest":
        docs.sort(key=lambda d: d.get("ai_health_score", 0), reverse=True)
    elif chip == "trending":
        docs.sort(key=lambda d: (d.get("historical_results") or {}).get("roi", 0), reverse=True)
    else:
        skey = {"health": lambda d: d.get("ai_health_score", 0),
                "rating": lambda d: d.get("rating", 0),
                "roi": lambda d: (d.get("historical_results") or {}).get("roi", 0),
                "win_rate": lambda d: (d.get("historical_results") or {}).get("win_rate", 0)}.get(sort)
        if skey:
            docs.sort(key=skey, reverse=True)

    return {"strategies": docs, "count": len(docs)}


# ---------------------------------------------------------------------------- #
# STRATEGY IMPORT PIPELINE (P2) — import Pine Script / Freqtrade / Jesse / JSON,
# AI-extract into Ananta's schema, validate + report, review/edit, then approve
# into the Strategy Library. Owner-only mutations. See strategy_import.py.
# NOTE: these specific routes MUST be declared before GET /library/{strategy_id}
# so "/library/imports" is not captured by the {strategy_id} path param.
# ---------------------------------------------------------------------------- #
class ImportAnalyzeReq(BaseModel):
    raw_content: str
    source_format: str = "auto"   # auto | pine_script | freqtrade | jesse | json
    name: str | None = None


class ImportDraftUpdate(BaseModel):
    patch: dict


@api_router.get("/library/import/formats")
async def import_formats():
    """Supported frameworks for the import UI dropdown."""
    import strategy_import  # noqa: PLC0415
    return {"formats": strategy_import.SUPPORTED_FORMATS}


@api_router.post("/library/import/detect")
async def import_detect(payload: ImportAnalyzeReq):
    """Cheap, credit-free format auto-detection (no AI)."""
    import strategy_import  # noqa: PLC0415
    return strategy_import.detect_format(payload.raw_content)


@api_router.post("/library/import/analyze", dependencies=[Depends(require_owner)])
async def import_analyze(payload: ImportAnalyzeReq):
    """AI-extract a strategy from raw source, validate, and persist a review draft.
    Consumes LLM credits. Returns the full draft (conversion report + validation)."""
    import strategy_import  # noqa: PLC0415
    import import_ai  # noqa: PLC0415

    raw = (payload.raw_content or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="raw_content is required")

    detected = strategy_import.detect_format(raw)
    fmt = payload.source_format if payload.source_format and payload.source_format != "auto" else detected["best"]
    if fmt not in strategy_import.ADAPTERS:
        fmt = detected["best"]

    try:
        extraction = await import_ai.analyze_strategy(
            raw, fmt, strategy_import.ai_hint_for(fmt), name_hint=payload.name)
    except Exception as e:  # noqa: BLE001
        logger.error("import analyze failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI extraction error: {e}")

    try:
        draft = strategy_import.build_draft(
            raw_source=raw, source_format=fmt, detected=detected,
            extraction=extraction, name_override=payload.name)
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("import build_draft failed on malformed extraction: %s", e)
        raise HTTPException(status_code=422,
            detail="The AI extraction was malformed and could not be structured. Try again or paste cleaner source.") from e
    await db.strategy_imports.insert_one({**draft})
    draft.pop("_id", None)
    return draft


@api_router.post("/library/import/direct", dependencies=[Depends(require_owner)])
async def import_direct(payload: ImportAnalyzeReq):
    """Save an imported strategy WITHOUT any AI analysis (consumes no LLM credits). For JSON the
    parsed object is used directly as the extraction; other formats get a minimal editable draft.
    Unblocks users with no credits. (Executable-in-engine support is P2.)"""
    import strategy_import  # noqa: PLC0415
    import json as _json  # noqa: PLC0415

    raw = (payload.raw_content or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="raw_content is required")
    detected = strategy_import.detect_format(raw)
    fmt = payload.source_format if payload.source_format and payload.source_format != "auto" else detected["best"]
    if fmt not in strategy_import.ADAPTERS:
        fmt = detected["best"]

    extraction: dict = {}
    if fmt == "json":
        try:
            parsed = _json.loads(raw)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422,
                detail="Invalid JSON — fix the syntax or use Analyze with AI.") from e
        if isinstance(parsed, dict):
            extraction = parsed
            # Power-user path: if the JSON already carries an engine-compatible rule spec at the
            # top level ({indicators:{...}, entry:[...], exit:[...]} in Ananta's declarative format),
            # lift it into the declarative block so the strategy compiles to the engine WITHOUT AI —
            # making it deployable + Research/Lab-runnable, not just a view-only blueprint.
            if ("declarative" not in extraction
                    and isinstance(extraction.get("indicators"), dict)
                    and isinstance(extraction.get("entry"), list)):
                _entry = extraction.get("entry")
                _exit = extraction.get("exit") if isinstance(extraction.get("exit"), list) else []
                _ind = extraction.get("indicators")
                extraction["declarative"] = {
                    "compilable": True,
                    "params": extraction.get("params") or extraction.get("parameters") or {},
                    "indicators": _ind,
                    "entry": _entry,
                    "exit": _exit,
                    "entry_reason": extraction.get("entry_reason") or "Imported strategy entry",
                }
                # Present indicators as the library's display list ({name, params}) instead of the
                # declarative {id: {fn, ...}} map, so the strategy card renders cleanly.
                extraction["indicators"] = [
                    {"name": (v.get("fn") or k), "params": {p: val for p, val in v.items() if p != "fn"}}
                    for k, v in _ind.items() if isinstance(v, dict)
                ]

                # Human-readable rule bullets so the draft passes review-validation (which
                # requires at least one entry rule) and reads clearly in the library.
                def _bullets(conds):
                    out = []
                    for c in conds or []:
                        if isinstance(c, dict) and c.get("lhs") is not None:
                            rhs = c.get("rhs")
                            out.append(f"{c['lhs']} {str(c.get('op', '')).replace('_', ' ')}"
                                       + (f" {rhs}" if rhs is not None else ""))
                    return out
                if not extraction.get("entry_rules"):
                    extraction["entry_rules"] = _bullets(_entry)
                if not extraction.get("exit_rules"):
                    extraction["exit_rules"] = _bullets(_exit)
    if not isinstance(extraction, dict):
        extraction = {}
    extraction.setdefault("ai_summary", "Imported without AI analysis.")
    extraction.setdefault("conversion", {
        "notes": "Saved directly without AI conversion — rules were not auto-validated to the engine.",
        "confidence_score": 0})

    try:
        draft = strategy_import.build_draft(
            raw_source=raw, source_format=fmt, detected=detected,
            extraction=extraction, name_override=payload.name)
    except Exception as e:  # noqa: BLE001 — never surface a raw 500 for user-pasted content
        logger.warning("import_direct build_draft failed: %s", e)
        raise HTTPException(status_code=422, detail=(
            "This definition could not be structured into a strategy. For a free-form idea, use "
            "'Analyze with AI'. For a no-AI import, paste valid JSON (optionally with an Ananta "
            "declarative rule block to make it executable).")) from e
    draft["ai_skipped"] = True
    try:
        await db.strategy_imports.insert_one({**draft})
    except Exception as e:  # noqa: BLE001
        logger.error("import_direct insert failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not save the draft. Please try again.") from e
    draft.pop("_id", None)
    return draft


@api_router.get("/library/imports", dependencies=[Depends(require_owner)])
async def import_list():
    """List saved import drafts (most recent first)."""
    docs = await db.strategy_imports.find({}, {"_id": 0, "raw_source": 0}).sort("created_at", -1).to_list(100)
    return {"drafts": docs, "count": len(docs)}


@api_router.get("/library/imports/{draft_id}", dependencies=[Depends(require_owner)])
async def import_get(draft_id: str):
    doc = await db.strategy_imports.find_one({"id": draft_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="import draft not found")
    return doc


@api_router.put("/library/imports/{draft_id}", dependencies=[Depends(require_owner)])
async def import_update(draft_id: str, payload: ImportDraftUpdate):
    """Apply user edits to a draft. Re-runs deterministic validation on the new fields."""
    import strategy_import  # noqa: PLC0415
    doc = await db.strategy_imports.find_one({"id": draft_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="import draft not found")
    patch = payload.patch or {}
    # only allow editable, library-shaped + a few metadata fields
    editable = set(strategy_import.LIBRARY_FIELDS) | {
        "volatility_preference", "expected_holding_period", "strengths", "weaknesses", "tags",
        "position_sizing", "conversion_report"}
    editable.discard("id")
    clean = {k: v for k, v in patch.items() if k in editable}
    doc.update(clean)
    doc["validation"] = strategy_import.validate_extraction(doc)
    doc["updated_at"] = _strat_now_iso()
    await db.strategy_imports.update_one({"id": draft_id}, {"$set": {**{k: doc[k] for k in clean},
        "validation": doc["validation"], "updated_at": doc["updated_at"]}})
    return doc


@api_router.delete("/library/imports/{draft_id}", dependencies=[Depends(require_owner)])
async def import_delete(draft_id: str):
    r = await db.strategy_imports.delete_one({"id": draft_id})
    if not r.deleted_count:
        raise HTTPException(status_code=404, detail="import draft not found")
    return {"deleted": draft_id}


@api_router.post("/library/imports/{draft_id}/approve", dependencies=[Depends(require_owner)])
async def import_approve(draft_id: str):
    """Finalise a reviewed draft into the Strategy Library. Blocked if validation has errors."""
    import strategy_import  # noqa: PLC0415
    doc = await db.strategy_imports.find_one({"id": draft_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="import draft not found")
    validation = strategy_import.validate_extraction(doc)
    if validation.get("error_count"):
        raise HTTPException(status_code=422,
            detail="Cannot approve: unresolved errors — " +
                   "; ".join(i["message"] for i in validation["issues"] if i["severity"] == "error"))
    lib_doc = strategy_import.to_library_doc(doc)
    if await db.strategy_library.find_one({"id": lib_doc["id"]}, {"_id": 1}):
        lib_doc["id"] = f"{lib_doc['id']}-{uuid.uuid4().hex[:4]}"

    # P2: if the import compiled to the declarative engine, wire it as an executable strategy.
    if doc.get("declarable") and (doc.get("declarative_spec") or {}).get("entry"):
        from strategy.declarative_defs import register_imported  # noqa: PLC0415
        ekey = lib_doc["id"]
        lib_doc["engine_key"] = ekey
        lib_doc["wireable"] = True
        lib_doc["declarative_spec"] = doc["declarative_spec"]
        lib_doc["engine_params"] = doc.get("engine_params") or {}
        register_imported(ekey, lib_doc["name"], lib_doc.get("description") or "",
                           doc["declarative_spec"], doc.get("engine_params") or {})

    await db.strategy_library.insert_one({**lib_doc})
    await db.strategy_imports.update_one({"id": draft_id},
        {"$set": {"status": "approved", "approved_library_id": lib_doc["id"], "updated_at": _strat_now_iso()}})
    lib_doc.pop("_id", None)
    return {"approved": True, "library_id": lib_doc["id"], "strategy": lib_doc}


@api_router.post("/library/imports/{draft_id}/backtest-preview", dependencies=[Depends(require_owner)])
async def import_backtest_preview(draft_id: str, symbol: str | None = None, days: int = 30, exchange: str = "kraken"):
    """P2: prove an imported strategy is executable BEFORE approval — replay its compiled
    declarative spec over real historical OHLCV. Fails clearly if the import did not compile.
    When `symbol` is omitted, infer a sensible crypto pair from the draft (Ananta is spot-crypto)."""
    import asyncio  # noqa: PLC0415
    from declarative_backtest import run_declarative_backtest  # noqa: PLC0415
    from declarative_engine import validate_spec  # noqa: PLC0415
    from backtest import fetch_history  # noqa: PLC0415

    doc = await db.strategy_imports.find_one({"id": draft_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="import draft not found")
    spec = doc.get("declarative_spec") or {}
    v = validate_spec(spec)
    if not (doc.get("declarable") and v["ok"] and spec.get("entry")):
        raise HTTPException(status_code=422,
            detail="This import did not compile to executable rules: " + "; ".join(v["issues"] or [doc.get("declarative_reason") or "not compilable"]))

    settings = await load_settings(db)
    enabled = settings.enabled_symbols or ["BTC/USD"]
    note = None
    if not symbol:
        # infer from the draft's preferred coins, else fall back to a liquid enabled pair
        cands = doc.get("preferred_coins") or doc.get("symbols") or []
        pick = next((c for c in cands if isinstance(c, str) and "/" in c and c in enabled), None)
        if not pick:
            pick = next((c for c in cands if isinstance(c, str) and "/" in c), None)
        symbol = pick or ("BTC/USD" if "BTC/USD" in enabled else enabled[0])
        mkt = doc.get("market_type") or []
        if mkt and not any("crypto" in str(m).lower() for m in mkt):
            note = f"Ananta is spot-crypto only — backtested on {symbol} as a proxy for a {', '.join(mkt)} strategy."
    params = dict(doc.get("engine_params") or {})
    days = max(7, min(90, days))
    try:
        candles = await asyncio.to_thread(fetch_history, symbol, days, "1h", exchange)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"could not fetch history: {e}") from e
    if len(candles) < 60:
        raise HTTPException(status_code=422, detail="insufficient historical data for a backtest")
    metrics = await asyncio.to_thread(run_declarative_backtest, spec, candles, params, stop_pct=8.0)
    hist = {k: metrics[k] for k in ("roi", "win_rate", "profit_factor", "sharpe", "sortino",
                                    "max_drawdown", "avg_trade", "trade_count")}
    await db.strategy_imports.update_one({"id": draft_id},
        {"$set": {"backtested": True, "preview_backtest": {**hist, "symbol": symbol, "days": days,
                  "bars": metrics["bars"], "at": _strat_now_iso()}, "updated_at": _strat_now_iso()}})
    return {"id": draft_id, "symbol": symbol, "days": days, "historical_results": hist,
            "bars": metrics["bars"], "note": note}


@api_router.post("/library/{lib_id}/backtest", dependencies=[Depends(require_owner)])
async def library_backtest(lib_id: str, symbol: str = "BTC/USD", days: int = 30, exchange: str = "kraken"):
    """Replay a WIREABLE catalog strategy's declarative spec over real historical OHLCV and
    persist the resulting metrics onto the library doc (replaces seeded numbers). No LLM cost."""
    import asyncio  # noqa: PLC0415
    from strategy.declarative_defs import get_declarative_spec  # noqa: PLC0415
    from strategy_runtime import resolve_full_params  # noqa: PLC0415
    from declarative_backtest import run_declarative_backtest  # noqa: PLC0415
    from backtest import fetch_history  # noqa: PLC0415

    doc = await db.strategy_library.find_one({"id": lib_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="strategy not found")
    ekey = doc.get("engine_key")
    spec = get_declarative_spec(ekey) if ekey else None
    if not (doc.get("wireable") and spec):
        raise HTTPException(status_code=400, detail="strategy is not wireable / has no declarative spec")

    days = max(7, min(90, days))
    params = await resolve_full_params(db, ekey)
    try:
        candles = await asyncio.to_thread(fetch_history, symbol, days, "1h", exchange)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("library backtest data fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=f"could not fetch history: {e}") from e
    if len(candles) < 60:
        raise HTTPException(status_code=422, detail="insufficient historical data for a backtest")

    stop_pct = float(params.get("stop_loss_pct", 8.0))
    metrics = await asyncio.to_thread(run_declarative_backtest, spec, candles, params, stop_pct=stop_pct)
    hist = {k: metrics[k] for k in ("roi", "win_rate", "profit_factor", "sharpe", "sortino",
                                    "max_drawdown", "avg_trade", "trade_count")}
    await db.strategy_library.update_one({"id": lib_id}, {"$set": {
        "historical_results": hist, "backtested": True,
        "backtest_meta": {"symbol": symbol, "days": days, "exchange": exchange, "bars": metrics["bars"],
                          "at": _strat_now_iso()},
        "updated_at": _strat_now_iso()}})
    return {"id": lib_id, "engine_key": ekey, "symbol": symbol, "days": days,
            "historical_results": hist, "bars": metrics["bars"]}


@api_router.get("/library/{strategy_id}")
async def library_get(strategy_id: str):
    doc = await db.strategy_library.find_one({"id": strategy_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="strategy not found")
    return doc


@api_router.post("/library/{strategy_id}/favorite", dependencies=[Depends(require_owner)])
async def library_favorite(strategy_id: str):
    doc = await db.strategy_library.find_one({"id": strategy_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="strategy not found")
    fav = not bool(doc.get("favorite"))
    await db.strategy_library.update_one({"id": strategy_id}, {"$set": {"favorite": fav}})
    return {"id": strategy_id, "favorite": fav}


class CloneRequest(BaseModel):
    name: str | None = None


@api_router.post("/library/{strategy_id}/clone", dependencies=[Depends(require_owner)])
async def library_clone(strategy_id: str, body: CloneRequest = CloneRequest()):
    """Copy an existing RULE-BASED (declarative) strategy into a new, independently-editable
    library entry. Core engine strategies (Hunter/Squeeze/Continuation) use hardcoded logic and
    cannot be cloned. The copy is wired via the declarative engine exactly like an import, so it
    survives restarts (rehydrated on startup) and can be tuned without affecting the original."""
    from strategy.declarative_defs import get_declarative_spec, register_imported  # noqa: PLC0415
    from strategy_runtime import resolve_full_params  # noqa: PLC0415

    src = await db.strategy_library.find_one({"id": strategy_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="strategy not found")

    ekey = src.get("engine_key")
    spec = src.get("declarative_spec") or (get_declarative_spec(ekey) if ekey else None)
    if not (spec and spec.get("entry")):
        raise HTTPException(status_code=400, detail=(
            "Only rule-based strategies can be copied. Core engine strategies "
            "(Hunter, Squeeze, Continuation) use built-in logic — create a new strategy instead."))

    params = dict(src.get("engine_params") or {})
    if not params and ekey:
        try:
            params = await resolve_full_params(db, ekey)
        except Exception:  # noqa: BLE001
            params = {}

    base_name = ((body.name or "").strip() or f"{src.get('name', 'Strategy')} (Copy)")[:80]
    new_key = f"clone-{uuid.uuid4().hex[:8]}"
    desc = src.get("description") or ""
    register_imported(new_key, base_name, desc, spec, params)

    now = _strat_now_iso()
    new_doc = {**src}
    new_doc.pop("_id", None)
    new_doc.update({
        "id": new_key,
        "name": base_name,
        "engine_key": new_key,
        "wireable": True,
        "internal": False,
        "imported": True,
        "declarative_spec": spec,
        "engine_params": params,
        "origin": "clone",
        "cloned_from": strategy_id,
        "cloned_from_name": src.get("name"),
        "favorite": False,
        "active_config_id": None,
        "enabled": False,
        "reference_only": False,
        "historical_results": None,
        "backtested": False,
        "backtest_meta": None,
        "created_at": now,
        "updated_at": now,
    })
    await db.strategy_library.insert_one({**new_doc})
    new_doc.pop("_id", None)
    # A freshly copied strategy must NOT auto-trade — the live engine treats a missing
    # meta row as enabled-by-default, so pin the clone to DISABLED until the owner deploys it.
    await db.strategy_meta.update_one(
        {"key": new_key},
        {"$set": {"key": new_key, "status": "DISABLED", "enabled": False, "created_at": now, "updated_at": now}},
        upsert=True,
    )
    return {"cloned": True, "id": new_key, "strategy": new_doc}


class LibraryRename(BaseModel):
    name: str


def _is_user_added(doc: dict) -> bool:
    """Only user-added strategies (imports + clones) may be renamed/deleted.
    Built-in Core and seeded Catalog strategies stay locked."""
    return bool(doc.get("imported") or doc.get("origin") == "clone")


@api_router.patch("/library/{strategy_id}", dependencies=[Depends(require_owner)])
async def library_rename(strategy_id: str, body: LibraryRename):
    """Rename a user-added (imported or cloned) library strategy. Keeps the runtime
    registry name in sync for wired declarative strategies. Built-in strategies are locked."""
    from strategy.declarative_defs import get_declarative_spec, register_imported  # noqa: PLC0415

    src = await db.strategy_library.find_one({"id": strategy_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="strategy not found")
    if not _is_user_added(src):
        raise HTTPException(status_code=400, detail="Only your imported or copied strategies can be renamed. Built-in strategies are locked.")
    new_name = (body.name or "").strip()[:80]
    if not new_name:
        raise HTTPException(status_code=400, detail="A name is required")

    now = _strat_now_iso()
    await db.strategy_library.update_one({"id": strategy_id}, {"$set": {"name": new_name, "updated_at": now}})

    ekey = src.get("engine_key")
    spec = src.get("declarative_spec") or (get_declarative_spec(ekey) if ekey else None)
    if ekey and spec and spec.get("entry"):
        register_imported(ekey, new_name, src.get("description") or "", spec, src.get("engine_params") or {})

    doc = await db.strategy_library.find_one({"id": strategy_id}, {"_id": 0})
    return {"updated": True, "strategy": doc}


@api_router.delete("/library/{strategy_id}", dependencies=[Depends(require_owner)])
async def library_delete(strategy_id: str):
    """Delete a user-added (imported or cloned) library strategy plus its saved configs and
    engine state. Blocked while the strategy is deployed (must be disabled first). Built-in
    Core/Catalog strategies are locked and cannot be deleted."""
    from strategy.declarative_defs import unregister_imported  # noqa: PLC0415

    src = await db.strategy_library.find_one({"id": strategy_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="strategy not found")
    if not _is_user_added(src):
        raise HTTPException(status_code=400, detail="Only your imported or copied strategies can be deleted. Built-in strategies are locked.")

    ekey = src.get("engine_key")
    if ekey:
        meta = await db.strategy_meta.find_one({"key": ekey}, {"_id": 0}) or {}
        # Mirror the live-engine gate: a missing meta row counts as enabled-by-default, so
        # "deployed" means enabled AND not explicitly DISABLED/ERROR.
        effective_enabled = meta.get("enabled", True) and meta.get("status", "PAPER") not in ("DISABLED", "ERROR")
        if effective_enabled:
            raise HTTPException(status_code=409, detail="This strategy is currently deployed. Disable it first, then delete.")

    await db.strategy_library.delete_one({"id": strategy_id})
    configs_removed = 0
    if ekey:
        unregister_imported(ekey)
        res = await db.strategy_configs.delete_many({"strategy_key": ekey})
        configs_removed = res.deleted_count
        await db.strategy_meta.delete_one({"key": ekey})
    return {"deleted": True, "id": strategy_id, "configs_removed": configs_removed}





@api_router.post("/library/{strategy_id}/ai-grade", dependencies=[Depends(require_owner)])
async def library_ai_grade(strategy_id: str):
    """Re-grade a library strategy with the AI (Claude) over its logic + seeded results.
    Consumes LLM credits."""
    doc = await db.strategy_library.find_one({"id": strategy_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="strategy not found")
    import library_ai  # noqa: PLC0415
    try:
        grade = await library_ai.grade_strategy(doc)
    except Exception as e:  # noqa: BLE001
        logger.error("library ai-grade failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI grade error: {e}")
    await db.strategy_library.update_one({"id": strategy_id}, {"$set": {
        "ai_summary": grade["ai_summary"], "ai_health_score": grade["ai_health_score"],
        "ai_grade": grade["ai_grade"], "ai_confidence": grade["ai_confidence"],
        "updated_at": _strat_now_iso(),
    }})
    return {"id": strategy_id, **grade}


# ---- mount router and CORS ----
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """Production safety net: log the full stack for observability but return a clean,
    non-leaking JSON 500 so the client never receives a raw stack trace / HTML error page.
    HTTPException / validation errors are handled by FastAPI's own handlers before this."""
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Please try again."})


# ---- lifecycle ----
@app.on_event("startup")
async def on_startup():
    # Enlarge the default thread-pool executor. asyncio.to_thread (used by every CCXT
    # market-data fetch) shares this pool; the small default (min(32, cpu+4)) could be
    # fully consumed by concurrent/slow Kraken calls during warmup, starving all other
    # to_thread work and making the API appear to hang. 48 workers comfortably absorbs
    # the snapshot + OHLCV + levels fetch storm without changing any trading behaviour.
    with contextlib.suppress(Exception):
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=48, thread_name_prefix="io"))
    # CRITICAL: nothing here may block on MongoDB. Uvicorn does not serve ANY request
    # (including the K8s /health probe) until this returns, so a slow/unreachable Atlas
    # here would hang the probe and crash-loop the whole container. All Mongo-dependent
    # init is deferred to a resilient background task that retries until Mongo is reachable.
    asyncio.create_task(_deferred_startup())
    logger.info("Ananta backend started (serving /health; DB init deferred).")


async def _deferred_startup():
    """Initialise singletons/indexes and start the background loops off the boot path.
    Retries the DB-dependent bootstrap until Mongo is reachable so a transient Atlas
    outage degrades gracefully (app stays up, self-heals) instead of crash-looping."""
    attempt = 0
    while True:
        attempt += 1
        try:
            await load_settings(db)
            await load_portfolio(db)
            await seed_owner(db)
            await seed_demo(db)
            await db.users.create_index("email", unique=True)
            with contextlib.suppress(Exception):
                await db.users.create_index("user_id", unique=True)
                await db.user_sessions.create_index("session_token", unique=True)
                await db.user_sessions.create_index("user_id")
                await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
            await _seed_library_if_empty()
            await _bootstrap_declarative()
            await _purge_orphan_import_drafts()
            logger.info("Deferred DB bootstrap complete (attempt %d).", attempt)
            break
        except Exception as e:  # noqa: BLE001
            logger.warning("DB bootstrap attempt %d failed (Mongo unreachable?): %s", attempt, e)
            await asyncio.sleep(min(5 + attempt, 30))
    trading_loop.start()
    position_watcher.start()
    research_resolver.start()
    shadow_watcher.start()
    lab_worker.start()
    lab_appender.start()
    health_scheduler.start()
    # Heavy index builds + first cache compute run OFF the boot path so the backend
    # becomes healthy instantly even on a large production DB (avoids boot-probe timeouts).
    asyncio.create_task(_background_warmup())


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
