"""
Systemic Breakout Filter — Layer 5c.

Promotes a regular BUY signal into a high-velocity "Breakout" state when ALL
three conditions fire simultaneously on the same candle:

  1) Gemini macro = BULLISH AND confidence >= settings.breakout_min_confidence
  2) Current hourly volume is at/above the 95th percentile of the last 14
     hourly candle volumes (sudden interest spike).
  3) Real-time bid-ask spread is <= settings.breakout_max_spread_pct (tight
     book guarantees we can actually fill the aggressive lot).

A breakout entry uses settings.breakout_lot_usd and the position is flagged
with breakout_mode=True, which makes the position watcher use the wider
trail_arm_pct / trail_distance_pct so the trade has room to run.
"""
from __future__ import annotations

from setup_classifier import percentile_rank


def detect_breakout(
    bars_1h: list[list[float]],
    macro_bias: str,
    macro_confidence: float,
    spread_pct: float,
    *,
    min_confidence: float = 0.85,
    volume_percentile_floor: float = 95.0,
    max_spread_pct: float = 0.20,
) -> tuple[bool, dict]:
    """Returns (is_breakout, evidence). Evidence always populated for the
    operator audit log so we can see *which* leg failed when it doesn't fire.

    bars_1h: CCXT OHLCV format [[ts, open, high, low, close, volume], ...]
    """
    evidence: dict = {
        "macro_bias": macro_bias,
        "macro_confidence": round(macro_confidence, 3),
        "spread_pct": round(spread_pct, 4),
        "min_confidence": min_confidence,
        "volume_percentile_floor": volume_percentile_floor,
        "max_spread_pct": max_spread_pct,
    }

    # leg 1 — macro
    macro_ok = macro_bias == "BULLISH" and macro_confidence >= min_confidence
    evidence["macro_ok"] = macro_ok

    # leg 2 — volume spike (need >= 14 bars for a meaningful percentile)
    if len(bars_1h) < 14:
        evidence["volume_ok"] = False
        evidence["reason"] = f"need >= 14 hourly bars (have {len(bars_1h)})"
        return False, evidence

    lookback = bars_1h[-14:]
    volumes = [float(b[5]) for b in lookback if len(b) >= 6]
    if not volumes:
        evidence["volume_ok"] = False
        evidence["reason"] = "no volume data in lookback window"
        return False, evidence

    current_vol = volumes[-1]
    vol_rank = percentile_rank(volumes, current_vol)
    evidence["current_volume"] = round(current_vol, 4)
    evidence["volume_percentile"] = round(vol_rank, 2)
    volume_ok = vol_rank >= volume_percentile_floor
    evidence["volume_ok"] = volume_ok

    # leg 3 — spread
    spread_ok = spread_pct <= max_spread_pct
    evidence["spread_ok"] = spread_ok

    is_breakout = macro_ok and volume_ok and spread_ok
    if not is_breakout:
        failed = [k for k, v in {"macro_ok": macro_ok, "volume_ok": volume_ok, "spread_ok": spread_ok}.items() if not v]
        evidence["reason"] = f"failed legs: {', '.join(failed)}"
    else:
        evidence["reason"] = "all 3 legs aligned — SYSTEMIC BREAKOUT"
    return is_breakout, evidence
