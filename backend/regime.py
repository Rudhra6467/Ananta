"""
regime.py — Market Regime Classifier (Phase E, pure compute, ZERO LLM credits).

Answers "What market am I looking at?" BEFORE any strategy activates. The router
uses the regime to pick which independent alpha model (Hunter / Squeeze) is even
allowed to act, and Hunter uses it to choose an entry profile.

Regimes: TREND_UP / TREND_DOWN / RANGE / COMPRESSION / REVERSAL / NEUTRAL.

Built from the asset's own 4h bars using indicators already in setup_classifier.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from setup_classifier import adx, atr, ema, percentile_rank, rsi

# 4h bar layout: [ts, open, high, low, close, volume]
_H, _L, _C = 2, 3, 4


@dataclass
class Regime:
    regime: str
    strong_uptrend: bool        # bullish EMA stack + HH/HL + ADX trend
    panic: bool                 # capitulation: extreme oversold + ATR expansion
    compression: bool           # Bollinger/ATR volatility collapse
    evidence: dict = field(default_factory=dict)


def _bbwidth_series(closes: list[float], period: int = 20, k: float = 2.0) -> list[float]:
    out: list[float] = []
    for i in range(len(closes)):
        if i < period - 1:
            continue
        w = closes[i - period + 1:i + 1]
        m = sum(w) / period
        sd = (sum((c - m) ** 2 for c in w) / period) ** 0.5
        out.append((2 * k * sd) / m * 100.0 if m else 0.0)
    return out


def _structure(highs: list[float], lows: list[float], half: int = 20) -> tuple[bool, bool]:
    """Crude swing structure: compare the most-recent `half` window to the prior one.
    Returns (higher_high_higher_low, lower_high_lower_low)."""
    if len(highs) < half * 2:
        return False, False
    recent_h, prev_h = highs[-half:], highs[-2 * half:-half]
    recent_l, prev_l = lows[-half:], lows[-2 * half:-half]
    hh_hl = max(recent_h) > max(prev_h) and min(recent_l) > min(prev_l)
    lh_ll = max(recent_h) < max(prev_h) and min(recent_l) < min(prev_l)
    return hh_hl, lh_ll


def classify_regime(bars_4h: list[list[float]]) -> Regime:
    if not bars_4h or len(bars_4h) < 60:
        return Regime("NEUTRAL", False, False, False, {"reason": "insufficient_bars"})

    closes = [b[_C] for b in bars_4h]
    highs = [b[_H] for b in bars_4h]
    lows = [b[_L] for b in bars_4h]
    try:
        r = rsi(closes, 14)[-1]
        ema20 = ema(closes, 20)[-1]
        ema50 = ema(closes, 50)[-1]
        ema200 = ema(closes, 200)[-1] if len(closes) >= 200 else ema(closes, 50)[-1]
        adx_val = adx(highs, lows, closes)[-1]
        atr_series = atr(highs, lows, closes)
        atr_pct = percentile_rank(atr_series, atr_series[-1])
        bbw = _bbwidth_series(closes)
        bbw_pct = percentile_rank(bbw, bbw[-1]) if len(bbw) > 5 else 100.0
        price = closes[-1]
    except Exception:
        return Regime("NEUTRAL", False, False, False, {"reason": "indicator_error"})

    hh_hl, lh_ll = _structure(highs, lows)
    ema_stack_up = ema20 > ema50 > ema200
    ema_stack_down = ema20 < ema50 < ema200

    strong_uptrend = bool(ema_stack_up and price > ema20 and adx_val >= 20.0 and hh_hl)
    panic = bool(r <= 22.0 and atr_pct >= 70.0)
    compression = bool((bbw_pct <= 30.0 and atr_pct <= 35.0) or atr_pct <= 10.0)

    # Priority: compression > reversal(panic) > strong trends > range > neutral.
    if compression:
        regime = "COMPRESSION"
    elif panic or (r <= 32.0 and (ema_stack_down or lh_ll)):
        regime = "REVERSAL"
    elif strong_uptrend:
        regime = "TREND_UP"
    elif ema_stack_down and adx_val >= 20.0:
        regime = "TREND_DOWN"
    elif adx_val < 20.0:
        regime = "RANGE"
    else:
        regime = "NEUTRAL"

    return Regime(
        regime, strong_uptrend, panic, compression,
        {
            "rsi": round(r, 2),
            "adx": round(adx_val, 2),
            "atr_percentile": round(atr_pct, 1),
            "bbwidth_percentile": round(bbw_pct, 1),
            "ema_stack": "UP" if ema_stack_up else "DOWN" if ema_stack_down else "MIXED",
            "higher_high_higher_low": hh_hl,
            "lower_high_lower_low": lh_ll,
        },
    )
