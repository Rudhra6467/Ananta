"""Research regime definitions and transition helpers.

Regime labels are research labels, not trading signals. Their purpose is to segment
historical evidence so strategy performance can be conditioned on market state.
"""
from __future__ import annotations

REGIME_LABELS = (
    "TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "HIGH_VOL",
    "MOMENTUM_UP", "MOMENTUM_DOWN", "NEUTRAL", "INSUFFICIENT_DATA",
)


def transition(previous: str | None, current: str) -> dict[str, str | bool | None]:
    return {
        "previous_regime": previous,
        "current_regime": current,
        "changed": previous is not None and previous != current,
    }


def regime_family(label: str) -> str:
    if label in {"TREND_UP", "TREND_DOWN", "MOMENTUM_UP", "MOMENTUM_DOWN"}:
        return "TREND"
    if label in {"HIGH_VOL", "COMPRESSION"}:
        return "VOLATILITY"
    if label == "RANGE":
        return "MEAN_REVERSION"
    if label == "INSUFFICIENT_DATA":
        return "UNKNOWN"
    return "NEUTRAL"


__all__ = ["REGIME_LABELS", "transition", "regime_family"]
