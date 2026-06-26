"""Phase E engine tests: regime classifier, squeeze model, entry quality, Hunter profiles.
Pure-compute — no DB, no network, no LLM."""
from types import SimpleNamespace

import pytest

from regime import classify_regime
from squeeze import evaluate_squeeze
from entry_quality import score_hunter, score_squeeze, grade_from_pct
from primary_layer import evaluate_primary


def _bar(ts, o, h, l, c, v):
    return [ts, o, h, l, c, v]


# ---------------- regime ----------------
def test_regime_strong_uptrend():
    bars = []
    for i in range(260):
        price = 100 + i * 0.5  # steady ramp
        bars.append(_bar(i, price - 0.2, price + 0.4, price - 0.4, price, 100))
    reg = classify_regime(bars)
    assert reg.regime == "TREND_UP"
    assert reg.strong_uptrend is True


def test_regime_compression():
    bars = []
    # volatile history then a tight flat coil -> recent volatility in low percentile
    for i in range(60):
        hi, lo = 110, 90
        bars.append(_bar(i, 100, hi, lo, 100 + (i % 3), 100))
    for i in range(60, 120):
        bars.append(_bar(i, 100, 100.2, 99.8, 100, 100))
    reg = classify_regime(bars)
    assert reg.compression is True
    assert reg.regime == "COMPRESSION"


def test_regime_insufficient():
    assert classify_regime([]).regime == "NEUTRAL"


# ---------------- squeeze ----------------
def test_squeeze_continuation_triggers():
    bars = []
    # 25 coil bars (tight), big breakout candle, inside candle, then break of inside high
    for i in range(25):
        bars.append(_bar(i, 100, 100.3, 99.7, 100, 100))
    bars.append(_bar(25, 100, 121, 100, 120, 400))   # breakout candle (vol spike)
    bars.append(_bar(26, 120, 119, 110, 115, 120))   # inside candle
    bars.append(_bar(27, 116, 122, 115, 120.5, 130))  # breaks inside high (119)
    sig = evaluate_squeeze(bars)
    assert sig.triggered is True
    assert sig.entry_profile in ("CONTINUATION", "RETEST")
    assert sig.stop_20ma is not None and sig.stop_20ma < 120.5


def test_squeeze_no_setup_when_flat():
    bars = [_bar(i, 100, 100.2, 99.8, 100, 100) for i in range(40)]
    sig = evaluate_squeeze(bars)
    assert sig.triggered is False


# ---------------- entry quality ----------------
def test_grade_bands():
    assert grade_from_pct(95) == "A+"
    assert grade_from_pct(82) == "A"
    assert grade_from_pct(70) == "B"
    assert grade_from_pct(50) == "C"


def test_score_hunter_shape():
    q = score_hunter(rsi_4h=18, volume_slope=-5000, support_touches=10, support_strength=12,
                     htf_trend_aligned=True, higher_high_higher_low=True, entry_profile="STABILIZED_REVERSAL")
    assert 0 <= q["pct"] <= 100
    assert q["grade"] in ("A+", "A", "B", "C")
    assert set(q["components"]) >= {"rsi_reset", "volume_exhaustion", "structure"}


def test_score_squeeze_shape():
    q = score_squeeze(bbwidth_percentile=10, atr_percentile=20, volume_spike_ratio=3.0,
                      breakout_strength_pct=2.0, entry_profile="RETEST")
    assert 0 <= q["pct"] <= 100
    assert q["grade"] in ("A+", "A", "B", "C")


# ---------------- Hunter regime-aware profiles ----------------
_SETTINGS = SimpleNamespace(
    level_proximity_pct=1.5, pullback_max_green_body_pct=1.5,
    volume_exhaustion_window=6, rsi_reset_max=35.0, structural_stop_buffer_pct=2.0,
)
_ZONE = {"low": 99.0, "high": 101.0, "mid": 100.0, "touches": 8, "strength": 10.0}


def _flat_bars(last_open=99.9, last_close=100.0):
    bars = [_bar(i, 100, 100.5, 99.5, 100, 100) for i in range(24)]
    bars.append(_bar(24, last_open, 100.6, 99.4, last_close, 100))
    return bars


def test_hunter_aggressive_pullback_profile():
    reg = SimpleNamespace(regime="TREND_UP", strong_uptrend=True, panic=False,
                          evidence={"higher_high_higher_low": True})
    sig = evaluate_primary("BTC/USD", 100.0, _flat_bars(), [_ZONE], _SETTINGS, regime=reg)
    assert sig.entry_profile == "AGGRESSIVE_PULLBACK"
    assert sig.triggered is True
    assert sig.structural_stop is not None and sig.structural_stop < 100.0
    assert "entry_quality" in sig.evidence


def test_hunter_deep_discount_requires_acceptance():
    reg = SimpleNamespace(regime="REVERSAL", strong_uptrend=False, panic=True, evidence={})
    # last 4 bars trade inside the zone -> acceptance
    bars = [_bar(i, 100, 100.5, 99.5, 100, 100) for i in range(21)]
    for i in range(21, 25):
        bars.append(_bar(i, 100, 100.2, 99.6, 99.8, 100))
    sig = evaluate_primary("BTC/USD", 100.0, bars, [_ZONE], _SETTINGS, regime=reg)
    assert sig.entry_profile == "DEEP_DISCOUNT"
    assert sig.triggered is True


def test_hunter_default_profile_when_no_regime():
    sig = evaluate_primary("BTC/USD", 100.0, _flat_bars(), [_ZONE], _SETTINGS, regime=None)
    assert sig.entry_profile == "STABILIZED_REVERSAL"


# ---------------- router ----------------
def test_router_eligibility():
    from router import route, hunter_allowed, squeeze_allowed
    assert "hunter" in route("TREND_UP")["eligible_models"]
    assert "squeeze" in route("COMPRESSION")["eligible_models"]
    assert route("TREND_DOWN")["eligible_models"] == []
    assert squeeze_allowed("COMPRESSION") is True
    assert squeeze_allowed("TREND_DOWN") is False
    assert hunter_allowed("REVERSAL") is True
    # unknown regime falls back to both
    assert set(route(None)["eligible_models"]) >= {"hunter", "squeeze"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])