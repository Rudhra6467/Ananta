"""Regression (P2): CUSTOM imported/cloned strategies must execute in the Research Lab.

Root cause: lab/backtest.run_backtest only knew the hardcoded DECLARATIVE catalog, and the
Lab runs in an isolated worker PROCESS with no in-memory imported-strategy registry. So a
custom strategy selected for a Lab run produced ZERO entries (silent blank result).

Fix: the parent process resolves the custom strategy's declarative spec + params and passes
them into run_backtest via `decl_overrides` (picklable), keyed by lowercased engine key.

Uses the real historical candle store (no network). Skips if BTC/USD 1h history is thin.
"""
from __future__ import annotations

import pytest

from lab import backtest, data_store

_MIN_BARS = backtest.WARMUP_BARS + 300

# A custom (e.g. cloned) EMA-cross strategy — identical shape to what register_imported stores.
_CUSTOM_KEY = "clone-testcustom01"
_CUSTOM_SPEC = {
    "indicators": {"ema_fast": {"fn": "ema", "period": "$ema_fast"},
                   "ema_slow": {"fn": "ema", "period": "$ema_slow"}},
    "entry": [{"lhs": "ema_fast", "op": "cross_above", "rhs": "ema_slow"}],
    "exit": [{"lhs": "ema_fast", "op": "cross_below", "rhs": "ema_slow"}],
    "entry_reason": "custom fast EMA crossed above slow EMA",
}
_CUSTOM_PARAMS = {"ema_fast": 8, "ema_slow": 21}


@pytest.fixture(scope="module")
def btc_window():
    bars = data_store.load_candles("BTC/USD", "1h")
    if len(bars) < _MIN_BARS:
        pytest.skip(f"insufficient BTC/USD 1h history ({len(bars)} bars)")
    end_ms = bars[-1][0]
    start_ms = bars[max(backtest.WARMUP_BARS, len(bars) - 2200)][0]
    return start_ms, end_ms


def test_custom_strategy_executes_in_lab(btc_window):
    start_ms, end_ms = btc_window
    overrides = {_CUSTOM_KEY: {"spec": _CUSTOM_SPEC, "params": _CUSTOM_PARAMS}}
    r = backtest.run_backtest("BTC/USD", start_ms, end_ms, strategies=[_CUSTOM_KEY],
                              exit_method="atr", timeframe="1h", decl_overrides=overrides)
    assert "error" not in r, f"custom strategy errored: {r.get('error')}"
    assert r["entries"] > 0, "custom strategy generated zero entries in the Lab (regression!)"
    assert r["trades"] > 0, "custom strategy generated zero trades in the Lab (regression!)"
    # all trades attributed to the custom key — no cross-contamination with core strategies
    assert set(r.get("strategy_breakdown", {})) == {_CUSTOM_KEY}


def test_custom_strategy_without_overrides_is_dropped(btc_window):
    """Without decl_overrides an unknown custom key must NOT match core strategies
    (it simply produces no entries) — proving the override is what wires it in."""
    start_ms, end_ms = btc_window
    r = backtest.run_backtest("BTC/USD", start_ms, end_ms, strategies=[_CUSTOM_KEY],
                              exit_method="atr", timeframe="1h")
    assert "error" not in r
    assert r["entries"] == 0
    assert r["trades"] == 0


def test_multi_exit_forwards_custom_overrides(btc_window):
    """The exit-comparison path (run_multi_exit) must also replay custom strategies."""
    start_ms, end_ms = btc_window
    overrides = {_CUSTOM_KEY: {"spec": _CUSTOM_SPEC, "params": _CUSTOM_PARAMS}}
    r = backtest.run_multi_exit("BTC/USD", start_ms, end_ms, strategies=[_CUSTOM_KEY],
                                timeframe="1h", decl_overrides=overrides)
    assert r.get("entries") and r["entries"] > 0, "custom strategy produced no entries in exit comparison"


def test_unregister_imported_removes_from_registry():
    """Deleting an imported/cloned strategy must remove it from the schema registry so it no
    longer appears in /strategy/registry (else orphans clutter the Research picker forever)."""
    from strategy.declarative_defs import register_imported, unregister_imported
    from strategy.core import get_schema, list_schemas

    key = "clone-unregtest99"
    register_imported(key, "Unreg Test", "temp", _CUSTOM_SPEC, _CUSTOM_PARAMS)
    assert get_schema(key) is not None
    assert key in {s.key for s in list_schemas()}

    unregister_imported(key)
    assert get_schema(key) is None
    assert key not in {s.key for s in list_schemas()}

