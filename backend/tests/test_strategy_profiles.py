"""Strategy Profile: per-strategy allowed-regimes + disabled state must be honoured in the
Research Lab (and, by the same helper, live). Also covers the recommended-matrix + normalize.
"""
from __future__ import annotations

import pytest

import strategy_profiles as sp
from lab import backtest, data_store


def test_regime_allowed_semantics():
    # 2026-07-26 change: empty/absent allowed_regimes == DISABLED (was "trade all").
    assert sp.regime_allowed(None, "TREND_UP") is False                       # unconfigured = benched
    assert sp.regime_allowed({"enabled": True, "allowed_regimes": []}, "X") is False   # empty = benched
    assert sp.regime_allowed({"enabled": False, "allowed_regimes": ["TREND_UP"]}, "TREND_UP") is False
    prof = {"enabled": True, "allowed_regimes": ["TREND_UP", "COMPRESSION"]}
    assert sp.regime_allowed(prof, "TREND_UP") is True
    assert sp.regime_allowed(prof, "RANGE") is False


def test_recommended_matrix_shapes():
    ema = sp.recommended_profile("ema-cross")
    assert ema["allowed_regimes"] == ["COMPRESSION", "RANGE"] and ema["exit_method"] == "fixed"
    assert ema["exit_params"] == {"target_profit": 5.0, "target_loss": 3.5}
    assert sp.recommended_profile("rsi-momentum")["enabled"] is False   # benched
    assert sp.recommended_profile("rsi-momentum")["allowed_regimes"] == []
    assert sp.recommended_profile("nope") is None
    assert len(sp.REGIMES) == 6


def test_normalize_drops_junk():
    p = sp.normalize_profile({"enabled": 1, "allowed_regimes": ["TREND_UP", "BOGUS"],
                              "exit_method": "weird", "exit_params": {"atr_multiplier": 3, "junk": 9}})
    assert p["allowed_regimes"] == ["TREND_UP"]
    assert p["exit_method"] == "native"          # invalid method -> native
    assert p["exit_params"] == {"atr_multiplier": 3}


@pytest.fixture(scope="module")
def btc_window():
    bars = data_store.load_candles("BTC/USD", "1h")
    if len(bars) < backtest.WARMUP_BARS + 400:
        pytest.skip("insufficient BTC/USD 1h history")
    return bars[max(backtest.WARMUP_BARS, len(bars) - 2500)][0], bars[-1][0]


def test_lab_regime_filter_and_disable(btc_window):
    start, end = btc_window
    # Baseline: ema-cross explicitly enabled across ALL regimes (unconstrained) → full entry set.
    base = backtest.run_backtest("BTC/USD", start, end, strategies=["ema-cross"], exit_method="atr", timeframe="1h",
                                 profile_overrides={"ema-cross": {"enabled": True, "allowed_regimes": list(sp.REGIMES)}})
    filt = backtest.run_backtest("BTC/USD", start, end, strategies=["ema-cross"], exit_method="atr", timeframe="1h",
                                 profile_overrides={"ema-cross": {"enabled": True, "allowed_regimes": ["TREND_UP"]}})
    off = backtest.run_backtest("BTC/USD", start, end, strategies=["ema-cross"], exit_method="atr", timeframe="1h",
                                profile_overrides={"ema-cross": {"enabled": False, "allowed_regimes": []}})
    # New semantics: NO profile at all == benched == zero entries (empty allowed_regimes disabled).
    no_prof = backtest.run_backtest("BTC/USD", start, end, strategies=["ema-cross"], exit_method="atr", timeframe="1h")
    assert filt["entries"] <= base["entries"]
    assert set(filt.get("regime_breakdown", {})) <= {"TREND_UP"}
    assert off["entries"] == 0
    assert no_prof["entries"] == 0
