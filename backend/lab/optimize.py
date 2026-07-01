"""
lab/optimize.py — parameter sweeps, sensitivity, and Walk-Forward Analysis.

Anti-curve-fit toolkit built on the parity-guaranteed replay engine (lab.backtest):
  * grid_search   — sweep a param grid over ONE window; rank combos (see the plateau).
  * sensitivity   — vary ONE parameter; report metric per value + a robustness verdict.
  * walk_forward  — rolling optimize (In-Sample) -> test (Out-of-Sample) folds; report
                    the WFA efficiency (how much in-sample edge survives OOS).

Param grid keys use a target prefix so one grid can mix risk-setting and exit-profile
sweeps, per-strategy:
    "set:stop_loss_pct"            -> RiskSettings.stop_loss_pct
    "set:rsi_reset_max"            -> RiskSettings.rsi_reset_max (Hunter "wait" tuning)
    "prof:squeeze:trail_atr_mult"  -> Squeeze exit profile ATR trail multiple
    "prof:hunter:profit_arm_pct"   -> Hunter profit-protection arm threshold
All pure-compute and 100% credit-free (runs against historical_candles.db).
"""
from __future__ import annotations

import itertools
import logging
import statistics

from lab import backtest, data_store

logger = logging.getLogger("ananta.lab.optimize")

MIN_TRADES = 8  # combos/folds with fewer trades are statistically untrustworthy


def _metric(summary: dict, name: str) -> float:
    if summary.get("error") or summary.get("trades", 0) == 0:
        return -1e9
    if name == "return_over_dd":
        return summary["total_return_pct"] / max(summary["max_drawdown_pct"], 1.0)
    return float(summary.get(name, summary["total_return_pct"]))


def _split_overrides(combo: dict) -> tuple[dict, dict]:
    """Translate a flat combo {prefixed_key: value} into (setting_overrides, profile_overrides)."""
    so: dict = {}
    po: dict = {}
    for key, val in combo.items():
        if key.startswith("set:"):
            so[key[4:]] = val
        elif key.startswith("prof:"):
            _, strat, field = key.split(":", 2)
            po.setdefault(strat, {})[field] = val
    return so, po


def _expand(grid: dict) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*[grid[k] for k in keys])]


def _run(symbols: list[str], start_ms: int, end_ms: int, so: dict, po: dict) -> dict:
    """Run a combo across one or more symbols; aggregate into a portfolio-level summary."""
    per = []
    for sym in symbols:
        r = backtest.run_backtest(sym, start_ms, end_ms, setting_overrides=so or None,
                                  profile_overrides=po or None)
        if "error" not in r:
            per.append(r)
    if not per:
        return {"error": "no_runs", "trades": 0}
    trades = sum(r["trades"] for r in per)
    wins = sum(r["win_rate_pct"] * r["trades"] for r in per) / trades if trades else 0.0
    return {
        "symbols": [r["symbol"] for r in per],
        "trades": trades,
        "total_return_pct": round(statistics.mean(r["total_return_pct"] for r in per), 3),
        "win_rate_pct": round(wins, 1),
        "max_drawdown_pct": round(max(r["max_drawdown_pct"] for r in per), 2),
        "avg_trade_quality": round(statistics.mean(
            r["avg_trade_quality"] for r in per if r["avg_trade_quality"] is not None), 1)
            if any(r["avg_trade_quality"] is not None for r in per) else None,
    }


def grid_search(symbols, start_ms, end_ms, grid: dict, metric: str = "return_over_dd",
                min_trades: int = MIN_TRADES) -> dict:
    """Sweep the full grid over [start_ms, end_ms]; return combos ranked by `metric`."""
    if isinstance(symbols, str):
        symbols = [symbols]
    results = []
    for combo in _expand(grid):
        so, po = _split_overrides(combo)
        summ = _run(symbols, start_ms, end_ms, so, po)
        m = _metric(summ, metric) if summ["trades"] >= min_trades else -1e9
        results.append({"params": combo, "metric": round(m, 4) if m > -1e8 else None,
                        "trades": summ["trades"], "total_return_pct": summ.get("total_return_pct"),
                        "win_rate_pct": summ.get("win_rate_pct"),
                        "max_drawdown_pct": summ.get("max_drawdown_pct")})
    ranked = sorted(results, key=lambda x: (x["metric"] is not None, x["metric"] or -1e9), reverse=True)
    return {"metric": metric, "combos_tested": len(results), "best": ranked[0] if ranked else None,
            "ranked": ranked}


