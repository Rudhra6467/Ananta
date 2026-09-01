"""Deterministic feature engineering for research observations.

Only bars at or before ``as_of`` are used. This makes the feature snapshot suitable
for point-in-time backtests and later live/replay comparison.
"""
from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Any, Sequence


def _returns(closes: Sequence[float]) -> list[float]:
    return [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes)) if closes[i - 1] != 0]


def _sma(values: Sequence[float], n: int) -> float | None:
    return mean(values[-n:]) if len(values) >= n else None


def _std(values: Sequence[float], n: int) -> float | None:
    if len(values) < n:
        return None
    x = values[-n:]
    m = mean(x)
    return sqrt(sum((v - m) ** 2 for v in x) / n)


def build_feature_snapshot(
    *, bars: Sequence[dict[str, Any]], as_of, feature_version: str = "features-v1"
) -> dict[str, Any]:
    """Build a reproducible feature snapshot from historical bars only."""
    eligible = [b for b in bars if b["timestamp"] <= as_of]
    if not eligible:
        raise ValueError("No bars available at or before as_of")
    eligible = sorted(eligible, key=lambda b: b["timestamp"])
    closes = [float(b["ohlcv"]["close"]) for b in eligible]
    volumes = [float(b["ohlcv"]["volume"]) for b in eligible]
    latest = eligible[-1]
    c = closes[-1]
    r = _returns(closes)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    vol20 = _std(r, 20)
    volume20 = _sma(volumes, 20)
    return {
        "feature_version": feature_version,
        "symbol": latest["symbol"],
        "timeframe": latest["timeframe"],
        "timestamp": latest["timestamp"],
        "as_of": as_of,
        "features": {
            "close": c,
            "return_1": r[-1] if r else None,
            "return_5": (c / closes[-6] - 1.0) if len(closes) >= 6 and closes[-6] else None,
            "return_20": (c / closes[-21] - 1.0) if len(closes) >= 21 and closes[-21] else None,
            "sma_20": sma20,
            "sma_50": sma50,
            "distance_sma20": (c / sma20 - 1.0) if sma20 else None,
            "distance_sma50": (c / sma50 - 1.0) if sma50 else None,
            "realized_vol_20": vol20,
            "volume_ratio_20": (volumes[-1] / volume20) if volume20 else None,
            "range_pct": ((latest["ohlcv"]["high"] - latest["ohlcv"]["low"]) / c) if c else None,
        },
        "source_bar_key": latest["key"],
    }


async def persist_feature_snapshot(db, snapshot: dict[str, Any]) -> None:
    """Persist a feature snapshot under its point-in-time identity."""
    key = "|".join([
        snapshot["symbol"], snapshot["timeframe"],
        snapshot["timestamp"].isoformat(), snapshot["feature_version"],
    ])
    document = {**snapshot, "snapshot_id": key}
    await db.research_market_features.update_one(
        {"snapshot_id": key}, {"$set": document}, upsert=True
    )


__all__ = ["build_feature_snapshot", "persist_feature_snapshot"]
