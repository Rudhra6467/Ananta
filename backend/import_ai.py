"""AI strategy extractor for the Import Pipeline (Claude via the Emergent LLM key).

Given raw strategy code (Pine Script / Freqtrade / Jesse / JSON) + a framework hint,
extract a fully-structured strategy definition AND a conversion report with a confidence
score. Same LlmChat pattern as library_ai.py / coach.py — one call, strict JSON out.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("ananta.import_ai")

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-6"
MAX_RAW = 16000

SYSTEM_PROMPT = (
    "You are Ananta's Strategy Import Analyst. You read a trading strategy written in an external "
    "framework and translate it into Ananta's internal strategy schema, then honestly report how well "
    "the conversion went. Ananta trades CRYPTO SPOT, long-biased, on 1H/4H/Daily timeframes with a "
    "universal exit engine (ATR trailing stops, profit-lock floors, structural stops).\n\n"
    "Extract EVERYTHING you can infer from the code: entry conditions, exit conditions, risk management, "
    "position sizing, indicators + their parameters, timeframes, and long/short support. Do NOT invent "
    "performance numbers. If something is ambiguous, make a reasonable inference and note it in the "
    "conversion report. Be modest with scores — poorly specified or exotic strategies score lower.\n\n"
    "Return STRICT JSON ONLY (no markdown, no prose) with EXACTLY this shape:\n"
    "{\n"
    '  "name": "concise strategy name",\n'
    '  "description": "1-2 sentence plain-English summary of what it does",\n'
    '  "category": one of ["Trend Following","Momentum","Mean Reversion","Volatility","Statistical / Quantitative","Academic / Institutional","Breakout","Scalping"],\n'
    '  "style": "short style label e.g. Trend Following / Breakout / Momentum",\n'
    '  "direction": "long" | "short" | "both",\n'
    '  "long_short_support": {"long": true|false, "short": true|false},\n'
    '  "timeframe": "primary TF e.g. 1H",\n'
    '  "timeframes": ["all TFs it supports"],\n'
    '  "market_type": ["Crypto" and/or "Stocks","Forex","Futures" ...],\n'
    '  "risk": "Conservative" | "Moderate" | "Aggressive",\n'
    '  "market_regimes": ["e.g. Trending","Bull Market","Sideways","High Volatility"],\n'
    '  "volatility_preference": "Low" | "Medium" | "High" | "Any",\n'
    '  "expected_holding_period": "e.g. Intraday / Hours / 1-3 days / Weeks",\n'
    '  "indicators": [{"name": "EMA", "params": {"period": 12}}],\n'
    '  "parameters": {"flat key/value tunables extracted from inputs/attrs"},\n'
    '  "entry_rules": ["human-readable bullet per entry condition"],\n'
    '  "exit_rules": ["human-readable bullet per exit condition"],\n'
    '  "risk_management": {"stop_loss_pct": number?, "take_profit_pct": number?, "trailing": bool?, "...": "..."},\n'
    '  "position_sizing": {"method": "fixed|percent|risk|...", "value": "..."},\n'
    '  "ideal_market": "when it works best",\n'
    '  "recommended_market": "which assets/markets suit it",\n'
    '  "ideal_conditions": ["..."],\n'
    '  "avoid_conditions": ["..."],\n'
    '  "strengths": ["..."],\n'
    '  "weaknesses": ["..."],\n'
    '  "tags": ["searchable tags"],\n'
    '  "ai_summary": "2-3 sentences: where it excels, where to avoid it",\n'
    '  "ai_health_score": integer 0-100,\n'
    '  "ai_confidence": integer 0-100,\n'
    '  "conversion": {\n'
    '     "confidence_score": integer 0-100 (how faithfully this maps onto Ananta),\n'
    '     "unsupported_features": ["framework features Ananta cannot replicate"],\n'
    '     "missing_logic": ["logic that was ambiguous or could not be fully extracted"],\n'
    '     "warnings": ["conversion caveats the user should review"],\n'
    '     "notes": "a detailed multi-sentence conversion report explaining the mapping decisions"\n'
    "  },\n"
    '  "declarative": {\n'
    '     "compilable": true|false,\n'
    '     "reason": "one sentence: why it is or is not compilable to Ananta rule engine",\n'
    '     "params": {"flat numeric tunables referenced by $name e.g. ema_fast: 12"},\n'
    '     "indicators": {"<id>": {"fn": "<supported fn>", "<param>": number_or_$ref}},\n'
    '     "entry": [{"lhs": "<operand>", "op": "<supported op>", "rhs": "<operand>"}],\n'
    '     "exit":  [{"lhs": "<operand>", "op": "<supported op>", "rhs": "<operand>"}],\n'
    '     "entry_reason": "short human-readable reason string"\n'
    "  }\n"
    "}\n\n"
    "DECLARATIVE COMPILER RULES (critical): entry conditions are AND-ed (all true), exit conditions "
    "are OR-ed (any true) and may be []. Use ONLY the primitives below; if the strategy needs anything "
    "else set declarative.compilable=false and still return your best-effort partial mapping.\n"
    "  Supported indicator fns + required params:\n"
    "    ema{period}, sma{period}, rsi{period}, atr{period}, macd_line{fast,slow}, "
    "macd_signal{fast,slow,signal}, macd_hist{fast,slow,signal}, bb_lower{period,std}, "
    "bb_upper{period,std}, bb_mid{period}, donchian_high{period}, donchian_low{period}, "
    "atr_breakout_level{period,k}, keltner_upper{ema_period,atr_period,mult}, "
    "keltner_mid{ema_period}, supertrend_dir{atr_period,multiplier}, supertrend_line{atr_period,multiplier}.\n"
    "  Supported ops: cross_above, cross_below, gt, lt, gte, lte, rising, falling.\n"
    "  Operands (lhs/rhs): an indicator id you defined | a price field (open/high/low/close/prev_close) "
    "| a number | a $paramName that MUST exist in declarative.params.\n"
    "  Ananta is LONG-ONLY spot: entry = the long trigger, exit = the flatten trigger."
)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON in AI extraction response")
    return json.loads(m.group(0))


async def analyze_strategy(raw: str, source_format: str, ai_hint: str,
                           name_hint: str | None = None) -> dict:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty strategy source")
    truncated = len(raw) > MAX_RAW
    body = raw[:MAX_RAW]

    prompt = (
        f"FRAMEWORK: {source_format}\n"
        f"HINT: {ai_hint}\n"
        + (f"NAME HINT: {name_hint}\n" if name_hint else "")
        + ("NOTE: source was truncated for length; extract from what is shown.\n" if truncated else "")
        + "\n--- STRATEGY SOURCE START ---\n" + body + "\n--- STRATEGY SOURCE END ---\n\n"
        "Return the extraction JSON now."
    )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"import-{source_format}-{datetime.now(UTC).timestamp()}",
        system_message=SYSTEM_PROMPT,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)
    raw_out = await chat.send_message(UserMessage(text=prompt))
    return _extract_json(str(raw_out))
