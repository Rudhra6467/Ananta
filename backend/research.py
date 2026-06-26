"""
Research Database (Phase 2 — validation-first architecture).

A permanent, append-only diagnostic log of EVERY asset evaluation cycle —
whether or not a trade occurs. This is the instrument that converts the bot's
"no-trade" silence into measurable evidence.

Per ROADMAP.md §2/§3/§3.6 it captures the core decision schema
(Timestamp | Asset | Gemini_Confidence | News_Sentiment | Macro_Bias | Decision)
plus a 4-tier confidence band and forward-looking Counterfactual P&L fields that
are resolved later by a background loop (24h / 72h / 7d).

Design notes:
- Additive only: logging never throws into the trading cycle (callers wrap in
  contextlib.suppress). Survives portfolio resets (it is the permanent record).
- Counterfactual returns are RAW price returns (entry-only, PRE-friction). They
  validate ENTRY quality, NOT the exit engine. Classification bands are applied
  at query time so the rule can be refined without migrating stored data.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from market_data import fetch_ohlcv_4h, fetch_snapshot
from models import ResearchLog
from strategies import STRATEGY_DEFS

logger = logging.getLogger(__name__)

# Counterfactual resolution horizons.
CF_HORIZONS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "72h": timedelta(hours=72),
    "7d": timedelta(days=7),
}

# Default noise band (%) for classifying a resolved rejection.
DEFAULT_CF_BAND_PCT = 1.5


# ---------- tier classification ----------
def confidence_tier(
    confidence: float,
    *,
    execute_floor: float = 0.80,
    shadow_width: float = 0.10,
    log_floor: float = 0.50,
) -> str:
    """Map a Gemini macro confidence to a 4-tier research band.

    EXECUTE   >= execute_floor (real paper fills)
    SHADOW    [execute_floor - shadow_width, execute_floor)  (full sim, no book)
    LOG_ONLY  [log_floor, shadow band)                       (entry context only)
    IGNORE    < log_floor
    """
    shadow_floor = round(max(0.0, execute_floor - shadow_width), 10)
    if confidence >= execute_floor:
        return "EXECUTE"
    if confidence >= shadow_floor:
        return "SHADOW"
    if confidence >= log_floor:
        return "LOG_ONLY"
    return "IGNORE"


def _absolute_decision(decision: str, blocked_reasons: list[str]) -> str:
    """EXECUTE = an order/intent was generated; REJECT = a signal was blocked;
    HOLD = no actionable signal."""
    if decision in ("BUY", "SELL"):
        return "EXECUTE"
    if blocked_reasons:
        return "REJECT"
    return "HOLD"


# ---------- Slice 1: per-cycle logger ----------
async def log_evaluation_cycle(
    db: AsyncIOMotorDatabase,
    *,
    symbol: str,
    macro_confidence: float,
    macro_bias: str,
    decision: str,
    blocked_reasons: list[str],
    price: float,
    setup_strength: str | None = None,
    breakout: bool = False,
    htf_trend_aligned: bool | None = None,
    reasoning_id: str | None = None,
    news_source: str | None = None,
    news_sentiment: float | None = None,
    min_confidence: float = 0.80,
    row_type: str = "SETUP",
    asset_class: str | None = None,
    sector_data: dict | None = None,
    reason_codes: list[str] | None = None,
    support_zone: float | None = None,
    resistance_zone: float | None = None,
    rsi_4h: float | None = None,
    volume_status: str | None = None,
    market_regime: str | None = None,
    breaker_state: str = "PASS",
    relative_strength_btc: float | None = None,
    rr_estimate: float | None = None,
    fifty_pct: dict | None = None,
    strategy_signals: dict | None = None,
) -> ResearchLog:
    """Append one row to the permanent research_log. Returns the row."""
    tier = "BACKGROUND" if row_type == "BACKGROUND" else confidence_tier(
        macro_confidence, execute_floor=min_confidence,
    )
    row = ResearchLog(
        symbol=symbol,
        row_type=row_type,
        asset_class=asset_class,
        macro_confidence=round(float(macro_confidence), 4),
        macro_bias=macro_bias if macro_bias in ("BULLISH", "BEARISH", "NEUTRAL") else "NEUTRAL",
        news_sentiment=news_sentiment,
        news_source=news_source,
        decision=decision if decision in ("BUY", "SELL", "HOLD", "BLOCKED") else "HOLD",
        absolute_decision=_absolute_decision(decision, blocked_reasons),
        confidence_tier=tier,
        blocked_reasons=list(blocked_reasons or []),
        reason_codes=list(reason_codes or []),
        price=round(float(price), 8),
        setup_strength=setup_strength,
        breakout=bool(breakout),
        htf_trend_aligned=htf_trend_aligned,
        reasoning_id=reasoning_id,
        support_zone=support_zone,
        resistance_zone=resistance_zone,
        rsi_4h=rsi_4h,
        volume_status=volume_status,
        market_regime=market_regime,
        breaker_state=breaker_state if breaker_state in ("PASS", "CAUTION", "VETO") else "PASS",
        relative_strength_btc=relative_strength_btc,
        rr_estimate=rr_estimate,
        sector_data=sector_data or {},
        swing_low=(fifty_pct or {}).get("swing_low"),
        swing_high=(fifty_pct or {}).get("swing_high"),
        midpoint_50=(fifty_pct or {}).get("midpoint_50"),
        distance_from_midpoint_pct=(fifty_pct or {}).get("distance_from_midpoint_pct"),
        above_or_below_midpoint=(fifty_pct or {}).get("above_or_below_midpoint"),
        strategy_signals=strategy_signals or {},
    )
    await db.research_log.insert_one(row.model_dump())
    return row


# ---------- Phase 2: Rejection Leaderboard ----------
async def summarize_rejections(db: AsyncIOMotorDatabase, since_hours: int | None = None) -> dict:
    """Aggregate reason_codes across research_log rows into a leaderboard for the
    3-day iterative sprint reviews: which filters protect capital vs. block winners."""
    query: dict = {}
    if since_hours:
        cutoff = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
        query = {"timestamp": {"$gte": cutoff}}

    counts: dict[str, int] = {}
    per_symbol: dict[str, dict[str, int]] = {}
    total = 0
    greenlit = 0
    cursor = db.research_log.find(query, {"reason_codes": 1, "symbol": 1})
    async for doc in cursor:
        total += 1
        sym = doc.get("symbol", "?")
        for code in (doc.get("reason_codes") or []):
            counts[code] = counts.get(code, 0) + 1
            per_symbol.setdefault(sym, {})[code] = per_symbol.setdefault(sym, {}).get(code, 0) + 1
            if code == "GREENLIT":
                greenlit += 1
    leaderboard = [
        {"code": k, "count": v, "pct_of_evals": round(v / total * 100.0, 2) if total else 0.0}
        for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return {
        "total_evaluations": total,
        "greenlit": greenlit,
        "greenlit_rate_pct": round(greenlit / total * 100.0, 2) if total else 0.0,
        "since_hours": since_hours,
        "rejection_leaderboard": leaderboard,
        "per_symbol": per_symbol,
    }


def summarize_funnel(rows: list[dict]) -> dict:
    """Setup funnel: Detected → Qualified → PASS/CAUTION/VETO → Executed (Phase 2.x)."""
    setups = [r for r in rows if r.get("row_type", "SETUP") == "SETUP"]
    breaker = {"PASS": 0, "CAUTION": 0, "VETO": 0}
    for r in setups:
        st = r.get("breaker_state", "PASS")
        breaker[st] = breaker.get(st, 0) + 1
    return {
        "detected": len(setups),
        "qualified": sum(1 for r in setups if "GREENLIT" in (r.get("reason_codes") or [])),
        "breaker": breaker,
        "executed": sum(1 for r in setups if r.get("decision") == "BUY"),
    }


def summarize_breaker_accuracy(rows: list[dict], band_pct: float = DEFAULT_CF_BAND_PCT) -> dict:
    """Per breaker-state, classify resolved forward outcomes to prove whether the
    breaker is intelligent or merely restrictive. For a CAUTION/VETO row, an UP
    forward move = breaker was over-restrictive (missed); DOWN = breaker protected."""
    out: dict[str, dict] = {}
    for st in ("PASS", "CAUTION", "VETO"):
        sub = [r for r in rows if r.get("breaker_state", "PASS") == st and r.get("row_type", "SETUP") == "SETUP"]
        rets = [r.get("cf_ret_7d") for r in sub if r.get("cf_ret_7d") is not None]
        correct = missed = neutral = 0
        for r in sub:
            primary = r.get("cf_ret_7d")
            if primary is None:
                primary = r.get("cf_ret_72h")
            if primary is None:
                primary = r.get("cf_ret_24h")
            cls = classify_cf(primary, band_pct)
            if cls == "CORRECT_REJECTION":
                correct += 1
            elif cls == "MISSED_OPPORTUNITY":
                missed += 1
            elif cls == "NEUTRAL":
                neutral += 1
        out[st] = {
            "count": len(sub),
            "resolved": len(rets),
            "avg_ret_7d": round(sum(rets) / len(rets), 4) if rets else None,
            "protected": correct,       # forward move was down → breaker was right to caution/veto
            "over_restrictive": missed,  # forward move was up → breaker held back a winner
            "neutral": neutral,
        }
    return out


# ---------- Phase B: Research-First analytics (DIAGNOSTIC; credit-free aggregation) ----------
def _mean(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _cf_primary(r: dict) -> float | None:
    """Best-resolved forward return for a row (72h preferred)."""
    for f in ("cf_ret_72h", "cf_ret_7d", "cf_ret_24h"):
        if r.get(f) is not None:
            return r.get(f)
    return None


def summarize_winner_profile(trades: list[dict], eps: float = 0.0) -> dict:
    """'What makes winners?' — average entry features of WIN vs LOSS closed trades.
    Consumes closed SELL trades carrying `entry_attribution` + mfe/mae."""
    sells = [t for t in trades if t.get("side") == "SELL"]
    winners = [t for t in sells if (t.get("pnl") or 0) > eps]
    losers = [t for t in sells if (t.get("pnl") or 0) < -eps]

    def profile(group: list[dict]) -> dict:
        attr = [t.get("entry_attribution") or {} for t in group]
        return {
            "count": len(group),
            "avg_rsi": _mean([a.get("rsi_at_entry") for a in attr]),
            "avg_distance_from_midpoint_pct": _mean([a.get("distance_from_midpoint_pct") for a in attr]),
            "avg_relative_strength": _mean([a.get("relative_strength_btc") for a in attr]),
            "avg_support_zone_score": _mean([a.get("support_zone_score") for a in attr]),
            "avg_volume_score": _mean([a.get("volume_score") for a in attr]),
            "avg_rr_estimate": _mean([a.get("rr_estimate") for a in attr]),
            "avg_mfe_pct": _mean([t.get("mfe_pct") for t in group]),
            "avg_mae_pct": _mean([t.get("mae_pct") for t in group]),
        }

    total = len(winners) + len(losers)
    return {
        "winners": profile(winners),
        "losers": profile(losers),
        "win_rate_pct": round(len(winners) / total * 100, 2) if total else 0.0,
        "sample": total,
    }


_MISS_BUCKETS = [
    ("RSI Not Reset", "REJECTED_RSI_NOT_RESET"),
    ("Volume Not Exhausted", "REJECTED_VOLUME_NOT_EXHAUSTED"),
    ("No Support Zone", "REJECTED_NO_SUPPORT_ZONE"),
    ("Chasing Green Candle", "REJECTED_CHASING_GREEN_CANDLE"),
    ("Circuit Breaker", "REJECTED_SECONDARY_VETO_EXISTENTIAL"),
]


def summarize_missed_opportunities(rows: list[dict], band_pct: float = DEFAULT_CF_BAND_PCT) -> dict:
    """For each rejection filter, how many rejected setups LATER became profitable vs
    not (resolved counterfactuals) + net counterfactual P&L. Reveals which filters
    protect capital vs which are over-restrictive."""
    out = []
    for label, code in _MISS_BUCKETS:
        sub = [r for r in rows if code in (r.get("reason_codes") or []) and _cf_primary(r) is not None]
        prof = [r for r in sub if _cf_primary(r) > band_pct]
        unprof = [r for r in sub if _cf_primary(r) < -band_pct]
        net = sum(_cf_primary(r) for r in sub)
        out.append({
            "filter": label, "code": code,
            "rejected_resolved": len(sub),
            "later_profitable": len(prof),
            "later_unprofitable": len(unprof),
            "net_cf_pnl_pct": round(net, 4),
        })
    known = {c for _, c in _MISS_BUCKETS}
    others = [r for r in rows if r.get("reason_codes") and not (set(r["reason_codes"]) & known)
              and "GREENLIT" not in r["reason_codes"] and _cf_primary(r) is not None]
    if others:
        net = sum(_cf_primary(r) for r in others)
        out.append({
            "filter": "Other", "code": "OTHER",
            "rejected_resolved": len(others),
            "later_profitable": len([r for r in others if _cf_primary(r) > band_pct]),
            "later_unprofitable": len([r for r in others if _cf_primary(r) < -band_pct]),
            "net_cf_pnl_pct": round(net, 4),
        })
    return {"buckets": out}


_RSI_BANDS = [("20-30", 20, 30), ("30-40", 30, 40), ("40-50", 40, 50), ("50-60", 50, 60), ("60+", 60, 999)]


def summarize_rsi_distribution(rows: list[dict], band_pct: float = DEFAULT_CF_BAND_PCT) -> dict:
    """RSI bucket study from resolved counterfactuals (entry-quality proxy, A-i).
    Win rate / avg return / avg drawdown / count per RSI band — informs (does NOT change)
    the RSI threshold."""
    out = []
    for label, lo, hi in _RSI_BANDS:
        sub = [r for r in rows if r.get("rsi_4h") is not None and lo <= r["rsi_4h"] < hi and _cf_primary(r) is not None]
        rets = [_cf_primary(r) for r in sub]
        wins = [x for x in rets if x > band_pct]
        draws = [r.get("cf_ret_24h") for r in sub if (r.get("cf_ret_24h") or 0) < 0]
        out.append({
            "bucket": label,
            "count": len(sub),
            "win_rate_pct": round(len(wins) / len(sub) * 100, 2) if sub else 0.0,
            "avg_return_pct": _mean(rets),
            "avg_drawdown_pct": _mean(draws),
        })
    return {"buckets": out}


def summarize_zone_effectiveness(rows: list[dict], band_pct: float = DEFAULT_CF_BAND_PCT) -> dict:
    """Support-zone predictive value: for rows interacting with a support zone, how
    often the forward move bounced (up) vs failed (down), with avg return/drawdown.
    Overall + per-symbol."""
    interacting = [r for r in rows if r.get("support_zone") is not None and _cf_primary(r) is not None]

    def block(sub: list[dict]) -> dict:
        rets = [_cf_primary(r) for r in sub]
        draws = [r.get("cf_ret_24h") for r in sub if (r.get("cf_ret_24h") or 0) < 0]
        return {
            "touches": len(sub),
            "successful_bounces": len([x for x in rets if x > band_pct]),
            "failed_bounces": len([x for x in rets if x < -band_pct]),
            "avg_return_pct": _mean(rets),
            "avg_drawdown_pct": _mean(draws),
        }

    by_symbol = {}
    for r in interacting:
        by_symbol.setdefault(r["symbol"], []).append(r)
    per_symbol = [{"symbol": s, **block(rs)} for s, rs in by_symbol.items()]
    per_symbol.sort(key=lambda x: x["touches"], reverse=True)
    return {"overall": block(interacting), "by_symbol": per_symbol}



# ---------- Slice 2: counterfactual resolver ----------
async def _default_fetch_price(symbol: str) -> float | None:
    snap = await fetch_snapshot(symbol)
    return snap.price if snap is not None else None


async def resolve_counterfactuals(
    db: AsyncIOMotorDatabase,
    fetch_price: Callable[[str], Awaitable[float | None]] | None = None,
    now: datetime | None = None,
    max_rows_per_horizon: int = 500,
) -> int:
    """Fill forward returns for rows whose horizon has elapsed.

    Forward return = (price_now - price_at_decision) / price_at_decision * 100.
    Resolved 'now' is the resolution-time price (resolver cadence keeps this
    within minutes of the true horizon boundary). Returns rows resolved.
    """
    fetch_price = fetch_price or _default_fetch_price
    now = now or datetime.now(UTC)
    resolved = 0

    for key, delta in CF_HORIZONS.items():
        ret_field = f"cf_ret_{key}"
        done_field = f"cf_resolved_{key}"
        cutoff = (now - delta).isoformat()
        rows = await db.research_log.find(
            {done_field: False, "timestamp": {"$lte": cutoff}},
            {"_id": 0, "id": 1, "symbol": 1, "price": 1},
        ).limit(max_rows_per_horizon).to_list(max_rows_per_horizon)
        if not rows:
            continue

        price_cache: dict[str, float | None] = {}
        for r in rows:
            entry = r.get("price")
            if not entry:
                await db.research_log.update_one({"id": r["id"]}, {"$set": {done_field: True}})
                continue
            sym = r["symbol"]
            if sym not in price_cache:
                price_cache[sym] = await fetch_price(sym)
            cur = price_cache[sym]
            if cur is None:
                continue  # retry next pass; market data unavailable
            ret = (cur - entry) / entry * 100.0
            await db.research_log.update_one(
                {"id": r["id"]},
                {"$set": {ret_field: round(ret, 4), done_field: True}},
            )
            resolved += 1

    if resolved:
        logger.info("Counterfactual resolver: filled %d forward-return cells", resolved)
    return resolved


# ---------- query-time analytics ----------
def classify_cf(ret: float | None, band_pct: float = DEFAULT_CF_BAND_PCT) -> str | None:
    """Classify a resolved REJECTED setup's forward return.

    For a long-only bot: price UP after a rejection = we were too strict
    (MISSED_OPPORTUNITY); price DOWN = the rejection protected capital
    (CORRECT_REJECTION). Within +/- band = NEUTRAL noise.
    NOTE: raw-price, pre-friction (entry-quality proxy only).
    """
    if ret is None:
        return None
    if ret >= band_pct:
        return "MISSED_OPPORTUNITY"
    if ret <= -band_pct:
        return "CORRECT_REJECTION"
    return "NEUTRAL"


# confidence buckets for near-miss / expectancy-by-tier analysis
_BUCKETS: list[tuple[str, float, float]] = [
    ("<0.50", 0.0, 0.50),
    ("0.50-0.59", 0.50, 0.60),
    ("0.60-0.69", 0.60, 0.70),
    ("0.70-0.74", 0.70, 0.75),
    ("0.75-0.79", 0.75, 0.80),
    ("0.80-0.84", 0.80, 0.85),
    ("0.85-0.89", 0.85, 0.90),
    ("0.90+", 0.90, 1.0001),
]


def _bucket_for(conf: float) -> str:
    for label, lo, hi in _BUCKETS:
        if lo <= conf < hi:
            return label
    return "<0.50"


def _avg(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 4) if vals else None


def summarize_research(rows: list[dict], band_pct: float = DEFAULT_CF_BAND_PCT) -> dict:
    """Aggregate research_log rows into decision/tier/bucket diagnostics.

    Surfaces: total rows, decision + tier distribution, per-confidence-bucket
    counterfactual returns and correct-rejection vs missed-opportunity counts,
    and a focused Near-Miss block (BULLISH rejections in the 0.70-0.79 band).
    """
    setup_rows = [r for r in rows if r.get("row_type", "SETUP") == "SETUP"]
    total = len(setup_rows)

    decision_dist: dict[str, int] = {"EXECUTE": 0, "REJECT": 0, "HOLD": 0}
    tier_dist: dict[str, int] = {"EXECUTE": 0, "SHADOW": 0, "LOG_ONLY": 0, "IGNORE": 0}
    resolved_24h = resolved_72h = resolved_7d = 0

    buckets: dict[str, dict] = {
        label: {
            "count": 0, "rets_24h": [], "rets_72h": [], "rets_7d": [],
            "correct_rejection": 0, "missed_opportunity": 0, "neutral": 0,
        }
        for label, _, _ in _BUCKETS
    }

    for r in setup_rows:
        decision_dist[r.get("absolute_decision", "HOLD")] = (
            decision_dist.get(r.get("absolute_decision", "HOLD"), 0) + 1
        )
        tier_dist[r.get("confidence_tier", "IGNORE")] = (
            tier_dist.get(r.get("confidence_tier", "IGNORE"), 0) + 1
        )
        if r.get("cf_resolved_24h"):
            resolved_24h += 1
        if r.get("cf_resolved_72h"):
            resolved_72h += 1
        if r.get("cf_resolved_7d"):
            resolved_7d += 1

        b = buckets[_bucket_for(float(r.get("macro_confidence", 0.0)))]
        b["count"] += 1
        for key, store in (("cf_ret_24h", "rets_24h"), ("cf_ret_72h", "rets_72h"), ("cf_ret_7d", "rets_7d")):
            v = r.get(key)
            if v is not None:
                b[store].append(float(v))
        # classification uses the 7d horizon as primary (falls back to 72h/24h)
        primary = r.get("cf_ret_7d")
        if primary is None:
            primary = r.get("cf_ret_72h")
        if primary is None:
            primary = r.get("cf_ret_24h")
        cls = classify_cf(primary, band_pct)
        if cls == "CORRECT_REJECTION":
            b["correct_rejection"] += 1
        elif cls == "MISSED_OPPORTUNITY":
            b["missed_opportunity"] += 1
        elif cls == "NEUTRAL":
            b["neutral"] += 1

    bucket_out = []
    for label, _, _ in _BUCKETS:
        b = buckets[label]
        bucket_out.append({
            "bucket": label,
            "count": b["count"],
            "avg_ret_24h": _avg(b["rets_24h"]),
            "avg_ret_72h": _avg(b["rets_72h"]),
            "avg_ret_7d": _avg(b["rets_7d"]),
            "correct_rejection": b["correct_rejection"],
            "missed_opportunity": b["missed_opportunity"],
            "neutral": b["neutral"],
        })

    # Near-Miss: BULLISH setups rejected/held in the 0.70-0.79 confidence band.
    near = [
        r for r in setup_rows
        if r.get("macro_bias") == "BULLISH"
        and 0.70 <= float(r.get("macro_confidence", 0.0)) < 0.80
        and r.get("absolute_decision") in ("REJECT", "HOLD")
    ]
    near_resolved = [r.get("cf_ret_7d") for r in near if r.get("cf_ret_7d") is not None]
    near_missed = sum(1 for v in near_resolved if classify_cf(v, band_pct) == "MISSED_OPPORTUNITY")
    near_correct = sum(1 for v in near_resolved if classify_cf(v, band_pct) == "CORRECT_REJECTION")

    return {
        "total_setup_rows": total,
        "decision_distribution": decision_dist,
        "tier_distribution": tier_dist,
        "counterfactuals_resolved": {"24h": resolved_24h, "72h": resolved_72h, "7d": resolved_7d},
        "confidence_buckets": bucket_out,
        "near_miss_0_70_0_79_bullish": {
            "count": len(near),
            "resolved_7d": len(near_resolved),
            "missed_opportunity": near_missed,
            "correct_rejection": near_correct,
            "avg_ret_7d": _avg([v for v in near_resolved]),
            "interpretation": (
                "If missed_opportunity >> correct_rejection here, the 0.80 floor may be too "
                "strict for this regime. Raw-price proxy — confirm via friction-adjusted sim before acting."
            ),
        },
        "band_pct": band_pct,
        "note": (
            "Counterfactual returns are RAW price (pre-friction, entry-quality proxy). "
            "They validate ENTRY selection, not the exit engine."
        ),
    }


# ---------- background resolver loop ----------
STRATEGY_LAB_HORIZON = timedelta(days=7)
STRATEGY_LAB_WINDOW_DAYS = 30


async def resolve_strategy_lab(
    db: AsyncIOMotorDatabase,
    now: datetime | None = None,
    band_pct: float = 1.0,
    max_rows: int = 600,
) -> int:
    """Resolve PENDING strategy_lab_log rows whose 7d horizon elapsed: fill forward
    return_pct + max_drawdown_pct (from cached 4h OHLC) + WIN/LOSS/NEUTRAL outcome.
    CCXT-only (credit-free). Capped per pass to keep memory + API load bounded."""
    now = now or datetime.now(UTC)
    cutoff = (now - STRATEGY_LAB_HORIZON).isoformat()
    rows = await db.strategy_lab_log.find(
        {"outcome": "PENDING", "detected_at": {"$lte": cutoff}},
        {"_id": 0, "id": 1, "symbol": 1, "detected_at": 1, "entry_price": 1},
    ).limit(max_rows).to_list(max_rows)
    if not rows:
        return 0

    price_cache: dict[str, float | None] = {}
    bars_cache: dict[str, list[list[float]]] = {}
    resolved = 0
    for r in rows:
        sym, entry = r.get("symbol"), r.get("entry_price")
        if not entry:
            await db.strategy_lab_log.update_one({"id": r["id"]}, {"$set": {"outcome": "VOID", "resolved": True}})
            continue
        if sym not in price_cache:
            snap = await fetch_snapshot(sym)
            price_cache[sym] = snap.price if snap is not None else None
            with contextlib.suppress(Exception):
                bars_cache[sym] = await fetch_ohlcv_4h(sym, limit=60) or []
        cur = price_cache[sym]
        if cur is None:
            continue  # retry next pass
        ret = (cur - entry) / entry * 100.0
        # max adverse excursion = worst low after detection (<=0); from cached 4h bars
        det_ms = _iso_to_ms(r.get("detected_at"))
        lows = [b[3] for b in bars_cache.get(sym, []) if b and b[0] >= det_ms] if det_ms else []
        max_dd = round((min(lows) - entry) / entry * 100.0, 4) if lows else round(min(0.0, ret), 4)
        outcome = "WIN" if ret > band_pct else "LOSS" if ret < -band_pct else "NEUTRAL"
        await db.strategy_lab_log.update_one(
            {"id": r["id"]},
            {"$set": {"return_pct": round(ret, 4), "max_drawdown_pct": max_dd,
                      "outcome": outcome, "resolved": True, "resolved_at": now.isoformat()}},
        )
        resolved += 1
    if resolved:
        logger.info("Strategy-lab resolver: resolved %d signals", resolved)
    return resolved


def _iso_to_ms(iso: str | None) -> int | None:
    if not iso:
        return None
    with contextlib.suppress(Exception):
        return int(datetime.fromisoformat(iso).timestamp() * 1000)
    return None


async def summarize_strategy_lab(
    db: AsyncIOMotorDatabase, window_days: int = STRATEGY_LAB_WINDOW_DAYS,
    min_promote: int = 20,
) -> dict:
    """Strategy Research Laboratory scoreboard. Streams strategy_lab_log (memory-safe,
    projected) into per-strategy funnel + research metrics, then computes deltas vs the
    Hunter benchmark. Sorted by Expected Value — the primary promotion dashboard."""
    cutoff = (datetime.now(UTC) - timedelta(days=window_days)).isoformat()
    acc: dict[str, dict] = {
        d["id"]: {"detected": 0, "qualified": 0, "breaker_pass": 0, "resolved": 0,
                  "wins": 0, "losses": 0, "neutral": 0, "sum_ret": 0.0,
                  "gross_profit": 0.0, "gross_loss": 0.0, "sum_loss": 0.0, "worst_dd": 0.0}
        for d in STRATEGY_DEFS
    }
    cursor = db.strategy_lab_log.find(
        {"detected_at": {"$gte": cutoff}},
        {"_id": 0, "strategy": 1, "qualified": 1, "breaker_state": 1,
         "outcome": 1, "return_pct": 1, "max_drawdown_pct": 1},
    )
    async for doc in cursor:
        a = acc.get(doc.get("strategy"))
        if a is None:
            continue
        a["detected"] += 1
        if doc.get("qualified"):
            a["qualified"] += 1
            if doc.get("breaker_state") == "PASS":
                a["breaker_pass"] += 1
        outcome = doc.get("outcome")
        if outcome in ("WIN", "LOSS", "NEUTRAL"):
            a["resolved"] += 1
            ret = doc.get("return_pct") or 0.0
            a["sum_ret"] += ret
            dd = doc.get("max_drawdown_pct")
            if dd is not None and dd < a["worst_dd"]:
                a["worst_dd"] = dd
            if outcome == "WIN":
                a["wins"] += 1
                a["gross_profit"] += ret
            elif outcome == "LOSS":
                a["losses"] += 1
                a["gross_loss"] += abs(ret)
                a["sum_loss"] += ret
            else:
                a["neutral"] += 1

    def metrics(a: dict) -> dict:
        det, qual, res = a["detected"], a["qualified"], a["resolved"]
        wins, losses = a["wins"], a["losses"]
        wr = wins / res if res else 0.0
        avg_win = a["gross_profit"] / wins if wins else 0.0
        avg_loss = a["sum_loss"] / losses if losses else 0.0  # negative
        ev = (wr * avg_win + (1 - wr) * avg_loss) if res else None
        pf = (a["gross_profit"] / a["gross_loss"]) if a["gross_loss"] > 0 else (None if a["gross_profit"] == 0 else float("inf"))
        return {
            "detected": det, "qualified": qual, "breaker_pass": a["breaker_pass"],
            "resolved": res, "wins": wins, "losses": losses, "neutral": a["neutral"],
            "win_rate_pct": round(wr * 100, 1) if res else None,
            "avg_return_pct": round(a["sum_ret"] / res, 3) if res else None,
            "expected_value_pct": round(ev, 3) if ev is not None else None,
            "profit_factor": (round(pf, 2) if pf not in (None, float("inf")) else (None if pf is None else 999.0)),
            "max_drawdown_pct": round(a["worst_dd"], 3),
            "qualification_rate_pct": round(qual / det * 100, 1) if det else None,
            "conversion_rate_pct": round(wins / det * 100, 1) if det else None,
            "execution_efficiency_pct": round(wins / qual * 100, 1) if qual else None,
        }

    computed = {sid: metrics(a) for sid, a in acc.items()}
    hunter = computed.get("hunter", {})

    def _delta(v, base):
        if v is None or base is None:
            return None
        return round(v - base, 3)

    out = []
    for d in STRATEGY_DEFS:
        m = computed[d["id"]]
        deltas = {
            "win_rate": _delta(m["win_rate_pct"], hunter.get("win_rate_pct")),
            "avg_return": _delta(m["avg_return_pct"], hunter.get("avg_return_pct")),
            "expected_value": _delta(m["expected_value_pct"], hunter.get("expected_value_pct")),
            "profit_factor": _delta(m["profit_factor"], hunter.get("profit_factor")),
        }
        verdict = "Accumulating data…"
        if m["resolved"] >= min_promote:
            beats = all((deltas[k] or -1) > 0 for k in ("win_rate", "avg_return", "expected_value", "profit_factor"))
            if d["id"] == "hunter":
                verdict = "Benchmark"
            elif beats:
                verdict = "PROMOTION CANDIDATE"
            elif (m["expected_value_pct"] or -1) > 0:
                verdict = "Edge, below Hunter"
            else:
                verdict = "Underperforming"
        out.append({**d, **m, "vs_hunter": deltas, "verdict": verdict})

    out.sort(key=lambda x: (x["expected_value_pct"] is not None, x["expected_value_pct"] or -999), reverse=True)
    return {"strategies": out, "promote_threshold": min_promote, "window_days": window_days,
            "benchmark": "hunter"}


class ResearchResolverLoop:
    """Periodically resolves elapsed counterfactual horizons. Uses CCXT market
    data only (no LLM calls) — credit-neutral."""

    def __init__(self, db: AsyncIOMotorDatabase, interval_seconds: int = 600):
        self.db = db
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self):
        logger.info("ResearchResolverLoop started, interval=%ss", self.interval)
        while not self._stop.is_set():
            try:
                await resolve_counterfactuals(self.db)
                await resolve_strategy_lab(self.db)
            except Exception as e:
                logger.exception("Research resolver iteration error: %s", e)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
        logger.info("ResearchResolverLoop stopped")

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
