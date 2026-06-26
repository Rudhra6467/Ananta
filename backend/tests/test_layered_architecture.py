"""Tests for the Phase 2 Primary/Secondary layered architecture + RSI helper."""
from __future__ import annotations

from models import RiskSettings
from setup_classifier import rsi
from primary_layer import evaluate_primary, _linreg_slope
from circuit_breaker import evaluate_breaker


def _bar(o, h, l, c, v):
    return [0.0, float(o), float(h), float(l), float(c), float(v)]


def _declining_into_support(zone_price=100.0, n=30, start=120.0, falling_volume=True):
    """A clean pullback: price drifts DOWN from `start` to `zone_price` with the
    final candle red and falling volume — the textbook primary-layer setup."""
    bars = []
    for i in range(n):
        frac = i / (n - 1)
        price = start - (start - zone_price) * frac
        o = price + 0.4
        c = price  # red-ish (close below open) on the way down
        h = price + 0.6
        l = price - 0.6
        vol = (1000 - i * 20) if falling_volume else (500 + i * 20)
        bars.append(_bar(o, h, l, c, max(vol, 10)))
    return bars


def _zone_at(p):
    return [{"low": p - 1.0, "high": p + 1.0, "mid": p, "touches": 8, "strength": 12.0, "last_touch_ms": 0}]


# ---------------- RSI ----------------
def test_rsi_all_gains_is_100():
    closes = [float(i) for i in range(1, 40)]  # monotonic up
    out = rsi(closes, 14)
    assert out and out[-1] == 100.0


def test_rsi_downtrend_is_low():
    closes = [float(i) for i in range(40, 1, -1)]  # monotonic down
    out = rsi(closes, 14)
    assert out and out[-1] <= 1.0


def test_rsi_insufficient_data():
    assert rsi([1.0, 2.0, 3.0], 14) == []


def test_linreg_slope_sign():
    assert _linreg_slope([5, 4, 3, 2, 1]) < 0
    assert _linreg_slope([1, 2, 3, 4, 5]) > 0


# ---------------- Primary layer ----------------
def test_primary_triggers_on_clean_setup():
    s = RiskSettings()
    bars = _declining_into_support(100.0)
    zones = _zone_at(100.0)
    sig = evaluate_primary("SOL/USD", price=100.0, bars_4h=bars, zones=zones, settings=s)
    assert sig.triggered, sig.reason_codes
    assert sig.reason_codes == []
    # structural stop = zone low (99) minus 2% buffer
    assert sig.structural_stop is not None and sig.structural_stop < 99.0


def test_primary_rejects_no_support():
    s = RiskSettings()
    bars = _declining_into_support(100.0)
    sig = evaluate_primary("SOL/USD", price=100.0, bars_4h=bars, zones=[], settings=s)
    assert not sig.triggered
    assert "REJECTED_NO_SUPPORT_ZONE" in sig.reason_codes


def test_primary_rejects_chasing_green_candle():
    s = RiskSettings()
    bars = _declining_into_support(100.0)
    # overwrite last candle as a big green breakout body (+3%)
    bars[-1] = _bar(100.0, 104.0, 99.5, 103.0, 200)
    zones = _zone_at(100.0)
    sig = evaluate_primary("SOL/USD", price=103.0, bars_4h=bars, zones=zones, settings=s)
    assert not sig.triggered
    assert "REJECTED_CHASING_GREEN_CANDLE" in sig.reason_codes


def test_primary_rejects_rising_volume():
    s = RiskSettings()
    bars = _declining_into_support(100.0, falling_volume=False)  # volume rising into zone
    zones = _zone_at(100.0)
    sig = evaluate_primary("SOL/USD", price=100.0, bars_4h=bars, zones=zones, settings=s)
    assert not sig.triggered
    assert "REJECTED_VOLUME_NOT_EXHAUSTED" in sig.reason_codes


def test_primary_rejects_rsi_not_reset():
    s = RiskSettings()
    # price rising into the zone -> RSI hot (> 35), should reject on momentum
    bars = []
    for i in range(30):
        price = 90.0 + i  # uptrend -> high RSI
        bars.append(_bar(price - 0.4, price + 0.6, price - 0.6, price, 500 - i * 10))
    zones = _zone_at(119.0)
    sig = evaluate_primary("SOL/USD", price=119.0, bars_4h=bars, zones=zones, settings=s)
    assert "REJECTED_RSI_NOT_RESET" in sig.reason_codes


def test_primary_insufficient_data():
    s = RiskSettings()
    sig = evaluate_primary("SOL/USD", price=100.0, bars_4h=[_bar(1, 1, 1, 1, 1)], zones=_zone_at(100.0), settings=s)
    assert not sig.triggered
    assert "REJECTED_INSUFFICIENT_DATA" in sig.reason_codes


# ---------------- Circuit Breaker (tri-state) ----------------
def test_breaker_passes_on_neutral():
    s = RiskSettings()
    state, reason = evaluate_breaker("NEUTRAL", 0.1, news_sentiment=None)
    assert state == "PASS"


def test_breaker_cautions_on_bearish_never_vetoes():
    s = RiskSettings()
    # Even high-conviction bearish macro is at most CAUTION — never VETO (forbidden).
    state, reason = evaluate_breaker("BEARISH", 0.95, news_sentiment=None)
    assert state == "CAUTION"


def test_breaker_vetoes_only_on_existential_event():
    s = RiskSettings()
    state, reason = evaluate_breaker("NEUTRAL", 0.1, existential_event="PROTOCOL_EXPLOIT")
    assert state == "VETO"
    assert "EXISTENTIAL" in reason
