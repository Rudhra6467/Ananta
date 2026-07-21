"""
SHADOW Simulator (Phase 2.1 — validation-first).

Converts the 0.70-0.79 "near-miss" confidence band from passive text rows into
ACTIVE virtual trades that are managed by the SAME exit engine as real paper
trades (`position_watcher.evaluate_exit`) — but with ZERO capital and no impact
on the paper book.

Why: counterfactual returns validate ENTRY quality only. SHADOW exercises the
EXIT engine (stop-loss + volatility-adaptive trailing, incl. per-asset-class
overrides like PAXG) on setups we deliberately did NOT execute, answering
empirically: "what WOULD a 0.76-confidence bullish entry have done?"

Entry rule (kept simple + robust, decoupled from the live fusion gate):
  bias == BULLISH AND  shadow_floor <= confidence < min_confidence(execute floor)
  AND no shadow position already open for that symbol.

Collections:
  - shadow_positions : currently-open virtual trades (one per symbol)
  - shadow_trades    : closed virtual trades with outcome (pnl_pct, exit reason)
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from asset_profiles import asset_class
from market_data import fetch_snapshot
from models import Position, RiskSettings

logger = logging.getLogger(__name__)

# Fixed virtual notional — outcomes are measured in %, so the absolute size is
# irrelevant; $100 keeps quantities readable.
SHADOW_NOTIONAL_USD = 100.0
SHADOW_BAND_WIDTH = 0.10  # SHADOW band = [execute_floor - 0.10, execute_floor)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _shadow_floor(settings: RiskSettings) -> float:
    return round(max(0.0, settings.min_confidence - SHADOW_BAND_WIDTH), 10)


def is_shadow_entry(bias: str, confidence: float, settings: RiskSettings) -> bool:
    """True if this is a bullish near-miss in the SHADOW band."""
    return (
        bias == "BULLISH"
        and _shadow_floor(settings) <= confidence < settings.min_confidence
    )


async def maybe_open_shadow(
    db: AsyncIOMotorDatabase,
    *,
    symbol: str,
    macro,
    snapshot,
    settings: RiskSettings,
    is_breakout: bool = False,
    sector: str | None = None,
    atr_percentile: float | None = None,
) -> dict | None:
    """Open a virtual shadow position for a bullish near-miss, if one isn't already open."""
    if not is_shadow_entry(macro.bias, macro.confidence, settings):
        return None
    if snapshot is None or snapshot.price <= 0:
        return None
    if await db.shadow_positions.find_one({"symbol": symbol}, {"_id": 1}):
        return None  # one open shadow per symbol at a time

    pos = Position(
        symbol=symbol,
        quantity=SHADOW_NOTIONAL_USD / snapshot.price,
        avg_cost=snapshot.price,
        peak_price=snapshot.price,
        breakout_mode=is_breakout,
        sector=sector,
        atr_percentile_at_entry=atr_percentile,
    )
    doc = pos.model_dump()
    doc.update({
        "asset_class": asset_class(symbol),
        "confidence_at_entry": round(float(macro.confidence), 4),
        "bias_at_entry": macro.bias,
        "opened_at": _now_iso(),
    })
    await db.shadow_positions.insert_one(doc)
    logger.info("SHADOW opened %s @ %.6f (conf=%.2f)", symbol, snapshot.price, macro.confidence)
    return doc


def _position_from_doc(doc: dict) -> Position:
    fields = {k: doc[k] for k in Position.model_fields if k in doc}
    return Position(**fields)