def sensitivity(symbols, start_ms, end_ms, target: str, values: list,
                metric: str = "total_return_pct", min_trades: int = MIN_TRADES) -> dict:
    """Vary a SINGLE parameter across `values`; expose plateau (robust) vs cliff (fragile)."""
    gs = grid_search(symbols, start_ms, end_ms, {target: values}, metric, min_trades)
    curve = [{"value": r["params"][target], "metric": r["metric"], "trades": r["trades"],
              "total_return_pct": r["total_return_pct"]} for r in gs["ranked"]]
    curve.sort(key=lambda x: x["value"])
    valid = [c["metric"] for c in curve if c["metric"] is not None]
    if len(valid) >= 3:
        spread = max(valid) - min(valid)
        mean = statistics.mean(valid)
        cv = statistics.pstdev(valid) / abs(mean) if mean else float("inf")
        verdict = "ROBUST (flat plateau)" if cv < 0.35 else "FRAGILE (sharp cliff — likely curve-fit)"
    else:
        spread = cv = None
        verdict = "INSUFFICIENT_DATA"
    return {"target": target, "metric": metric, "curve": curve,
            "spread": round(spread, 4) if spread is not None else None,
            "coeff_variation": round(cv, 3) if cv is not None else None, "verdict": verdict}


def _usable_window(symbols: list[str], timeframe: str = "4h") -> tuple[int, int] | None:
    """Intersection of available history across symbols, past the warmup buffer."""
    lo, hi = None, None
    for sym in symbols:
        bars = data_store.load_candles(sym, timeframe)
        if len(bars) < backtest.WARMUP_BARS + 20:
            continue
        s_ts = bars[backtest.WARMUP_BARS][0]
        e_ts = bars[-1][0]
        lo = s_ts if lo is None else max(lo, s_ts)
        hi = e_ts if hi is None else min(hi, e_ts)
    if lo is None or hi is None or lo >= hi:
        return None
    return lo, hi


def walk_forward(symbols, grid: dict, folds: int = 5, metric: str = "return_over_dd",
                 min_trades: int = MIN_TRADES) -> dict:
    """Rolling In-Sample optimize -> Out-of-Sample test. Each fold optimizes on a train
    block then evaluates the FROZEN best params on the next (unseen) test block."""
    if isinstance(symbols, str):
        symbols = [symbols]
    win = _usable_window(symbols)
    if win is None:
        return {"error": "insufficient_history", "symbols": symbols}
    w0, wN = win
    seg = (wN - w0) // (folds + 1)
    if seg <= 0:
        return {"error": "window_too_small"}

    fold_reports = []
    is_metrics, oos_metrics = [], []
    for k in range(folds):
        is_start = w0 + k * seg
        is_end = w0 + (k + 1) * seg
        oos_start = is_end
        oos_end = w0 + (k + 2) * seg
        gs = grid_search(symbols, is_start, is_end, grid, metric, min_trades)
        best = gs["best"]
        if not best or best["metric"] is None:
            fold_reports.append({"fold": k + 1, "skipped": "no_valid_IS_combo"})
            continue
        so, po = _split_overrides(best["params"])
        oos = _run(symbols, oos_start, oos_end, so, po)
        oos_m = _metric(oos, metric) if oos["trades"] >= min_trades else None
        is_metrics.append(best["metric"])
        if oos_m is not None:
            oos_metrics.append(oos_m)
        fold_reports.append({
            "fold": k + 1,
            "is_window": [is_start, is_end], "oos_window": [oos_start, oos_end],
            "best_params": best["params"], "is_metric": best["metric"],
            "oos_metric": round(oos_m, 4) if oos_m is not None else None,
            "oos_trades": oos["trades"], "oos_return_pct": oos.get("total_return_pct"),
        })

    avg_is = round(statistics.mean(is_metrics), 4) if is_metrics else None
    avg_oos = round(statistics.mean(oos_metrics), 4) if oos_metrics else None
    efficiency = round(avg_oos / avg_is, 3) if (avg_is and avg_oos is not None and avg_is > 0) else None
    positive = sum(1 for m in oos_metrics if m > 0)
    return {
        "metric": metric, "folds": folds, "fold_reports": fold_reports,
        "avg_is_metric": avg_is, "avg_oos_metric": avg_oos,
        "wfa_efficiency": efficiency,           # OOS/IS: closer to 1.0 = edge survives; low = overfit
        "oos_positive_folds": f"{positive}/{len(oos_metrics)}" if oos_metrics else "0/0",
        "verdict": (
            "NO IN-SAMPLE EDGE — strategy unprofitable in-sample over these folds"
            if avg_is is not None and avg_is <= 0
            else "ROBUST — edge holds out-of-sample" if efficiency is not None and efficiency >= 0.5
            else "WEAK/OVERFIT — in-sample edge does not survive" if efficiency is not None
            else "INCONCLUSIVE — too few valid folds/trades"
        ),
    }
