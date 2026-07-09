"""AI Trading Coach — a proactive weekly review over the live trade ledger.

Uses the Emergent LLM key (Claude Sonnet) to turn the last 7 days of closed trades
into a plain-English coaching review plus ONE concrete, one-click-applyable parameter
tweak drawn from a safe whitelist. Grounded: the model only sees the real aggregates
we assemble here.
"""
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("ananta.coach")

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-6"

# Settings the Coach is allowed to recommend tuning, with (min, max) clamps.
APPLYABLE = {
    "min_confidence": (0.50, 0.95, "confidence floor"),
    "max_daily_loss_pct": (2.0, 20.0, "daily loss cap %"),
    "max_concurrent_positions": (1, 20, "max open positions"),
    "max_spread_pct": (0.10, 2.0, "max spread %"),
    "squeeze_vol_expansion_min": (1.2, 2.5, "squeeze volume expansion x"),
    "rsi_reset_max": (30.0, 45.0, "RSI reset ceiling"),
}

SYSTEM_PROMPT = (
    "You are Ananta's AI Trading Coach — a proactive, institutional-grade performance coach embedded "
    "in an algorithmic crypto trading platform. You review the operator's recent trading and give ONE "
    "focused weekly review. Use ONLY the DATA SNAPSHOT provided. Never invent trades or numbers.\n"
    "Return STRICT JSON only (no markdown, no prose outside JSON) with this exact shape:\n"
    "{\n"
    '  "summary": "2-3 sentence plain-English review citing real numbers",\n'
    '  "best_strategy": "hunter|squeeze|continuation|none",\n'
    '  "worst_strategy": "hunter|squeeze|continuation|none",\n'
    '  "common_mistake": "the single most impactful recurring issue you see",\n'
    '  "recommendation": {\n'
    '     "title": "short action title",\n'
    '     "detail": "why this helps, referencing the data",\n'
    '     "setting_key": "one of the ALLOWED_SETTINGS keys, or empty string if none fits",\n'
    '     "suggested_value": <number or null>\n'
    "  },\n"
    '  "estimated_impact": "e.g. +11% profit factor (be honest and modest)",\n'
    '  "confidence": <integer 0-100>\n'
    "}\n"
    "The setting_key MUST be from ALLOWED_SETTINGS and suggested_value MUST stay within its range. "
    "If the sample is too small to be confident, say so in summary, set recommendation.setting_key to "
    "empty string and keep confidence low."
)


async def _gather(db) -> tuple[str, dict]:
    since = datetime.now(UTC) - timedelta(days=7)
    since_iso = since.isoformat()
    trades = await db.trades.find(
        {"side": "SELL", "pnl": {"$ne": None}, "timestamp": {"$gte": since_iso}}, {"_id": 0},
    ).sort("timestamp", -1).limit(400).to_list(400)

    per: dict[str, dict] = {}
    for t in trades:
        s = t.get("strategy") or "unknown"
        d = per.setdefault(s, {"n": 0, "wins": 0, "pnl": 0.0, "exits": {}})
        d["n"] += 1
        pnl = t.get("pnl") or 0
        d["pnl"] += pnl
        if pnl > 0:
            d["wins"] += 1
        er = t.get("exit_reason") or "-"
        d["exits"][er] = d["exits"].get(er, 0) + 1

    lines = []
    for s, d in per.items():
        wr = round(100 * d["wins"] / d["n"], 1) if d["n"] else 0
        top_exit = max(d["exits"].items(), key=lambda kv: kv[1])[0] if d["exits"] else "-"
        lines.append(f"- {s}: trades={d['n']} win_rate={wr}% net_pnl=${round(d['pnl'],2)} top_exit={top_exit}")

    n_total = len(trades)
    stats = {"trades": n_total, "per_strategy": per}
    snapshot = (
        f"DATA SNAPSHOT (7-day window, generated {datetime.now(UTC).isoformat()[:19]}):\n"
        f"total closed trades: {n_total}\n\n"
        "PER-STRATEGY:\n" + ("\n".join(lines) if lines else "(no closed trades in the last 7 days)")
    )
    return snapshot, stats


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON in coach response")
    return json.loads(m.group(0))


async def weekly_review(db, settings) -> dict:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    snapshot, stats = await _gather(db)
    allowed = {k: {"current": getattr(settings, k, None), "min": v[0], "max": v[1], "means": v[2]}
               for k, v in APPLYABLE.items()}

    chat = LlmChat(api_key=api_key, session_id=f"coach-{datetime.now(UTC).date()}", system_message=SYSTEM_PROMPT)\
        .with_model(MODEL_PROVIDER, MODEL_NAME)
    user_text = (
        snapshot + "\n\nALLOWED_SETTINGS (key: current/min/max):\n"
        + "\n".join(f"- {k}: current={v['current']} range=[{v['min']},{v['max']}] ({v['means']})" for k, v in allowed.items())
        + "\n\nProduce the weekly review JSON now."
    )
    raw = await chat.send_message(UserMessage(text=user_text))
    review = _extract_json(str(raw))

    # sanitize recommendation against the whitelist
    rec = review.get("recommendation") or {}
    key = rec.get("setting_key") or ""
    val = rec.get("suggested_value")
    if key in APPLYABLE and isinstance(val, (int, float)):
        lo, hi, _ = APPLYABLE[key]
        rec["suggested_value"] = max(lo, min(hi, val))
        rec["current_value"] = getattr(settings, key, None)
        rec["applyable"] = True
    else:
        rec["applyable"] = False
        rec["setting_key"] = ""
    review["recommendation"] = rec
    review["stats"] = stats
    review["generated_at"] = datetime.now(UTC).isoformat()

    await db.coach_reviews.insert_one({**review, "ts": datetime.now(UTC)})
    return review


