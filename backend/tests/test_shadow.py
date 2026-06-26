"""Tests for the SHADOW simulator (Phase 2.1)."""
from __future__ import annotations

from models import RiskSettings
from shadow_sim import is_shadow_entry, summarize_shadow


def test_shadow_band_detection():
    s = RiskSettings()  # min_confidence 0.80 -> shadow band [0.70, 0.80)
    assert is_shadow_entry("BULLISH", 0.76, s) is True
    assert is_shadow_entry("BULLISH", 0.70, s) is True
    assert is_shadow_entry("BULLISH", 0.79, s) is True
    # at/above execute floor -> not shadow (would be a real entry)
    assert is_shadow_entry("BULLISH", 0.80, s) is False
    # below shadow floor -> not shadow
    assert is_shadow_entry("BULLISH", 0.69, s) is False
    # non-bullish never shadows
    assert is_shadow_entry("BEARISH", 0.76, s) is False
    assert is_shadow_entry("NEUTRAL", 0.76, s) is False


def test_shadow_band_tracks_custom_floor():
    s = RiskSettings(min_confidence=0.85)  # band becomes [0.75, 0.85)
    assert is_shadow_entry("BULLISH", 0.80, s) is True
    assert is_shadow_entry("BULLISH", 0.74, s) is False
    assert is_shadow_entry("BULLISH", 0.85, s) is False


def test_summarize_shadow_expectancy_and_buckets():
    closed = [
        {"win": True, "pnl_pct": 4.0, "confidence_at_entry": 0.72},
        {"win": False, "pnl_pct": -2.5, "confidence_at_entry": 0.74},
        {"win": True, "pnl_pct": 3.0, "confidence_at_entry": 0.77},
    ]
    out = summarize_shadow([], closed)
    assert out["closed_count"] == 3
    assert out["win_rate_pct"] == round(2 / 3 * 100, 2)
    assert out["avg_win_pct"] == 3.5
    assert out["avg_loss_pct"] == -2.5
    assert out["expectancy_pct"] == round((4.0 - 2.5 + 3.0) / 3, 4)
    b = {x["bucket"]: x for x in out["confidence_buckets"]}
    assert b["0.70-0.74"]["count"] == 2
    assert b["0.75-0.79"]["count"] == 1


def test_summarize_shadow_empty():
    out = summarize_shadow([], [])
    assert out["closed_count"] == 0
    assert out["win_rate_pct"] is None
    assert out["expectancy_pct"] is None
