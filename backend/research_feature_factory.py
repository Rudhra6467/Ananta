"""Versioned, point-in-time feature factory and deterministic regime classifier."""
from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Any, Sequence

FEATURE_VERSION = "features-v2"
REGIME_VERSION = "regime-v1"


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    value = mean(values[:period])
    for x in values[period:]:
        value = alpha * x + (1 - alpha) * value
    return value


def _sma(values: Sequence[float], period: int) -> float | None:
    return mean(values[-period:]) if len(values) >= period else None


def _std(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    x = values[-period:]
    m = mean(x)
    return sqrt(sum((v - m) ** 2 for v in x) / period)


def _rsi(closes: Sequence[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))][-period:]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_gain, avg_loss = mean(gains), mean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(bars: Sequence[dict[str, Any]], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    tr = []
    for i in range(1, len(bars)):
        h, l = bars[i]["ohlcv"]["high"], bars[i]["ohlcv"]["low"]
        prev_c = bars[i - 1]["ohlcv"]["close"]
        tr.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return mean(tr[-period:]) if len(tr) >= period else None


def _adx_proxy(closes: Sequence[float], period: int = 14) -> float | None:
    """Stable trend-strength proxy; full Wilder ADX is added in a later feature version."""
    if len(closes) < period * 2:
        return None
    short = _ema(closes, period)
    long = _ema(closes, period * 2)
    if short is None or long in (None, 0):
        return None
    return min(100.0, abs(short - long) / long * 1000.0)


def build_feature_snapshot(*, bars: Sequence[dict[str, Any]], as_of, feature_version: str = FEATURE_VERSION) -> dict[str, Any]:
    eligible = sorted((b for b in bars if b["timestamp"] <= as_of), key=lambda b: b["timestamp"])
    if not eligible:
        raise ValueError("No bars available at or before as_of")
    closes = [float(b["ohlcv"]["close"]) for b in eligible]
    volumes = [float(b["ohlcv"]["volume"]) for b in eligible]
    latest = eligible[-1]
    c = closes[-1]
    sma20, sma50 = _sma(closes, 20), _sma(closes, 50)
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    atr14 = _atr(eligible, 14)
    vol20 = _std([(closes[i] / closes[i-1]) - 1 for i in range(1, len(closes))], 20)
    volume20 = _sma(volumes, 20)
    return {
        "feature_version": feature_version,
        "symbol": latest["symbol"], "timeframe": latest["timeframe"],
        "timestamp": latest["timestamp"], "as_of": as_of,
        "features": {
            "close": c,
            "return_1": c / closes[-2] - 1 if len(closes) >= 2 else None,
            "return_5": c / closes[-6] - 1 if len(closes) >= 6 else None,
            "return_20": c / closes[-21] - 1 if len(closes) >= 21 else None,
            "sma_20": sma20, "sma_50": sma50,
            "ema_12": ema12, "ema_26": ema26,
            "macd": (ema12 - ema26) if ema12 is not None and ema26 is not None else None,
            "rsi_14": _rsi(closes, 14),
            "atr_14": atr14,
            "atr_pct": atr14 / c if atr14 is not None and c else None,
            "trend_strength_proxy": _adx_proxy(closes),
            "realized_vol_20": vol20,
            "volume_ratio_20": volumes[-1] / volume20 if volume20 else None,
            "range_pct": (latest["ohlcv"]["high"] - latest["ohlcv"]["low"]) / c if c else None,
            "distance_sma20": c / sma20 - 1 if sma20 else None,
            "distance_sma50": c / sma50 - 1 if sma50 else None,
        },
        "source_bar_key": latest["key"],
    }


def classify_regime(snapshot: dict[str, Any], regime_version: str = REGIME_VERSION) -> dict[str, Any]:
    f = snapshot["features"]
    trend = f.get("trend_strength_proxy")
    d20, d50 = f.get("distance_sma20"), f.get("distance_sma50")
    vol = f.get("realized_vol_20")
    rsi = f.get("rsi_14")
    if None in (trend, d20, d50, vol, rsi):
        label = "INSUFFICIENT_DATA"
    elif vol >= 0.04:
        label = "HIGH_VOL"
    elif trend >= 12 and d20 > 0 and d50 > 0:
        label = "TREND_UP"
    elif trend >= 12 and d20 < 0 and d50 < 0:
        label = "TREND_DOWN"
    elif vol <= 0.012 and abs(d20) <= 0.02:
        label = "COMPRESSION"
    elif abs(d20) <= 0.03 and 40 <= rsi <= 60:
        label = "RANGE"
    elif d20 > 0 and rsi >= 65:
        label = "MOMENTUM_UP"
    elif d20 < 0 and rsi <= 35:
        label = "MOMENTUM_DOWN"
    else:
        label = "NEUTRAL"
    return {"regime_version": regime_version, "regime": label, "feature_version": snapshot["feature_version"]}


async def persist_feature_and_regime(db, snapshot: dict[str, Any], regime: dict[str, Any]) -> None:
    key = "|".join([snapshot["symbol"], snapshot["timeframe"], snapshot["timestamp"].isoformat(), snapshot["feature_version"]])
    await db.research_market_features.update_one({"snapshot_id": key}, {"$set": {**snapshot, "snapshot_id": key}}, upsert=True)
    regime_key = "|".join([snapshot["symbol"], snapshot["timeframe"], snapshot["timestamp"].isoformat(), regime["regime_version"]])
    await db.research_market_context.update_one({"context_id": regime_key}, {"$set": {**regime, "context_id": regime_key, "symbol": snapshot["symbol"], "timeframe": snapshot["timeframe"], "timestamp": snapshot["timestamp"], "as_of": snapshot["as_of"]}}, upsert=True)


__all__ = ["FEATURE_VERSION", "REGIME_VERSION", "build_feature_snapshot", "classify_regime", "persist_feature_and_regime"]
