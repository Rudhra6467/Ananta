"""Tests for the Phase A analytics/research layer (analytics.py)."""
from __future__ import annotations

from analytics import (
    HIGH_BETA_SECTOR,
    compute_entry_volatility,
    compute_performance,
    regime_insight,
    sector_exposure,
    sector_for_symbol,
    volatility_regime,
)


# ---------- sector taxonomy ----------
def test_sector_mapping():
    assert sector_for_symbol("BTC/USD") == "Store of Value"
    assert sector_for_symbol("ETH/USDC") == HIGH_BETA_SECTOR
    assert sector_for_symbol("SOL/USD") == HIGH_BETA_SECTOR
    assert sector_for_symbol("ADA/USD") == HIGH_BETA_SECTOR
    assert sector_for_symbol("XRP/USD") == "Payments"
    assert sector_for_symbol("PAXG/USD") == "Altcoin / Commodity High Beta"
    assert sector_for_symbol("DOGE/USD") == "Altcoin / Commodity High Beta"


def test_high_beta_warning_fires_at_three():
    positions = [
        {"symbol": "ETH/USD", "quantity": 0.1},
        {"symbol": "SOL/USD", "quantity": 0.1},
        {"symbol": "ADA/USD", "quantity": 0.1},
        {"symbol": "BTC/USD", "quantity": 0.1},
    ]
    ex = sector_exposure(positions)
    assert ex["high_beta_count"] == 3
    assert ex["high_beta_warning"] is True
    assert ex["counts"]["Store of Value"] == 1


def test_high_beta_warning_below_threshold():
    positions = [
        {"symbol": "ETH/USD", "quantity": 0.1},
        {"symbol": "SOL/USD", "quantity": 0.1},
        {"symbol": "BTC/USD", "quantity": 0.1},
    ]
    ex = sector_exposure(positions)
    assert ex["high_beta_count"] == 2
    assert ex["high_beta_warning"] is False


def test_sector_exposure_ignores_zero_qty():
    positions = [
        {"symbol": "ETH/USD", "quantity": 0.0},
        {"symbol": "SOL/USD", "quantity": 0.1},
    ]
    ex = sector_exposure(positions)
    assert ex["high_beta_count"] == 1


# ---------- volatility regime ----------
def test_volatility_regime_buckets():
    assert volatility_regime(10.0) == "LOW_COMPRESSION"
    assert volatility_regime(55.0) == "NORMAL"
    assert volatility_regime(85.0) == "HIGH_PANIC"
    assert volatility_regime(None) == "UNKNOWN"


def test_compute_entry_volatility_short_history():
    atr, pct, regime = compute_entry_volatility([])
    assert atr is None and pct is None and regime == "UNKNOWN"


def test_compute_entry_volatility_with_bars():
    bars = [[i * 3600000, 100 + i, 100.5 + i, 99.5 + i, 100.2 + i, 1.0] for i in range(60)]
    atr, pct, regime = compute_entry_volatility(bars)
    assert atr is not None and atr > 0
    assert 0.0 <= pct <= 100.0
    assert regime in ("LOW_COMPRESSION", "NORMAL", "HIGH_PANIC")


# ---------- performance metrics ----------
def _sell(pnl, fee=0.1, slippage=0.0, regime="NORMAL", ts="2026-01-01T00:00:00+00:00"):
    return {"side": "SELL", "status": "FILLED", "pnl": pnl, "fee_usd": fee,
            "slippage_usd": slippage, "volatility_regime": regime, "timestamp": ts}


def test_expectancy_and_profit_factor():
    # 2 wins (+4, +2), 2 losses (-1, -1): win_rate=0.5, avg_win=3, loss_rate=0.5, avg_loss=1
    trades = [
        {"side": "BUY", "fee_usd": 0.1, "timestamp": "2026-01-01T00:00:00+00:00"},
        _sell(4.0, ts="2026-01-01T01:00:00+00:00"),
        _sell(2.0, ts="2026-01-01T02:00:00+00:00"),
        _sell(-1.0, ts="2026-01-01T03:00:00+00:00"),
        _sell(-1.0, ts="2026-01-01T04:00:00+00:00"),
    ]
    m = compute_performance(trades)
    assert m["closed_trades"] == 4
    assert m["win_rate_pct"] == 50.0
    assert m["avg_win_usd"] == 3.0
    assert m["avg_loss_usd"] == 1.0
    # expectancy = 0.5*3 - 0.5*1 = 1.0
    assert m["expectancy_usd"] == 1.0
    # profit factor = (4+2) / (1+1) = 3.0
    assert m["profit_factor"] == 3.0
    assert m["net_pnl_usd"] == 4.0
    # friction = fees on all 5 legs (0.1 each) = 0.5
    assert m["total_fees_usd"] == 0.5
    assert m["total_friction_usd"] == 0.5


