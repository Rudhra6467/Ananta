"""
router.py — Regime-First Strategy Router (Phase E2, pure compute).

Formalises "What market am I looking at?" -> "Which alpha models may act?".
The engine classifies the regime first, then asks the router which INDEPENDENT
models are eligible. Hunter and Squeeze are the active executors; the rest are
shadow models that may still log hypotheses.

This makes the regime -> strategy mapping first-class and visible in the Reason
Chain. It does not place orders — each model owns its own entry logic.
"""
from __future__ import annotations

# Active executors per regime (independent traders).
# Deep-research restriction (tightened): each core model trades ONLY in the regime where it
# has a demonstrated edge, and NEUTRAL/RANGE/TREND_DOWN are stood down entirely.
#   Hunter       -> REVERSAL only ("buys fear" after acceptance)
#   Squeeze      -> COMPRESSION only (volatility coil -> expansion)
#   Continuation -> TREND_UP only (gated further by the 4H trend filter, htf_trend_enabled)
#   NEUTRAL / RANGE / TREND_DOWN -> NO trading (stand aside)
_REGIME_MAP: dict[str, list[str]] = {
    "TREND_UP": ["continuation"],   # continuation only, behind the 4H trend filter
    "REVERSAL": ["hunter"],         # stabilized / deep-discount reversal
    "COMPRESSION": ["squeeze"],     # volatility coil -> expansion
    "RANGE": [],                    # stand aside — squeeze restricted to COMPRESSION
    "NEUTRAL": [],                  # BLOCKED — no trading in a mixed/undecided market
    "TREND_DOWN": [],               # no long executors in a confirmed downtrend
}

_RATIONALE: dict[str, str] = {
    "TREND_UP": "Strong uptrend — Continuation buys shallow dips to the 20-EMA (4H trend filter required).",
    "REVERSAL": "Oversold/panic — Hunter buys fear after acceptance.",
    "COMPRESSION": "Volatility coiled — Squeeze waits for a confirmed expansion.",
    "RANGE": "Low-trend range — no eligible executor; standing aside.",
    "NEUTRAL": "Mixed / undecided — trading BLOCKED until the regime resolves.",
    "TREND_DOWN": "Confirmed downtrend — no long executors active.",
}

ACTIVE_EXECUTORS = ("hunter", "squeeze", "continuation")


def route(regime_label: str | None) -> dict:
    """Return the eligible active models for a regime + a human rationale."""
    label = regime_label or "NEUTRAL"
    eligible = _REGIME_MAP.get(label, [])  # unknown/blocked regimes -> stand aside
    return {
        "regime": label,
        "eligible_models": eligible,
        "rationale": _RATIONALE.get(label, "Default routing."),
    }


def hunter_allowed(regime_label: str | None) -> bool:
    return "hunter" in route(regime_label)["eligible_models"]


def squeeze_allowed(regime_label: str | None) -> bool:
    return "squeeze" in route(regime_label)["eligible_models"]


def continuation_allowed(regime_label: str | None) -> bool:
    return "continuation" in route(regime_label)["eligible_models"]
