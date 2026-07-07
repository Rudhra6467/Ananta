"""Monte Carlo risk-of-ruin simulator.

Given a sample of realised per-trade P&L (in USD), we bootstrap thousands of randomised
trade-order sequences and walk an equity curve for each. This exposes the *distribution* of
outcomes an edge can produce — not just the single historical path — and quantifies the
probability of ruin (equity breaching a drawdown floor) and the probability of profit.

Pure-numpy, no external calls. We bootstrap (resample with replacement) the realised trade
multiset to project a forward sequence of the same length — this is the standard risk-of-ruin
Monte Carlo and varies both the final equity and the path (drawdown).
"""
from __future__ import annotations

import numpy as np


def run_monte_carlo(
    pnls: list[float],
    *,
    iterations: int = 2000,
    starting_equity: float = 1000.0,
    ruin_threshold_pct: float = 25.0,
    horizon: int | None = None,
) -> dict:
    """Bootstrap trade-order sequences and summarise the outcome distribution.

    - ``ruin`` = an equity path dips to/below starting_equity * (1 - ruin_threshold_pct/100)
      at ANY point during the sequence.
    - Returns percentile bands of the final equity, risk-of-ruin, prob-of-profit,
      the max-drawdown distribution and a histogram of final returns.
    """
    clean = [float(p) for p in pnls if p is not None and np.isfinite(p)]
    n = len(clean)
    if n < 5:
        return {"ok": False, "reason": "need at least 5 closed trades", "sample_size": n}

    iterations = int(max(200, min(20000, iterations)))
    horizon = int(horizon) if horizon else n
    horizon = max(5, min(horizon, n))
    ruin_floor = starting_equity * (1.0 - ruin_threshold_pct / 100.0)

    base = np.array(clean, dtype=float)
    rng = np.random.default_rng(42)

    final_equities = np.empty(iterations, dtype=float)
    max_drawdowns = np.empty(iterations, dtype=float)  # in %
    ruined = 0

    for i in range(iterations):
        # bootstrap: resample the trade multiset WITH replacement to project a forward
        # sequence of `horizon` trades — this varies both the endpoint and the path.
        seq = rng.choice(base, size=horizon, replace=True)
        curve = starting_equity + np.cumsum(seq)
        peak = np.maximum.accumulate(np.concatenate(([starting_equity], curve)))
        trough = np.concatenate(([starting_equity], curve))
        dd = (trough - peak) / peak  # negative fractions
        max_dd_pct = float(-dd.min() * 100.0)
        max_drawdowns[i] = max_dd_pct
        final_equities[i] = float(curve[-1])
        if curve.min() <= ruin_floor:
            ruined += 1

    final_returns_pct = (final_equities - starting_equity) / starting_equity * 100.0

    def pct(a, q):
        return round(float(np.percentile(a, q)), 2)

    risk_of_ruin = round(100.0 * ruined / iterations, 2)
    prob_profit = round(100.0 * float(np.mean(final_equities > starting_equity)), 2)

    # histogram of final returns (12 bins)
    counts, edges = np.histogram(final_returns_pct, bins=12)
    histogram = [
        {"lo": round(float(edges[j]), 2), "hi": round(float(edges[j + 1]), 2), "count": int(counts[j])}
        for j in range(len(counts))
    ]

    # verdict: institutional-style pass gate
    if risk_of_ruin <= 5.0 and prob_profit >= 60.0:
        verdict = "ROBUST"
    elif risk_of_ruin <= 15.0 and prob_profit >= 50.0:
        verdict = "ACCEPTABLE"
    else:
        verdict = "FRAGILE"

    return {
        "ok": True,
        "sample_size": n,
        "iterations": iterations,
        "horizon": horizon,
        "starting_equity": round(starting_equity, 2),
        "ruin_threshold_pct": ruin_threshold_pct,
        "ruin_floor": round(ruin_floor, 2),
        "risk_of_ruin_pct": risk_of_ruin,
        "prob_profit_pct": prob_profit,
        "verdict": verdict,
        "final_return_pct": {
            "p5": pct(final_returns_pct, 5),
            "p25": pct(final_returns_pct, 25),
            "median": pct(final_returns_pct, 50),
            "p75": pct(final_returns_pct, 75),
            "p95": pct(final_returns_pct, 95),
            "mean": round(float(np.mean(final_returns_pct)), 2),
        },
        "max_drawdown_pct": {
            "median": round(float(np.percentile(max_drawdowns, 50)), 2),
            "p95": round(float(np.percentile(max_drawdowns, 95)), 2),
            "worst": round(float(np.max(max_drawdowns)), 2),
        },
        "histogram": histogram,
    }
