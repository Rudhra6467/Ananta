"""Tests for the 10-gate paper->live graduation scorecard (analytics.graduation_readiness)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from analytics import graduation_readiness


def _sell(pnl, ts, regime="NORMAL", exit_reason="TRAIL_HIT", ext=3.0, fee=0.05, slip=0.02):
    return {
        "side": "SELL", "status": "FILLED", "symbol": "BTC/USD",
        "quantity": 0.01, "price": 100.0, "notional": 1.0,
        "pnl": pnl, "fee_usd": fee, "slippage_usd": slip,
        "timestamp": ts.isoformat(), "volatility_regime": regime,
        "exit_reason": exit_reason, "entry_extension_pct": ext,
    }


def _spread_trades(n, pnl_pattern, *, base=None, regimes=None, days_span=40):
    """Build n SELLs spread across `days_span` days with given pnl pattern."""
    base = base or (datetime.now(UTC) - timedelta(days=days_span))
    out = []
    for i in range(n):
        ts = base + timedelta(days=(days_span * i / max(n - 1, 1)))
        pnl = pnl_pattern[i % len(pnl_pattern)]
        regime = (regimes[i % len(regimes)] if regimes else "NORMAL")
        out.append(_sell(pnl, ts, regime=regime))
    return out


def test_empty_is_not_ready():
    g = graduation_readiness([], starting_equity=300.0)
    assert g["all_passed"] is False
    assert g["passed_count"] == 0 or g["passed_count"] < g["total_gates"]
    assert g["total_gates"] == 10
    assert g["verdict"] == "NOT READY"


def test_min_trades_gate():
    trades = _spread_trades(10, [2.0, -1.0])
    g = graduation_readiness(trades, starting_equity=300.0)
    c = next(x for x in g["criteria"] if x["id"] == "min_trades")
    assert c["passed"] is False  # only 10 < 50


def test_profit_factor_and_expectancy_gates():
    # 60 trades, wins +2 / losses -1 across two regimes -> PF = 120/40 = 3.0
    trades = _spread_trades(60, [2.0, 2.0, -1.0], regimes=["NORMAL", "HIGH_PANIC"])
    g = graduation_readiness(trades, starting_equity=300.0)
    pf = next(x for x in g["criteria"] if x["id"] == "profit_factor")
    exp = next(x for x in g["criteria"] if x["id"] == "positive_expectancy")
    assert pf["passed"] is True
    assert exp["passed"] is True


def test_regime_diversification_fails_when_one_regime_carries_all():
    # all profits in NORMAL, HIGH_PANIC only loses -> single regime carries profit
    trades = []
    base = datetime.now(UTC) - timedelta(days=40)
    for i in range(60):
        ts = base + timedelta(days=40 * i / 59)
        if i % 2 == 0:
            trades.append(_sell(3.0, ts, regime="NORMAL"))
        else:
            trades.append(_sell(-0.5, ts, regime="HIGH_PANIC"))
    g = graduation_readiness(trades, starting_equity=300.0)
    c = next(x for x in g["criteria"] if x["id"] == "regime_diversification")
    assert c["passed"] is False  # only 1 positive regime


def test_regime_diversification_passes_when_spread():
    trades = []
    base = datetime.now(UTC) - timedelta(days=40)
    for i in range(60):
        ts = base + timedelta(days=40 * i / 59)
        regime = ["NORMAL", "HIGH_PANIC", "LOW_COMPRESSION"][i % 3]
        # each regime nets positive, balanced
        trades.append(_sell(2.0 if i % 4 != 0 else -1.0, ts, regime=regime))
    g = graduation_readiness(trades, starting_equity=300.0)
    c = next(x for x in g["criteria"] if x["id"] == "regime_diversification")
    assert c["passed"] is True


def test_account_survival_breach_fails():
    # one catastrophic loss draws account below the 20% ruin line
    base = datetime.now(UTC) - timedelta(days=40)
    trades = [_sell(2.0, base + timedelta(days=i)) for i in range(5)]
    trades.append(_sell(-80.0, base + timedelta(days=6)))  # $300 -> ~$230 = >20% DD from peak
    g = graduation_readiness(trades, starting_equity=300.0, account_max_drawdown_pct=20.0)
    survival = next(x for x in g["criteria"] if x["id"] == "account_survival")
    dd = next(x for x in g["criteria"] if x["id"] == "max_drawdown")
    assert survival["passed"] is False
    assert dd["passed"] is False
    assert g["metrics"]["max_drawdown_pct"] >= 20.0


def test_risk_consistency_fails_on_single_outlier():
    # 50 tiny wins + 1 huge win that is > 20% of gross profit
    base = datetime.now(UTC) - timedelta(days=40)
    trades = [_sell(1.0, base + timedelta(days=40 * i / 59)) for i in range(59)]
    trades.append(_sell(100.0, base + timedelta(days=40)))  # outlier
    g = graduation_readiness(trades, starting_equity=300.0)
    c = next(x for x in g["criteria"] if x["id"] == "risk_consistency")
    assert c["passed"] is False  # 100 / (59+100) ~ 63% > 20%


def test_stability_requires_30_days():
    # 60 trades but all within 5 days -> stability fails
    base = datetime.now(UTC) - timedelta(days=4)
    trades = [_sell(2.0 if i % 3 else -1.0, base + timedelta(days=4 * i / 59)) for i in range(60)]
    g = graduation_readiness(trades, starting_equity=300.0)
    c = next(x for x in g["criteria"] if x["id"] == "stability")
    assert c["passed"] is False


def test_metrics_surface_exit_and_chase_data():
    base = datetime.now(UTC) - timedelta(days=40)
    trades = [
        _sell(2.0, base + timedelta(days=1), exit_reason="TRAIL_HIT", ext=4.0),
        _sell(-1.0, base + timedelta(days=2), exit_reason="SL_HIT", ext=9.0),
        _sell(3.0, base + timedelta(days=3), exit_reason="TRAIL_HIT", ext=2.0),
    ]
    g = graduation_readiness(trades, starting_equity=300.0)
    m = g["metrics"]
    assert m["stop_loss_frequency_pct"] > 0
    assert m["trail_exit_count"] == 2
    assert m["avg_entry_extension_pct"] is not None
    assert m["entry_extension_sample"] == 3
    assert m["total_friction_usd"] >= 0


def test_full_pass_scenario_is_ready():
    # Construct a clean, diversified, stable, well-behaved track record.
    base = datetime.now(UTC) - timedelta(days=45)
    trades = []
    regimes = ["NORMAL", "HIGH_PANIC", "LOW_COMPRESSION"]
    for i in range(80):
        ts = base + timedelta(days=45 * i / 79)
        regime = regimes[i % 3]
        # ~70% win rate, small balanced wins/losses, no single outlier
        pnl = 2.0 if (i % 10) < 7 else -1.0
        # keep sideways calm: LOW_COMPRESSION trades net slightly positive, not over-traded
        trades.append(_sell(pnl, ts, regime=regime, exit_reason="TRAIL_HIT" if pnl > 0 else "SL_HIT", ext=3.0))
    g = graduation_readiness(trades, starting_equity=300.0)
    # All 10 gates should pass on this idealized track record
    failing = [c["id"] for c in g["criteria"] if not c["passed"]]
    assert g["all_passed"] is True, f"unexpected failing gates: {failing}"
    assert g["verdict"] == "READY"
