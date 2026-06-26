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
from setup_classifier import atr, rsi

# 4h bar layout: [ts, open, high, low, close, volume]
_O, _H, _L, _C, _V = 1, 2, 3, 4, 5
PULLBACK_LOOKBACK = 3  # bars: price must have declined into the zone over this span
ACCEPTANCE_WINDOW = 4  # Profile 3: bars price must spend inside the demand zone
ATR_STOP_MULT = 0.4    # structural stop sits 0.4x ATR BELOW the structure low


@dataclass
class PrimarySignal:
    triggered: bool
    reason_codes: list[str]
    support_zone: dict | None
    structural_stop: float | None
    evidence: dict
    entry_profile: str | None = None  # AGGRESSIVE_PULLBACK | STABILIZED_REVERSAL | DEEP_DISCOUNT


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


def evaluate_primary(symbol: str, price: float, bars_4h: list[list[float]], zones: list[dict], settings, regime=None) -> PrimarySignal:
    """Run the Hunter technical gates, REGIME-AWARE (Phase E).

    Hunter is the "buy fear" trader. It now selects one of three entry profiles
    based on the market regime (when provided), instead of one fixed rule:

      * AGGRESSIVE_PULLBACK (strong uptrend): buy the FIRST touch of support;
        a deep RSI reset / volume exhaustion is NOT required (buyers step in fast).
      * STABILIZED_REVERSAL (default / transition): the classic 4-gate setup —
        support + pullback + volume exhaustion + RSI reset.
      * DEEP_DISCOUNT (panic): require ACCEPTANCE (price spends time inside the
        demand zone) rather than a precise RSI bounce.

    `regime` is an optional regime.Regime; when None, behaves as STABILIZED_REVERSAL.
    reason_codes lists every gate that failed (empty when triggered). Pure compute.
    """
    if not bars_4h or len(bars_4h) < 20:
        return PrimarySignal(False, ["REJECTED_INSUFFICIENT_DATA"], None, None, {"bars_4h": len(bars_4h or [])}, None)

    closes = [b[_C] for b in bars_4h]
    opens = [b[_O] for b in bars_4h]
    highs = [b[_H] for b in bars_4h]
    lows = [b[_L] for b in bars_4h]
    vols = [b[_V] for b in bars_4h]
    codes: list[str] = []
    ev: dict = {}

    # Select entry profile from regime.
    if regime is not None and getattr(regime, "strong_uptrend", False):
        profile = "AGGRESSIVE_PULLBACK"
    elif regime is not None and getattr(regime, "panic", False):
        profile = "DEEP_DISCOUNT"
    else:
        profile = "STABILIZED_REVERSAL"
    ev["entry_profile"] = profile

    # a) Historical support zone (shared by all profiles)
    prox = float(getattr(settings, "level_proximity_pct", 1.5))
    support = nearest_support(price, zones, prox)
    if support is None:
        codes.append("REJECTED_NO_SUPPORT_ZONE")

    # shared sub-signals
    last_open, last_close = opens[-1], closes[-1]
    body_pct = ((last_close - last_open) / last_open * 100.0) if last_open > 0 else 0.0
    max_green = float(getattr(settings, "pullback_max_green_body_pct", 1.5))
    declined = closes[-1] <= closes[-1 - PULLBACK_LOOKBACK] if len(closes) > PULLBACK_LOOKBACK else False
    win = int(getattr(settings, "volume_exhaustion_window", 6))
    vslope = _linreg_slope(vols[-win:])
    rsis = rsi(closes, 14)
    rsi_val = rsis[-1] if rsis else None
    thr = float(getattr(settings, "rsi_reset_max", 35.0))

    ev["entry_candle_body_pct"] = round(body_pct, 3)
    ev["declined_into_zone"] = declined
    ev["volume_slope"] = round(vslope, 4)
    ev["rsi_4h"] = round(rsi_val, 2) if rsi_val is not None else None

    not_chasing = body_pct <= max_green
    vol_ok = vslope < 0
    rsi_ok = rsi_val is not None and rsi_val <= thr

    # Profile-specific qualification
    if profile == "AGGRESSIVE_PULLBACK":
        # First touch in a strong uptrend: just don't chase a vertical green candle.
        if not not_chasing:
            codes.append("REJECTED_CHASING_GREEN_CANDLE")
        triggered = (support is not None) and not_chasing
    elif profile == "DEEP_DISCOUNT":
        # Require ACCEPTANCE: price spent >= 2 of the last bars inside the demand zone.
        acceptance = 0
        if support is not None:
            lo, hi = support["low"], support["high"]
            for b in bars_4h[-ACCEPTANCE_WINDOW:]:
                if b[_L] <= hi and b[_L] >= lo * 0.97:
                    acceptance += 1
        ev["acceptance_bars"] = acceptance
        acceptance_ok = acceptance >= 2
        if not acceptance_ok:
            codes.append("REJECTED_NO_ACCEPTANCE")
        triggered = (support is not None) and acceptance_ok
    else:  # STABILIZED_REVERSAL (classic 4 gates)
        pullback_ok = not_chasing and declined
        if not pullback_ok:
            codes.append("REJECTED_CHASING_GREEN_CANDLE")
        if not vol_ok:
            codes.append("REJECTED_VOLUME_NOT_EXHAUSTED")
        if not rsi_ok:
            codes.append("REJECTED_RSI_NOT_RESET")
        triggered = (support is not None) and pullback_ok and vol_ok and rsi_ok

    # ATR-structural stop: placed BELOW the structure low by 0.4x ATR (Phase E).
    # Crypto hunts obvious stops; ATR adapts the buffer to current noise.
    structural_stop = None
    if triggered and support:
        try:
            atr_last = atr(highs, lows, closes)[-1]
        except Exception:
            atr_last = 0.0
        struct_low = min(support["low"], min(lows[-PULLBACK_LOOKBACK - 1:]))
        structural_stop = round(struct_low - ATR_STOP_MULT * atr_last, 8)
        ev["atr_at_stop"] = round(atr_last, 8)

    # Entry quality score (research only; never gates).
    if triggered:
        from entry_quality import score_hunter
        ev["entry_quality"] = score_hunter(
            rsi_4h=rsi_val,
            volume_slope=vslope,
            support_touches=(support or {}).get("touches"),
            support_strength=(support or {}).get("strength"),
            htf_trend_aligned=(getattr(regime, "regime", None) == "TREND_UP") if regime else None,
            higher_high_higher_low=bool(getattr(regime, "evidence", {}).get("higher_high_higher_low")) if regime else False,
            entry_profile=profile,
        )

    ev["support_zone"] = support
    return PrimarySignal(triggered, [] if triggered else codes, support, structural_stop, ev, profile)


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
