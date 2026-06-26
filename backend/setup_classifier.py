"""
Setup classifier — distinguishes STRONG (pump) setups from NORMAL ones so the
position sizer can pick a bigger lot when conviction + trend + volatility all
agree.

STRONG = ALL of (strict AND):
  * LLM macro confidence ≥ 0.80
  * 1h trend aligned for longs: last close > EMA50 > EMA200
  * 1h volatility check: ATR percentile ≥ 60% of last 30 days OR 1h ADX ≥ 20

Anything else that still passes fusion = NORMAL.
"""
from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

SetupStrength = Literal["STRONG", "NORMAL", "NONE"]


# ---------------- pure indicator math ------------------------------------
def ema(values: list[float], period: int) -> list[float]:
    """Exponential moving average. Result is same length as input."""
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(alpha * float(v) + (1 - alpha) * out[-1])
    return out


def rsi(closes: list[float], period: int = 14) -> list[float]:
    """Wilder's RSI. Returns a list (last element = current RSI); empty if there
    is insufficient data. Used by the primary layer's momentum-reset gate."""
    if len(closes) < period + 1:
        return []
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))

    def _rsi(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - 100.0 / (1.0 + rs)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out = [_rsi(avg_gain, avg_loss)]
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out.append(_rsi(avg_gain, avg_loss))
    return out



def true_range(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    n = len(closes)
    out = [highs[0] - lows[0]] if n else []
    for i in range(1, n):
        h_l = highs[i] - lows[i]
        h_pc = abs(highs[i] - closes[i - 1])
        l_pc = abs(lows[i] - closes[i - 1])
        out.append(max(h_l, h_pc, l_pc))
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    """Wilder's ATR. Returns a list same length as inputs; warmup values are
    simple averages until we have `period` data points."""
    tr = true_range(highs, lows, closes)
    n = len(tr)
    if n == 0:
        return []
    out = [tr[0]]
    for i in range(1, n):
        if i < period:
            out.append(sum(tr[: i + 1]) / (i + 1))
        else:
            out.append((out[-1] * (period - 1) + tr[i]) / period)
    return out


def _wilder_smooth(values: list[float], period: int) -> list[float]:
    """Wilder's smoothing: smooth[i] = smooth[i-1] + (v[i] - smooth[i-1]) / period."""
    n = len(values)
    if n == 0:
        return []
    out = [values[0]]
    for i in range(1, n):
        out.append(out[-1] + (values[i] - out[-1]) / period)
    return out


def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    """Wilder's ADX. Returns one value per bar (warmup bars are 0)."""
    n = len(closes)
    if n < 2:
        return [0.0] * n
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm.append(up if up > dn and up > 0 else 0.0)
        minus_dm.append(dn if dn > up and dn > 0 else 0.0)

    tr = true_range(highs, lows, closes)
    smoothed_tr = _wilder_smooth(tr, period)
    smoothed_plus = _wilder_smooth(plus_dm, period)
    smoothed_minus = _wilder_smooth(minus_dm, period)

    plus_di: list[float] = []
    minus_di: list[float] = []
    for i in range(n):
        denom = smoothed_tr[i] if smoothed_tr[i] > 0 else 1e-9
        plus_di.append(100.0 * smoothed_plus[i] / denom)
        minus_di.append(100.0 * smoothed_minus[i] / denom)

    dx: list[float] = []
    for i in range(n):
        s = plus_di[i] + minus_di[i]
        if s == 0:
            dx.append(0.0)
        else:
            dx.append(100.0 * abs(plus_di[i] - minus_di[i]) / s)

    return _wilder_smooth(dx, period)


def percentile_rank(series: list[float], value: float) -> float:
    """Percent of `series` values that are ≤ `value`. 0-100."""
    if not series:
        return 0.0
    below = sum(1 for x in series if x <= value)
    return below / len(series) * 100.0


# ---------------- the classifier ----------------------------------------
def classify_setup(
    bars_1h: list[list[float]],
    macro_confidence: float,
    macro_bias: str,
    *,
    min_strong_confidence: float = 0.80,
    min_atr_percentile: float = 60.0,
    min_adx: float = 20.0,
    atr_lookback_bars: int = 720,  # 30 days × 24h
) -> tuple[SetupStrength, dict]:
    """Classify the setup quality for a LONG entry.

    Spot only - we never short. SELL decisions are not classified here.

    Returns (strength, evidence). Always returns valid output even with
    insufficient history (degrades to NORMAL with a note).
    """
    evidence: dict = {
        "min_strong_confidence": min_strong_confidence,
        "min_atr_percentile": min_atr_percentile,
        "min_adx": min_adx,
    }

    # If macro isn't bullish, no point even classifying - fusion will HOLD.
    if macro_bias != "BULLISH":
        evidence["reason"] = f"macro bias is {macro_bias}, not BULLISH"
        return "NONE", evidence

    if not bars_1h or len(bars_1h) < 200:
        evidence["reason"] = f"insufficient 1h history ({len(bars_1h) if bars_1h else 0} bars, need 200+)"
        evidence["macro_confidence"] = round(macro_confidence, 3)
        # Conservative: classify as NORMAL so the bot can still trade small
        return "NORMAL", evidence

    highs = [b[2] for b in bars_1h]
    lows = [b[3] for b in bars_1h]
    closes = [b[4] for b in bars_1h]

    last_close = closes[-1]
    ema50 = ema(closes, 50)[-1]
    ema200 = ema(closes, 200)[-1]
    trend_aligned = last_close > ema50 > ema200

    atr_series = atr(highs, lows, closes, 14)
    current_atr = atr_series[-1]
    lookback = min(atr_lookback_bars, len(atr_series))
    atr_recent = atr_series[-lookback:]
    atr_pct = percentile_rank(atr_recent, current_atr)
    atr_ok = atr_pct >= min_atr_percentile

    adx_series = adx(highs, lows, closes, 14)
    adx_value = adx_series[-1]
    adx_ok = adx_value >= min_adx

    volatility_ok = atr_ok or adx_ok
    confidence_ok = macro_confidence >= min_strong_confidence

    evidence.update({
        "last_close": round(last_close, 4),
        "ema50": round(ema50, 4),
        "ema200": round(ema200, 4),
        "trend_aligned_long": trend_aligned,
        "atr_value": round(current_atr, 6),
        "atr_percentile": round(atr_pct, 2),
        "atr_above_threshold": atr_ok,
        "adx_value": round(adx_value, 2),
        "adx_above_threshold": adx_ok,
        "volatility_ok": volatility_ok,
        "macro_confidence": round(macro_confidence, 3),
        "confidence_above_threshold": confidence_ok,
    })

    is_strong = confidence_ok and trend_aligned and volatility_ok
    if is_strong:
        return "STRONG", evidence

    # Which leg failed? Add a one-line reason for the operator log.
    missing = []
    if not confidence_ok:
        missing.append(f"conf {macro_confidence:.2f} < {min_strong_confidence}")
    if not trend_aligned:
        missing.append(
            f"1h trend not aligned (close={last_close:.2f}, ema50={ema50:.2f}, ema200={ema200:.2f})"
        )
    if not volatility_ok:
        missing.append(
            f"volatility floor not met (atr_pct={atr_pct:.1f}% < {min_atr_percentile}, "
            f"adx={adx_value:.1f} < {min_adx})"
        )
    evidence["downgrade_reason"] = "; ".join(missing) if missing else "n/a"
    return "NORMAL", evidence