async def watch_shadow_once(db: AsyncIOMotorDatabase) -> int:
    """Update peaks + check exits for all open shadow positions. Returns # closed."""
    open_docs = await db.shadow_positions.find({}, {"_id": 0}).to_list(200)
    if not open_docs:
        return 0
    from trading_engine import _safe_settings
    sdoc = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    settings = _safe_settings(sdoc) if sdoc else RiskSettings()
    closed = 0

    # lazy import to avoid a module-load circular import
    # (trading_engine -> shadow_sim -> position_watcher -> trading_engine)
    from position_watcher import evaluate_exit

    for doc in open_docs:
        snap = await fetch_snapshot(doc["symbol"])
        if snap is None or snap.price <= 0:
            continue
        # update trailing peak
        peak = max(float(doc.get("peak_price", doc["avg_cost"])), snap.price)
        if peak != doc.get("peak_price"):
            doc["peak_price"] = peak
            await db.shadow_positions.update_one(
                {"symbol": doc["symbol"]}, {"$set": {"peak_price": peak}},
            )

        pos = _position_from_doc(doc)
        reason, details = evaluate_exit(pos, snap, settings)
        if not reason:
            continue

        entry = pos.avg_cost
        exit_price = snap.price
        pnl_pct = (exit_price - entry) / entry * 100.0 if entry else 0.0
        opened_at = doc.get("opened_at", doc.get("entry_timestamp"))
        try:
            dur_s = (datetime.now(UTC) - datetime.fromisoformat(opened_at)).total_seconds()
        except Exception:
            dur_s = None

        await db.shadow_trades.insert_one({
            "symbol": doc["symbol"],
            "asset_class": doc.get("asset_class", asset_class(doc["symbol"])),
            "confidence_at_entry": doc.get("confidence_at_entry"),
            "entry_price": round(entry, 8),
            "exit_price": round(exit_price, 8),
            "peak_price": round(peak, 8),
            "pnl_pct": round(pnl_pct, 4),
            "win": pnl_pct > 0,
            "exit_reason": reason,
            "breakout": bool(doc.get("breakout_mode", False)),
            "opened_at": opened_at,
            "closed_at": _now_iso(),
            "duration_s": round(dur_s, 1) if dur_s is not None else None,
        })
        await db.shadow_positions.delete_one({"symbol": doc["symbol"]})
        closed += 1
        logger.info("SHADOW closed %s %s pnl=%.2f%%", doc["symbol"], reason, pnl_pct)

    return closed


def _avg(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 4) if vals else None


def summarize_shadow(open_docs: list[dict], closed: list[dict]) -> dict:
    """Win rate, expectancy and per-confidence-bucket stats over closed shadow trades."""
    wins = [t for t in closed if t.get("win")]
    losses = [t for t in closed if not t.get("win")]
    n = len(closed)
    win_rate = round(len(wins) / n * 100.0, 2) if n else None
    avg_win = _avg([t["pnl_pct"] for t in wins])
    avg_loss = _avg([t["pnl_pct"] for t in losses])
    expectancy = _avg([t["pnl_pct"] for t in closed])

    # bucket by confidence-at-entry within the shadow band
    buckets = {"0.70-0.74": [], "0.75-0.79": []}
    for t in closed:
        c = t.get("confidence_at_entry")
        if c is None:
            continue
        if 0.70 <= c < 0.75:
            buckets["0.70-0.74"].append(t["pnl_pct"])
        elif 0.75 <= c < 0.80:
            buckets["0.75-0.79"].append(t["pnl_pct"])
    bucket_out = [
        {"bucket": k, "count": len(v), "avg_pnl_pct": _avg(v),
         "win_rate": round(sum(1 for x in v if x > 0) / len(v) * 100.0, 2) if v else None}
        for k, v in buckets.items()
    ]

    return {
        "open_count": len(open_docs),
        "closed_count": n,
        "win_rate_pct": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "expectancy_pct": expectancy,
        "confidence_buckets": bucket_out,
        "note": (
            "Virtual near-miss trades (0.70-0.79 bullish) managed by the LIVE exit engine, "
            "no capital. Validates the EXIT engine on setups we did not execute. Raw price "
            "(pre-friction); treat expectancy as directional, not bankable."
        ),
    }


class ShadowWatcherLoop:
    """Manages open shadow positions on a short cadence (reuses the live exit engine)."""

    def __init__(self, db: AsyncIOMotorDatabase, interval_seconds: int = 30):
        self.db = db
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self):
        logger.info("ShadowWatcherLoop started, interval=%ss", self.interval)
        while not self._stop.is_set():
            try:
                await watch_shadow_once(self.db)
            except Exception as e:
                logger.exception("Shadow watcher iteration error: %s", e)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
        logger.info("ShadowWatcherLoop stopped")

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
