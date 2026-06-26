"""
Layer 4 - AI Macro Context Engine.
Calls Gemini 3 Pro (via Emergent Universal LLM Key + emergentintegrations) to analyze
a news summary string and return structured BIAS / CONFIDENCE / REASON.

Includes an MD5 payload cache so identical news payloads do not re-spend LLM
tokens — the previous decision is reused verbatim.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from typing import Literal

from emergentintegrations.llm.chat import LlmChat, UserMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.1-pro-preview"

# Per-symbol MD5 cache of (payload_hash -> MacroBias). One slot per symbol so
# stale-news skips the API call until the news actually updates.
_LAST_CALL_CACHE: dict[str, tuple[str, "MacroBias"]] = {}


def _payload_hash(symbol: str, news_summary: str, sector_context: str = "") -> str:
    """MD5 the inputs that drive the LLM decision. Used to dedupe successive
    identical calls (huge token savings when news_source returns the same
    summary multiple cycles in a row)."""
    raw = f"{symbol}\n--\n{news_summary or ''}\n--\n{sector_context or ''}".encode("utf-8")
    return hashlib.md5(raw, usedforsecurity=False).hexdigest()


def clear_macro_cache() -> None:
    """For tests."""
    _LAST_CALL_CACHE.clear()


class MacroBias(BaseModel):
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    model: str = DEFAULT_MODEL


SYSTEM_PROMPT = """You are Ananta.AI, a disciplined, risk-aware SPOT-only MULTI-ASSET macro analyst
for an algorithmic paper-trading bot. You analyze ONE asset per call across several asset classes
(Layer-1 crypto, DeFi protocol tokens, and tokenized gold) and decide its directional bias.

Strict rules:
- You are NOT a profit oracle. Capital preservation > opportunism. Spot only, no leverage.
- Weigh the ASSET-CLASS CONTEXT provided (on-chain TVL for L1, protocol TVL for DeFi, macro/inflation
  for gold). If that context says data is UNAVAILABLE, do NOT invent figures — reason qualitatively
  from the headlines or return NEUTRAL with low confidence.
- For tokenized GOLD (PAXG): crypto headlines are mostly noise; lean on the macro prints (gold rises
  on falling real rates, rising inflation, a weak USD, and risk-off sentiment).
- If signals are mixed, contradictory, or low-information, return NEUTRAL with low confidence.
- Confidence must reflect *information quality*, not enthusiasm. Lower is safer.
- Your REASON must be concise (1-3 sentences), explainable, and grounded in the inputs.

Return ONLY a JSON object with this exact shape, no markdown, no commentary:
{
  "bias": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <float 0.0..1.0>,
  "reason": "<short explainable reason>"
}
"""


def _extract_json(text: str) -> dict | None:
    """Robustly pull a JSON object from an LLM response."""
    if not text:
        return None
    # try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # try to find a JSON object in the text
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def analyze_macro(
    symbol: str, news_summary: str, sector_context: str = "", model: str = DEFAULT_MODEL,
) -> MacroBias:
    """Ask Gemini for a structured macro bias.
    Falls back to a NEUTRAL low-confidence result if anything goes wrong (defensive).

    Caches the (symbol, news_summary, sector_context) MD5 → previous MacroBias to
    skip the LLM call entirely when the payload hasn't changed since the last cycle.
    """
    payload_hash = _payload_hash(symbol, news_summary, sector_context)
    cached = _LAST_CALL_CACHE.get(symbol)
    if cached and cached[0] == payload_hash:
        logger.info("macro cache HIT for %s (hash=%s...) - reusing prior result", symbol, payload_hash[:8])
        return cached[1]

    api_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        logger.error("EMERGENT_LLM_KEY missing - returning safe NEUTRAL")
        return MacroBias(bias="NEUTRAL", confidence=0.0, reason="LLM key not configured. Defaulting to NEUTRAL for safety.", model=model)

    user_text = (
        f"Asset: {symbol}\n"
        f"Asset-Class Context:\n{sector_context or '(none provided)'}\n\n"
        f"Market/News Summary:\n{news_summary}\n\n"
        f"Return the JSON object now."
    )

    try:
        # fresh session per call - we manage history ourselves in MongoDB
        session_id = f"macro-{uuid.uuid4().hex}"
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=SYSTEM_PROMPT,
        ).with_model("gemini", model)

        response = await chat.send_message(UserMessage(text=user_text))
        data = _extract_json(response)
        if not data:
            logger.warning("Could not parse LLM JSON; raw=%s", response[:200] if response else None)
            return MacroBias(bias="NEUTRAL", confidence=0.1, reason="LLM returned unparseable output. Defaulting to NEUTRAL.", model=model)

        bias = str(data.get("bias", "NEUTRAL")).upper()
        if bias not in ("BULLISH", "BEARISH", "NEUTRAL"):
            bias = "NEUTRAL"
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        reason = str(data.get("reason", "")).strip() or "No reason provided."
        result = MacroBias(bias=bias, confidence=confidence, reason=reason, model=model)
        _LAST_CALL_CACHE[symbol] = (payload_hash, result)
        return result
    except Exception as e:
        logger.exception("LLM call failed: %s", e)
        return MacroBias(bias="NEUTRAL", confidence=0.0, reason=f"LLM error: {type(e).__name__}. Defaulting to NEUTRAL.", model=model)