def validate_apply(setting_key: str, value) -> float | int:
    """Validate one Coach-recommended tweak.

    Two layers: (1) the Coach may only touch keys in APPLYABLE (a deliberately
    NARROW advisory whitelist), and (2) the value is additionally clamped to the
    global HARD bounds in settings_spec so it can never exceed a safe range even
    if the advisory band is later widened.
    """
    if setting_key not in APPLYABLE:
        raise ValueError(f"setting '{setting_key}' is not applyable")
    if not isinstance(value, (int, float)):
        raise ValueError("value must be numeric")
    lo, hi, _ = APPLYABLE[setting_key]
    clamped = max(lo, min(hi, value))
    # defense-in-depth: never exceed the global hard bounds (single source of truth)
    try:
        from settings_spec import clamp_value
        clamped = clamp_value(setting_key, clamped)
    except Exception:  # noqa: BLE001 — advisory clamp already applied above
        pass
    return int(clamped) if isinstance(APPLYABLE[setting_key][0], int) else float(clamped)



TRADES_REVIEW_PROMPT = (
    "You are Ananta's AI Trading Coach reviewing a batch of CLOSED trades. Use ONLY the DATA SNAPSHOT. "
    "Write a concise, plain-English performance review (4-7 short sentences or bullets): overall result, "
    "what worked, the biggest recurring weakness, and one concrete suggestion. Cite real numbers. "
    "No preamble, no disclaimers."
)


async def trades_review(db, mode: str) -> dict:
    """AI-written review of the closed trades for a given book ('paper' | 'live')."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    m = (mode or "paper").lower()
    mode_q = {"$in": ["PAPER", "DRY_RUN"]} if m == "paper" else "LIVE"
    trades = await db.trades.find(
        {"side": "SELL", "pnl": {"$ne": None}, "mode": mode_q}, {"_id": 0},
    ).sort("timestamp", -1).limit(300).to_list(300)

    if not trades:
        return {"mode": m, "trades": 0, "review": f"No closed {m} trades yet — run the engine to build a history to analyse."}

    wins = [t for t in trades if (t.get("pnl") or 0) > 0]
    total = round(sum((t.get("pnl") or 0) for t in trades), 2)
    wr = round(100 * len(wins) / len(trades), 1)
    per_strat: dict[str, dict] = {}
    exits: dict[str, int] = {}
    for t in trades:
        s = per_strat.setdefault(t.get("strategy") or "unknown", {"n": 0, "pnl": 0.0})
        s["n"] += 1
        s["pnl"] += t.get("pnl") or 0
        exits[t.get("exit_reason") or "-"] = exits.get(t.get("exit_reason") or "-", 0) + 1

    snapshot = (
        f"DATA SNAPSHOT ({m.upper()} book, {len(trades)} closed trades):\n"
        f"net_pnl=${total} win_rate={wr}% wins={len(wins)} losses={len(trades)-len(wins)}\n"
        "PER-STRATEGY: " + "; ".join(f"{k}: n={v['n']} pnl=${round(v['pnl'],2)}" for k, v in per_strat.items()) + "\n"
        "EXIT REASONS: " + "; ".join(f"{k}={n}" for k, n in sorted(exits.items(), key=lambda kv: -kv[1])[:6])
    )
    chat = LlmChat(api_key=api_key, session_id=f"trades-review-{m}-{datetime.now(UTC).date()}",
                   system_message=TRADES_REVIEW_PROMPT).with_model(MODEL_PROVIDER, MODEL_NAME)
    text = await chat.send_message(UserMessage(text=snapshot + "\n\nWrite the review now."))
    return {"mode": m, "trades": len(trades), "win_rate": wr, "net_pnl": total, "review": str(text)}


async def latest_headline(db) -> dict:
    """Credit-free Cockpit headline: surfaces the most recent stored Coach review's
    top recommendation. Does NOT call the LLM (safe to poll)."""
    doc = await db.coach_reviews.find_one({}, sort=[("ts", -1)])
    if not doc:
        return {"has_review": False, "headline": "Run a weekly AI review in Research \u2192 AI to get proactive tuning advice.",
                "impact": None, "confidence": None}
    rec = doc.get("recommendation") or {}
    title = rec.get("title") or doc.get("common_mistake") or "Review ready"
    return {
        "has_review": True,
        "headline": title,
        "impact": doc.get("estimated_impact"),
        "confidence": doc.get("confidence"),
        "setting_key": rec.get("setting_key") or "",
        "applyable": bool(rec.get("applyable")),
    }
