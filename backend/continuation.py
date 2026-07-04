"""
continuation.py — Hunter Continuation (WS2), an INDEPENDENT alpha model (pure compute).

Personality: "I buy the dip in an established uptrend." Distinct from the Hunter
reversal ("buys fear" at deep oversold) and the Squeeze ("buys expansion").

Trigger : an ESTABLISHED uptrend — 50-EMA rising AND 20-EMA > 50-EMA AND price
          holding above the 50-EMA.
Entry   : a controlled PULLBACK from a recent swing high back toward the 20-EMA
          dynamic support, with volume DRYING UP (sellers exhausting) and RSI in a
          healthy pullback band (40-62, NOT the 30-35 reversal zone), then the
          current candle stabilises/turns back up (no chasing a vertical candle).
Stop    : structural — below the pullback low / 50-EMA, buffered by 0.4x ATR.

Pure compute, ZERO LLM credits. Risk is owned by the universal exit engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from setup_classifier import atr, ema, rsi

# bar layout: [ts, open, high, low, close, volume]
_O, _H, _L, _C, _V = 1, 2, 3, 4, 5
ATR_STOP_MULT = 0.4


@dataclass
class ContinuationSignal:
    triggered: bool
    entry_profile: str | None            # TREND_PULLBACK | None
    structural_stop: float | None
    evidence: dict = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)


def evaluate_continuation(bars: list[list[float]], settings, regime=None) -> ContinuationSignal:
    n = len(bars or [])
    slow = int(getattr(settings, "cont_ema_slow", 50))
    fast = int(getattr(settings, "cont_ema_fast", 20))
    rising_lb = int(getattr(settings, "cont_trend_rising_lookback", 10))
    if n < slow + rising_lb + 5:
        return ContinuationSignal(False, None, None, {"reason": "insufficient_bars", "bars": n})

    closes = [b[_C] for b in bars]
    highs = [b[_H] for b in bars]
    lows = [b[_L] for b in bars]
    vols = [b[_V] for b in bars]
    price = closes[-1]

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    ef, es = ema_fast[-1], ema_slow[-1]
    es_prev = ema_slow[-1 - rising_lb]
    rsis = rsi(closes, 14)
    rsi_val = rsis[-1] if rsis else None
    try:
        atr_last = atr(highs, lows, closes)[-1]
    except Exception:
        atr_last = 0.0

    codes: list[str] = []

    # 1) established uptrend: 20>50, 50 rising, price above 50-EMA
    trend_up = (ef > es) and (es > es_prev) and (price > es)
    if not trend_up:
        codes.append("REJECTED_NO_UPTREND")

    # 2) controlled pullback from a recent swing high
    swing_lb = int(getattr(settings, "cont_swing_lookback", 12))
    swing_high = max(highs[-swing_lb:])
    pullback_pct = ((swing_high - price) / swing_high * 100.0) if swing_high > 0 else 0.0
    pb_min = float(getattr(settings, "cont_pullback_min_pct", 1.0))
    pb_max = float(getattr(settings, "cont_pullback_max_pct", 12.0))
    pullback_ok = pb_min <= pullback_pct <= pb_max
    if not pullback_ok:
        codes.append("REJECTED_PULLBACK_OUT_OF_RANGE")

    # 3) at 20-EMA dynamic support (pulled back to it but holding above the 50-EMA)
    support_mult = float(getattr(settings, "cont_support_atr_mult", 0.6))
    near_fast = atr_last > 0 and abs(price - ef) <= support_mult * atr_last
    at_support = (near_fast or price <= ef * 1.005) and price >= es
    if not at_support:
        codes.append("REJECTED_NOT_AT_SUPPORT")

    # 4) volume dry-up into the pullback
    recent_vol = sum(vols[-3:]) / 3.0
    prior_vol = sum(vols[-10:-3]) / 7.0 if len(vols) >= 10 else recent_vol
    dryup_ratio = (recent_vol / prior_vol) if prior_vol > 0 else 1.0
    dryup_ok = dryup_ratio <= float(getattr(settings, "cont_vol_dryup_ratio", 0.9))
    if not dryup_ok:
        codes.append("REJECTED_NO_VOLUME_DRYUP")

    # 5) healthy pullback RSI band (not the oversold reversal zone)
    r_min = float(getattr(settings, "cont_rsi_min", 40.0))
    r_max = float(getattr(settings, "cont_rsi_max", 62.0))
    rsi_ok = rsi_val is not None and r_min <= rsi_val <= r_max
    if not rsi_ok:
        codes.append("REJECTED_RSI_OUT_OF_BAND")

    # 6) anti-chase + a stabilising / turning-up candle
    last_open = bars[-1][_O]
    body_pct = ((price - last_open) / last_open * 100.0) if last_open > 0 else 0.0
    not_chasing = body_pct <= float(getattr(settings, "cont_max_green_body_pct", 2.0))
    reclaim = price >= closes[-2]
    if not not_chasing:
        codes.append("REJECTED_CHASING_GREEN_CANDLE")
    if not reclaim:
        codes.append("REJECTED_NOT_TURNING_UP")

    triggered = bool(trend_up and pullback_ok and at_support and dryup_ok and rsi_ok and not_chasing and reclaim)

    structural_stop = None
    if triggered:
        struct_low = min(min(lows[-swing_lb:]), es)
        structural_stop = round(struct_low - ATR_STOP_MULT * atr_last, 8)

    ev = {
        "ema_fast": round(ef, 6), "ema_slow": round(es, 6),
        "trend_rising": es > es_prev, "price_above_slow": price > es,
        "pullback_pct": round(pullback_pct, 3), "swing_high": round(swing_high, 6),
        "at_20ema_support": at_support, "vol_dryup_ratio": round(dryup_ratio, 3),
        "rsi_14": round(rsi_val, 2) if rsi_val is not None else None,
        "entry_candle_body_pct": round(body_pct, 3), "atr": round(atr_last, 8),
    }
    return ContinuationSignal(triggered, "TREND_PULLBACK" if triggered else None,
                              structural_stop, ev, codes)
