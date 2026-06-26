"""
primary_layer.py — PRIMARY execution-driver layer (Phase 2, layered architecture).

The SOLE driver of entries. It answers one question: "Is there a high-probability
technical setup here?" A BUY is greenlit ONLY when ALL technical gates align:

  a) Historical Support Zone   — price has dropped into a 1–2y daily/4H horizontal floor
  b) Pullback Confirmation     — entry on a correction/retest, NOT chasing a green breakout candle
  c) Volume Exhaustion         — volume slope is falling into the zone (selling pressure drying up)
  d) Momentum Reset            — 4H RSI(14) cooled off / oversold (<= rsi_reset_max)

When a gate fails, an explicit reason_code is recorded for the Rejection Leaderboard
(`REJECTED_NO_SUPPORT_ZONE`, `REJECTED_CHASING_GREEN_CANDLE`,
`REJECTED_VOLUME_NOT_EXHAUSTED`, `REJECTED_RSI_NOT_RESET`).

Pure compute (no LLM, no credits). Risk is defined by the exit engine, not here.
"""
from __future__ import annotations

from dataclasses import dataclass

from levels import nearest_support
from setup_classifier import rsi

# 4h bar layout: [ts, open, high, low, close, volume]
_O, _C, _V = 1, 4, 5
PULLBACK_LOOKBACK = 3  # bars: price must have declined into the zone over this span


@dataclass
class PrimarySignal:
    triggered: bool
    reason_codes: list[str]
    support_zone: dict | None
    structural_stop: float | None
    evidence: dict


def _linreg_slope(values: list[float]) -> float:
    """Least-squares slope of a short series. Negative => declining."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    num = sum((xs[i] - mx) * (values[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    return num / den if den else 0.0


def evaluate_primary(symbol: str, price: float, bars_4h: list[list[float]], zones: list[dict], settings) -> PrimarySignal:
    """Run all four technical gates. Returns a PrimarySignal; reason_codes lists
    every gate that failed (empty when triggered)."""
    if not bars_4h or len(bars_4h) < 20:
        return PrimarySignal(False, ["REJECTED_INSUFFICIENT_DATA"], None, None, {"bars_4h": len(bars_4h or [])})

    closes = [b[_C] for b in bars_4h]
    opens = [b[_O] for b in bars_4h]
    vols = [b[_V] for b in bars_4h]
    codes: list[str] = []
    ev: dict = {}

    # a) Historical support zone
    prox = float(getattr(settings, "level_proximity_pct", 1.5))
    support = nearest_support(price, zones, prox)
    if support is None:
        codes.append("REJECTED_NO_SUPPORT_ZONE")

    # b) Pullback confirmation — reject chasing a green breakout candle, and require
    #    price approached the zone on a correction (declined over the lookback).
    last_open = opens[-1]
    last_close = closes[-1]
    body_pct = ((last_close - last_open) / last_open * 100.0) if last_open > 0 else 0.0
    max_green = float(getattr(settings, "pullback_max_green_body_pct", 1.5))
    declined = closes[-1] <= closes[-1 - PULLBACK_LOOKBACK] if len(closes) > PULLBACK_LOOKBACK else False
    pullback_ok = (body_pct <= max_green) and declined
    ev["entry_candle_body_pct"] = round(body_pct, 3)
    ev["declined_into_zone"] = declined
    if not pullback_ok:
        codes.append("REJECTED_CHASING_GREEN_CANDLE")

    # c) Volume exhaustion — falling volume slope into the zone.
    win = int(getattr(settings, "volume_exhaustion_window", 6))
    recent_vols = vols[-win:]
    vslope = _linreg_slope(recent_vols)
    vol_ok = vslope < 0
    ev["volume_slope"] = round(vslope, 4)
    if not vol_ok:
        codes.append("REJECTED_VOLUME_NOT_EXHAUSTED")

    # d) Momentum reset — 4H RSI(14) cooled off / oversold.
    rsis = rsi(closes, 14)
    rsi_val = rsis[-1] if rsis else None
    thr = float(getattr(settings, "rsi_reset_max", 35.0))
    rsi_ok = rsi_val is not None and rsi_val <= thr
    ev["rsi_4h"] = round(rsi_val, 2) if rsi_val is not None else None
    if not rsi_ok:
        codes.append("REJECTED_RSI_NOT_RESET")

    triggered = (support is not None) and pullback_ok and vol_ok and rsi_ok
    structural_stop = None
    if triggered and support:
        buf = float(getattr(settings, "structural_stop_buffer_pct", 2.0)) / 100.0
        structural_stop = round(support["low"] * (1.0 - buf), 8)

    ev["support_zone"] = support
    return PrimarySignal(triggered, [] if triggered else codes, support, structural_stop, ev)


def fifty_pct_metric(bars_4h: list[list[float]], price: float, lookback: int = 60) -> dict:
    """DIAGNOSTIC ONLY (Phase B). Compute the 50% / Fair-Value midpoint of the recent
    dealing range (impulse leg) over the last `lookback` 4H bars. Never gates a trade —
    purely stored in research_log to later test whether 'discount' entries win more.

    Returns swing_low, swing_high, midpoint_50, distance_from_midpoint_pct, above_or_below.
    """
    out: dict = {
        "swing_low": None, "swing_high": None, "midpoint_50": None,
        "distance_from_midpoint_pct": None, "above_or_below_midpoint": None,
    }
    if not bars_4h or len(bars_4h) < 5 or not price or price <= 0:
        return out
    window = bars_4h[-lookback:]
    swing_low = min(b[3] for b in window)   # bar low
    swing_high = max(b[2] for b in window)  # bar high
    if swing_high <= swing_low:
        return out
    midpoint = (swing_high + swing_low) / 2.0
    dist_pct = (price - midpoint) / midpoint * 100.0
    out.update({
        "swing_low": round(swing_low, 8),
        "swing_high": round(swing_high, 8),
        "midpoint_50": round(midpoint, 8),
        "distance_from_midpoint_pct": round(dist_pct, 4),
        "above_or_below_midpoint": "ABOVE" if price >= midpoint else "BELOW",
    })
    return out
