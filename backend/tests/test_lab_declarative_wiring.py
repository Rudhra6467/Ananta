"""Regression: declarative catalog strategies must fire entries in the Research Lab.

Root cause fixed 2026-07-17: lab/backtest._scan_entry only evaluated the three core
strategies (hunter/squeeze/continuation), so every declarative catalog strategy
(ema-cross, supertrend, turtle, vwap-mr, ...) produced ZERO entries → the Lab PDF
showed no trades. These tests assert declarative entries are now wired in.

Uses the real historical candle store (no network). Skips gracefully if the store
lacks enough BTC/USD 1h history in the CI image.
"""
from __future__ import annotations

import pytest

from lab import backtest, data_store
from strategy.declarative_defs import DECLARATIVE

_MIN_BARS = backtest.WARMUP_BARS + 300


@pytest.fixture(scope="module")
def btc_window():
    bars = data_store.load_candles("BTC/USD", "1h")
    if len(bars) < _MIN_BARS:
        pytest.skip(f"insufficient BTC/USD 1h history ({len(bars)} bars)")
    end_ms = bars[-1][0]
    start_ms = bars[max(backtest.WARMUP_BARS, len(bars) - 2200)][0]
    return start_ms, end_ms


@pytest.mark.parametrize("strat", ["turtle", "time-series-momentum", "stochastic-momentum",
                                   "vwap-mr", "ema-cross", "supertrend", "bollinger-mr"])
def test_declarative_strategy_produces_entries(btc_window, strat):
    start_ms, end_ms = btc_window
    r = backtest.run_backtest("BTC/USD", start_ms, end_ms, strategies=[strat],
                              exit_method="atr", timeframe="1h")
    assert "error" not in r, f"{strat} errored: {r.get('error')}"
    assert r["entries"] > 0, f"{strat} generated zero entries in the Lab (regression!)"
    assert r["trades"] > 0, f"{strat} generated zero trades in the Lab (regression!)"
    # every trade must be attributed to the selected strategy (no cross-contamination)
    assert set(r.get("strategy_breakdown", {})) == {strat}


def test_core_strategy_still_works(btc_window):
    """Guard: wiring declarative entries must not break the core hunter path."""
    start_ms, end_ms = btc_window
    r = backtest.run_backtest("BTC/USD", start_ms, end_ms, strategies=["hunter"],
                              exit_method="atr", timeframe="1h")
    assert "error" not in r
    assert set(r.get("strategy_breakdown", {})) <= {"hunter"}


def test_all_wired_declaratives_are_registered():
    """The 4 newly wired specs must be present in the declarative registry."""
    for key in ("turtle", "time-series-momentum", "stochastic-momentum", "vwap-mr"):
        assert key in DECLARATIVE, f"{key} missing from DECLARATIVE registry"
