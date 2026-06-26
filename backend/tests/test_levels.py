"""Tests for the Historical Horizontal Level Engine (Phase 1.5a)."""
from __future__ import annotations

from levels import compute_levels, nearest_support, nearest_resistance, _pivots


def _bar(ts, o, h, l, c, v=1000.0):
    return [float(ts), float(o), float(h), float(l), float(c), float(v)]


def _series_with_floor(floor=100.0, peak=120.0, cycles=4, span=8):
    """Build a synthetic candle series that repeatedly bottoms at `floor` and
    tops at `peak` so a clean horizontal support cluster forms at `floor`."""
    bars = []
    ts = 0
    for _ in range(cycles):
        # down-leg into the floor
        for step in range(span):
            frac = step / (span - 1)
            price = peak - (peak - floor) * frac
            bars.append(_bar(ts, price, price + 0.5, price - 0.5, price))
            ts += 1
        # explicit trough bar at the floor
        bars.append(_bar(ts, floor, floor + 0.3, floor - 0.2, floor)); ts += 1
        # up-leg back to the peak
        for step in range(span):
            frac = step / (span - 1)
            price = floor + (peak - floor) * frac
            bars.append(_bar(ts, price, price + 0.5, price - 0.5, price))
            ts += 1
        bars.append(_bar(ts, peak, peak + 0.2, peak - 0.3, peak)); ts += 1
    return bars


def test_pivots_detected():
    bars = _series_with_floor()
    pivots = _pivots(bars, k=3)
    assert pivots, "expected at least some swing pivots"
    prices = [p for _, p in pivots]
    # floor (~100) and peak (~120) should both appear among pivots
    assert any(abs(p - 100.0) <= 1.0 for p in prices)
    assert any(abs(p - 120.0) <= 1.0 for p in prices)


def test_compute_levels_finds_floor_zone():
    bars = _series_with_floor(floor=100.0, peak=120.0, cycles=4)
    zones = compute_levels(bars, [], tol_pct=0.75, min_touches=2)
    assert zones, "expected at least one multi-touch zone"
    # there must be a zone around the 100 floor with >= 2 touches
    floor_zone = next((z for z in zones if z["low"] <= 100.5 and z["high"] >= 99.5), None)
    assert floor_zone is not None
    assert floor_zone["touches"] >= 2


def test_min_touches_filter():
    bars = _series_with_floor(cycles=1)  # only one touch of the floor
    zones_strict = compute_levels(bars, [], tol_pct=0.75, min_touches=5)
    assert zones_strict == []  # nothing tested 5x in a single cycle


def test_nearest_support_when_price_at_floor():
    bars = _series_with_floor(floor=100.0, peak=120.0, cycles=4)
    zones = compute_levels(bars, [], tol_pct=0.75, min_touches=2)
    # price sitting right on the floor -> should detect support
    z = nearest_support(100.2, zones, proximity_pct=1.5)
    assert z is not None
    assert z["low"] <= 100.2 <= z["high"] * 1.015


def test_nearest_support_none_when_price_far_above():
    bars = _series_with_floor(floor=100.0, peak=120.0, cycles=4)
    zones = compute_levels(bars, [], tol_pct=0.75, min_touches=2)
    # price way above any support band -> no support touch
    assert nearest_support(200.0, zones, proximity_pct=1.5) is None


def test_nearest_resistance_above_price():
    bars = _series_with_floor(floor=100.0, peak=120.0, cycles=4)
    zones = compute_levels(bars, [], tol_pct=0.75, min_touches=2)
    r = nearest_resistance(101.0, zones, proximity_pct=1.5)
    assert r is not None
    assert r["mid"] > 101.0


def test_empty_inputs_safe():
    assert compute_levels([], [], tol_pct=0.75, min_touches=2) == []
    assert nearest_support(None, [], 1.5) is None
    assert nearest_support(100.0, [], 1.5) is None