def test_profit_factor_none_when_no_losses():
    trades = [_sell(1.0), _sell(2.0)]
    m = compute_performance(trades)
    assert m["profit_factor"] is None
    assert m["gross_loss_usd"] == 0.0


def test_regime_breakdown_groups_by_entry_regime():
    trades = [
        _sell(2.0, regime="HIGH_PANIC"),
        _sell(-1.0, regime="HIGH_PANIC"),
        _sell(3.0, regime="LOW_COMPRESSION"),
    ]
    m = compute_performance(trades)
    rb = m["regime_breakdown"]
    assert rb["HIGH_PANIC"]["trades"] == 2
    assert rb["HIGH_PANIC"]["wins"] == 1
    assert rb["HIGH_PANIC"]["win_rate_pct"] == 50.0
    assert rb["LOW_COMPRESSION"]["net_pnl_usd"] == 3.0
    assert abs(rb["HIGH_PANIC"]["expectancy_usd"] - 0.5) < 1e-6  # 0.5*2 - 0.5*1


def test_friction_includes_slippage():
    trades = [_sell(1.0, fee=0.2, slippage=0.05), _sell(-0.5, fee=0.2, slippage=0.05)]
    m = compute_performance(trades)
    assert m["total_fees_usd"] == 0.4
    assert m["total_slippage_usd"] == 0.1
    assert m["total_friction_usd"] == 0.5


# ---------- regime insight ("Best Regime to Trade") ----------
def test_regime_insight_not_ready_below_threshold():
    trades = [_sell(1.0, regime="NORMAL"), _sell(2.0, regime="HIGH_PANIC")]
    ins = regime_insight(trades)
    assert ins["ready"] is False
    assert ins["total_completed_trades"] == 2
    assert ins["best_regime"] is None
    assert "Accumulating Trade Data Base" in ins["insight_text"]
    assert "2/5" in ins["insight_text"]


def test_regime_insight_picks_highest_expectancy():
    trades = [
        # HIGH_PANIC: asymmetric wins -> highest expectancy
        _sell(3.5, regime="HIGH_PANIC"), _sell(-0.6, regime="HIGH_PANIC"),
        _sell(2.8, regime="HIGH_PANIC"),
        # NORMAL: steady but smaller
        _sell(0.8, regime="NORMAL"), _sell(0.6, regime="NORMAL"),
        # LOW_COMPRESSION: chop / losses
        _sell(-0.4, regime="LOW_COMPRESSION"), _sell(-0.3, regime="LOW_COMPRESSION"),
    ]
    ins = regime_insight(trades)
    assert ins["ready"] is True
    assert ins["best_regime"] == "HIGH_PANIC"
    assert ins["best_expectancy_usd"] > ins["regimes"]["NORMAL"]["expectancy_usd"]
    assert "HIGH_PANIC" in ins["insight_text"]
    assert ins["regimes"]["LOW_COMPRESSION"]["expectancy_usd"] < 0


def test_regime_insight_ignores_unknown_when_ranking():
    trades = [_sell(5.0, regime="UNKNOWN")] * 4 + [_sell(0.5, regime="NORMAL")]
    ins = regime_insight(trades)
    assert ins["ready"] is True  # 5 total
    assert ins["best_regime"] == "NORMAL"  # UNKNOWN excluded from ranking


def test_regime_insight_negative_edge_message():
    trades = [_sell(-0.5, regime="LOW_COMPRESSION") for _ in range(6)]
    ins = regime_insight(trades)
    assert ins["ready"] is True
    assert ins["best_expectancy_usd"] <= 0
    assert "No volatility regime shows a positive expectancy" in ins["insight_text"]


def test_max_drawdown_from_pnl_curve():
    # cumulative: +5, +3 (dd 2), +8, +4 (dd 4) -> max dd = 4
    trades = [_sell(5.0, ts="t1"), _sell(-2.0, ts="t2"), _sell(5.0, ts="t3"), _sell(-4.0, ts="t4")]
    m = compute_performance(trades)
    assert m["max_drawdown_usd"] == 4.0
