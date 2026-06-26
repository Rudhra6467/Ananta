"""
squeeze.py — Volatility Squeeze, an INDEPENDENT alpha model (Phase E, pure compute).

Personality: "I buy expansion." Completely separate from the Hunter ("I buy fear").

Trigger : Bollinger Bands fully INSIDE Keltner Channels (volatility coiled).
Entry   : NOT the first breakout candle (highest false-break rate). Instead:
            - CONTINUATION: breakout candle -> small inside candle -> break of the
              inside candle's high, OR
            - RETEST: breakout, pull back toward the basis (20-MA), then reclaim.
Stop    : hard stop at the 20-period MA (Bollinger basis).
Trail   : ATR-based dynamic trail (handled by the existing position watcher).

Pure compute, ZERO LLM credits. Risk is defined by the exit engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from setup_classifier import atr, ema, percentile_rank

# 4h bar layout: [ts, open, high, low, close, volume]
_O, _H, _L, _C, _V = 1, 2, 3, 4, 5

BB_PERIOD = 20
BB_K = 2.0
KC_MULT = 1.5
SQUEEZE_LOOKBACK = 8      # squeeze must have been ON within this many recent bars
BREAKOUT_WINDOW = 4       # breakout candle must be within this many recent bars
VOL_SPIKE_MULT = 1.5      # breakout volume must exceed this * 20-bar avg


@dataclass
class SqueezeSignal:
    triggered: bool
    entry_profile: str | None      # RETEST | CONTINUATION | None
    stop_20ma: float | None
    evidence: dict = field(default_factory=dict)


def _sma(vals: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(vals)):
        if i < period - 1:
            out.append(None)
        else:
            out.append(sum(vals[i - period + 1:i + 1]) / period)
    return out


def _stdev(vals: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(vals)):
        if i < period - 1:
            out.append(None)
            continue
        w = vals[i - period + 1:i + 1]
        m = sum(w) / period
        out.append((sum((c - m) ** 2 for c in w) / period) ** 0.5)
    return out


def evaluate_squeeze(bars_4h: list[list[float]]) -> SqueezeSignal:
    n = len(bars_4h or [])
    if n < BB_PERIOD + BREAKOUT_WINDOW + 2:
        return SqueezeSignal(False, None, None, {"reason": "insufficient_bars", "bars": n})

    closes = [b[_C] for b in bars_4h]
    highs = [b[_H] for b in bars_4h]
    lows = [b[_L] for b in bars_4h]
    vols = [b[_V] for b in bars_4h]

    basis = _sma(closes, BB_PERIOD)            # 20-MA == Bollinger basis == stop
    sd = _stdev(closes, BB_PERIOD)
    atr_series = atr(highs, lows, closes)
    ema20 = ema(closes, BB_PERIOD)

    def bb_upper(i):
        return basis[i] + BB_K * sd[i] if basis[i] is not None and sd[i] is not None else None

    def bb_lower(i):
        return basis[i] - BB_K * sd[i] if basis[i] is not None and sd[i] is not None else None

    def kc_upper(i):
        a = atr_series[i] if i < len(atr_series) else None
        return ema20[i] + KC_MULT * a if a is not None else None

    def kc_lower(i):
        a = atr_series[i] if i < len(atr_series) else None
        return ema20[i] - KC_MULT * a if a is not None else None

    def squeeze_on(i):
        bu, bl, ku, kl = bb_upper(i), bb_lower(i), kc_upper(i), kc_lower(i)
        if None in (bu, bl, ku, kl):
            return False
        return bu < ku and bl > kl

    last = n - 1
    # 1) squeeze must have coiled recently
    coiled = any(squeeze_on(i) for i in range(max(0, last - SQUEEZE_LOOKBACK), last))
    # avg volume baseline
    vol_avg = sum(vols[-BB_PERIOD:]) / BB_PERIOD if len(vols) >= BB_PERIOD else (sum(vols) / len(vols))

    # 2) find the most recent breakout candle (closed above its BB upper w/ volume spike)
    breakout_idx = None
    for i in range(last, max(0, last - BREAKOUT_WINDOW) - 1, -1):
        bu = bb_upper(i)
        if bu is None:
            continue
        if closes[i] > bu and vols[i] > vol_avg * VOL_SPIKE_MULT:
            breakout_idx = i
            break

    stop_20ma = round(basis[last], 8) if basis[last] is not None else None
    ev = {
        "coiled_recently": coiled,
        "breakout_idx_from_end": (last - breakout_idx) if breakout_idx is not None else None,
        "stop_20ma": stop_20ma,
        "vol_avg_20": round(vol_avg, 4),
    }

    # Need a coil AND a confirmed breakout that is NOT the current candle (don't chase).
    if not coiled or breakout_idx is None or breakout_idx >= last:
        return SqueezeSignal(False, None, stop_20ma, {**ev, "reason": "no_confirmed_setup"})

    bo_close = closes[breakout_idx]
    bo_high = highs[breakout_idx]
    bo_upper = bb_upper(breakout_idx)
    vol_spike_ratio = round(vols[breakout_idx] / vol_avg, 3) if vol_avg else None
    breakout_strength_pct = round((bo_close - bo_upper) / bo_upper * 100.0, 4) if bo_upper else None

    profile = None

    # CONTINUATION: an inside candle after the breakout, then current breaks its high.
    for j in range(breakout_idx + 1, last):
        inside = highs[j] <= highs[j - 1] and lows[j] >= lows[j - 1]
        if inside and closes[last] > highs[j]:
            profile = "CONTINUATION"
            break

    # RETEST: price pulled back toward/through the 20-MA basis after the breakout,
    # then the current candle reclaims (closes back above the breakout candle high).
    if profile is None and stop_20ma is not None:
        pulled_back = any(lows[k] <= basis[k] * 1.005 for k in range(breakout_idx + 1, last) if basis[k] is not None)
        reclaimed = closes[last] > bo_high and closes[last] > closes[last - 1]
        if pulled_back and reclaimed:
            profile = "RETEST"

    if profile is None:
        return SqueezeSignal(False, None, stop_20ma, {**ev, "reason": "awaiting_retest_or_continuation"})

    ev.update({
        "entry_profile": profile,
        "volume_spike_ratio": vol_spike_ratio,
        "breakout_strength_pct": breakout_strength_pct,
        "bb_upper_at_break": round(bo_upper, 8) if bo_upper else None,
    })
    # Stop must sit below current price to be valid.
    if stop_20ma is not None and closes[last] <= stop_20ma:
        return SqueezeSignal(False, profile, stop_20ma, {**ev, "reason": "price_below_basis"})
    return SqueezeSignal(True, profile, stop_20ma, ev)
