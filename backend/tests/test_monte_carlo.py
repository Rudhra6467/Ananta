"""Unit tests for the Monte Carlo risk-of-ruin simulator (pure math, no I/O)."""
import numpy as np

from lab.monte_carlo import run_monte_carlo


def test_insufficient_sample():
    r = run_monte_carlo([1.0, 2.0], iterations=500)
    assert r["ok"] is False
    assert r["sample_size"] == 2


def test_winning_edge_low_ruin():
    # Strongly positive edge: mostly wins, small losses -> low ruin, high prob profit.
    pnls = [5.0] * 40 + [-2.0] * 10
    r = run_monte_carlo(pnls, iterations=3000, starting_equity=1000.0, ruin_threshold_pct=25.0)
    assert r["ok"] is True
    assert r["risk_of_ruin_pct"] <= 5.0
    assert r["prob_profit_pct"] >= 60.0
    assert r["verdict"] in ("ROBUST", "ACCEPTABLE")
    assert r["final_return_pct"]["p5"] <= r["final_return_pct"]["median"] <= r["final_return_pct"]["p95"]
    assert len(r["histogram"]) == 12


def test_losing_edge_fragile():
    # Negative expectancy -> fragile, low prob profit.
    pnls = [-5.0] * 30 + [3.0] * 10
    r = run_monte_carlo(pnls, iterations=2000, starting_equity=1000.0, ruin_threshold_pct=25.0)
    assert r["ok"] is True
    assert r["prob_profit_pct"] < 50.0
    assert r["verdict"] == "FRAGILE"


def test_iterations_clamped_and_deterministic():
    pnls = [1.0, -1.0, 2.0, -0.5, 3.0, -2.0, 1.5, -1.0]
    r1 = run_monte_carlo(pnls, iterations=50)   # below floor -> clamped to 200
    r2 = run_monte_carlo(pnls, iterations=50)
    assert r1["iterations"] == 200
    # seeded rng -> reproducible
    assert r1["risk_of_ruin_pct"] == r2["risk_of_ruin_pct"]
    assert np.isfinite(r1["max_drawdown_pct"]["worst"])
