"""AI grading for Strategy Library entries (Claude via Emergent LLM key).

Given a strategy's logic + seeded historical results, produce a grounded AI summary,
a 0–100 health score, a letter grade and a confidence. Same LlmChat pattern as coach.py.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("ananta.library_ai")

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You are Ananta's Quant Strategy Rater. You evaluate a trading strategy from its logic and "
    "backtest results and return a grounded rating. Use ONLY the data provided; never invent numbers.\n"
    "Return STRICT JSON only (no markdown) with this exact shape:\n"
    "{\n"
    '  "ai_summary": "2-3 sentences: where it excels and where to avoid it, citing the metrics",\n'
    '  "ai_health_score": <integer 0-100>,\n'
    '  "ai_confidence": <integer 0-100>\n'
    "}\n"
    "Weigh risk-adjusted return (Sharpe/Sortino), profit factor, drawdown and sample size. "
    "Be honest and modest: weak or small-sample strategies score lower."
)

_GRADE = [(85, "A"), (70, "B"), (55, "C"), (40, "D")]


def _grade(score: int) -> str:
    for lo, g in _GRADE:
        if score >= lo:
            return g
    return "E"


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON in AI grade response")
    return json.loads(m.group(0))


async def grade_strategy(doc: dict) -> dict:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    r = doc.get("historical_results") or {}
    snapshot = (
        f"STRATEGY: {doc.get('name')} ({doc.get('style')} / {doc.get('category')})\n"
        f"Source: {doc.get('source')}\nDescription: {doc.get('description')}\n"
        f"Ideal market: {doc.get('ideal_market')} | Regimes: {', '.join(doc.get('market_regimes') or [])}\n"
        f"Timeframe: {doc.get('timeframe')} | Risk: {doc.get('risk')}\n"
        f"Entry rules: {'; '.join(doc.get('entry_rules') or [])}\n"
        f"Exit rules: {'; '.join(doc.get('exit_rules') or [])}\n"
        f"Ideal conditions: {', '.join(doc.get('ideal_conditions') or [])}\n"
        f"Avoid conditions: {', '.join(doc.get('avoid_conditions') or [])}\n"
        "BACKTEST RESULTS:\n"
        f"  ROI: {r.get('roi')}%  WinRate: {r.get('win_rate')}%  ProfitFactor: {r.get('profit_factor')}\n"
        f"  Sharpe: {r.get('sharpe')}  Sortino: {r.get('sortino')}  MaxDD: {r.get('max_drawdown')}%\n"
        f"  AvgTrade: {r.get('avg_trade')}%  Trades: {r.get('trade_count')}\n"
    )
    chat = LlmChat(api_key=api_key, session_id=f"lib-grade-{doc.get('id')}-{datetime.now(UTC).date()}",
                   system_message=SYSTEM_PROMPT).with_model(MODEL_PROVIDER, MODEL_NAME)
    raw = await chat.send_message(UserMessage(text=snapshot + "\n\nReturn the rating JSON now."))
    out = _extract_json(str(raw))
    score = max(0, min(100, int(out.get("ai_health_score", 0))))
    conf = max(0, min(100, int(out.get("ai_confidence", 0))))
    return {
        "ai_summary": str(out.get("ai_summary", "")).strip(),
        "ai_health_score": score,
        "ai_grade": _grade(score),
        "ai_confidence": conf,
    }
