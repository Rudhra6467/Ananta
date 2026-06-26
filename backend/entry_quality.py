"""
entry_quality.py — Entry Quality Scoring (Phase E, pure compute, ZERO LLM credits).

Every strategy entry (simulated OR executed) gets a graded score. This is for
RESEARCH, not filtering — so after N trades we can ask "do A-grade setups beat
B-grade?", "does waiting for a retest help?", "are weak zones worth trading?".

Each component is scored 0..10; the total is normalised to a 0..100 score with a
letter grade. Nothing here gates a trade.
"""
from __future__ import annotations


def _clamp(v: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, v))


def grade_from_pct(pct: float) -> str:
    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 65:
        return "B"
    return "C"


def _finalize(components: dict[str, float]) -> dict:
    comp = {k: round(_clamp(v), 1) for k, v in components.items()}
    total = sum(comp.values())
    max_total = len(comp) * 10.0
    pct = round(total / max_total * 100.0, 1) if max_total else 0.0
    return {
        "score": round(total, 1),
        "max": max_total,
        "pct": pct,
        "grade": grade_from_pct(pct),
        "components": comp,
    }


def score_hunter(
    *,
    rsi_4h: float | None,
    volume_slope: float | None,
    support_touches: int | None,
    support_strength: float | None,
    htf_trend_aligned: bool | None,
    higher_high_higher_low: bool,
    entry_profile: str,
) -> dict:
    """Grade a Hunter (reversal) entry from its feature snapshot."""
    # RSI reset: deeper oversold = higher quality (35 -> 0, 15 -> 10).
    rsi_score = 0.0 if rsi_4h is None else _clamp((35.0 - rsi_4h) / 2.0)
    # Volume exhaustion: more negative slope = drier selling = higher.
    vol_score = 0.0 if volume_slope is None else _clamp(5.0 + (-volume_slope) * 0.0005)
    # Zone quality: touches + structural strength.
    touch_score = _clamp((support_touches or 0) * 1.2)
    strength_score = _clamp((support_strength or 0) * 0.8)
    # Trend alignment.
    trend_score = 8.0 if htf_trend_aligned else 4.0
    # Structure confirmation (higher-low present).
    struct_score = 10.0 if higher_high_higher_low else 6.0
    # Aggressive first-touch profile trades slightly lower structural confirmation
    # by design, so reflect that it leans on trend rather than reset.
    if entry_profile == "AGGRESSIVE_PULLBACK":
        rsi_score = max(rsi_score, 6.0)  # trend entries don't need a deep reset
        trend_score = 10.0
    return _finalize({
        "rsi_reset": rsi_score,
        "volume_exhaustion": vol_score,
        "zone_touches": touch_score,
        "zone_strength": strength_score,
        "trend_alignment": trend_score,
        "structure": struct_score,
    })


def score_squeeze(
    *,
    bbwidth_percentile: float | None,
    atr_percentile: float | None,
    volume_spike_ratio: float | None,
    breakout_strength_pct: float | None,
    entry_profile: str,
) -> dict:
    """Grade a Volatility Squeeze (expansion) entry."""
    # Tighter compression before the break = higher quality.
    comp_score = 0.0 if bbwidth_percentile is None else _clamp((30.0 - bbwidth_percentile) / 2.0)
    atr_score = 0.0 if atr_percentile is None else _clamp((40.0 - atr_percentile) / 3.0)
    # Volume spike on the breakout (1.0x -> 0, 3x -> 10).
    vol_score = 0.0 if volume_spike_ratio is None else _clamp((volume_spike_ratio - 1.0) * 5.0)
    # Strength of the break above the band.
    break_score = 0.0 if breakout_strength_pct is None else _clamp(breakout_strength_pct * 3.0)
    # Retest/continuation entries are higher quality than chasing the first candle.
    timing_score = 9.0 if entry_profile in ("RETEST", "CONTINUATION") else 5.0
    return _finalize({
        "compression": comp_score,
        "atr_coil": atr_score,
        "volume_spike": vol_score,
        "breakout_strength": break_score,
        "entry_timing": timing_score,
    })
