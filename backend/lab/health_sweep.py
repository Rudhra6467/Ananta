"""
lab/health_sweep.py — Strategy Health precompute (pure aggregation, ZERO LLM credits).

Turns a rich multi-symbol / multi-timeframe backtest result (as produced by
LabWorker._run_backtest) into a compact per-strategy "health card" for the
Strategy Health Dashboard: best timeframe, best exit, regime performance,
MFE capture, and a plain-English recommendation badge.

The heavy compute (the backtests themselves) runs in LabWorker; this module only
summarises the already-computed numbers, so it is safe to call anywhere.
"""
from __future__ import annotations

from strategy.core import get_schema

# Fixed daily-sweep universe (deepest cached history; the main focus assets).
CORE_STRATEGIES = ["hunter", "squeeze", "continuation"]
SWEEP_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]
SWEEP_TIMEFRAMES = ["1h", "30m", "15m"]


def strategy_name(key: str) -> str:
    s = get_schema(key)
    return s.name if s else key


def _mode(values: list) -> str | None:
    """Most frequent non-null value; ties broken by first-seen order."""
    vals = [v for v in values if v]
    if not vals:
        return None
    counts: dict = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    return max(vals, key=lambda v: (counts[v], -vals.index(v)))


def recommendation(agg: dict) -> dict:
    """Map aggregate headline metrics → a recommendation badge for the health card."""
    tr = agg.get("total_return_pct") or 0.0
    pf = agg.get("profit_factor")
    dd = agg.get("max_drawdown_pct") or 0.0
    n = agg.get("trades") or 0
    if n < 5:
        return {"badge": "Not Recommended Currently", "tone": "negative",
                "reason": f"Only {n} trade(s) in this window — too few to judge. Widen the period or add assets."}
    if tr > 0 and (pf or 0) >= 1.3 and dd <= 25:
        return {"badge": "Good for Paper Trading", "tone": "positive",
                "reason": f"{tr:+.1f}% return, profit factor {pf:.2f}, contained {dd:.1f}% drawdown over {n} trades."}
    if tr > 0 and (pf or 0) >= 1.0:
        return {"badge": "Needs Improvement", "tone": "warning",
                "reason": f"Profitable ({tr:+.1f}%) but thin edge (PF {pf:.2f}) — optimise stops/trail before promoting."}
    if dd > 30:
        return {"badge": "Not Recommended Currently", "tone": "negative",
                "reason": f"{dd:.1f}% drawdown is excessive regardless of the {tr:+.1f}% return."}
    return {"badge": "Not Recommended Currently", "tone": "negative",
            "reason": f"Weak edge in this window ({tr:+.1f}% return, PF {pf if pf is not None else '—'})."}


def _merge_regime(per_symbol: dict) -> dict:
    """Sum per-regime buckets across symbols → {regime: {n, net_pnl, win_pct, avg_return_pct}}."""
    acc: dict = {}
    for m in per_symbol.values():
        if "error" in m:
            continue
        for reg, v in (m.get("regime_breakdown") or {}).items():
            if reg == "—":
                continue
            g = acc.setdefault(reg, {"n": 0, "wins": 0.0, "net": 0.0, "ret_w": 0.0})
            n = v.get("n") or 0
            g["n"] += n
            g["wins"] += (v.get("win_pct") or 0.0) / 100.0 * n
            g["net"] += v.get("net_pnl") or 0.0
            g["ret_w"] += (v.get("avg_return_pct") or 0.0) * n
    out = {}
    for reg, g in acc.items():
        n = g["n"] or 1
        out[reg] = {"n": g["n"], "net_pnl": round(g["net"], 2),
                    "win_pct": round(g["wins"] / n * 100.0, 1),
                    "avg_return_pct": round(g["ret_w"] / n, 3)}
    return out


def _best_exit(result: dict) -> str | None:
    """Most common winning exit config across symbols (prefers the 1h block)."""
    ec = result.get("exit_comparison") or {}
    labels = []
    for by_tf in ec.values():
        block = by_tf.get("1h") or next(iter(by_tf.values()), {})
        wk = block.get("winner_key")
        if wk:
            labels.append((block.get("rows") or {}).get(wk, {}).get("label", wk))
    return _mode(labels)


def _best_tf(result: dict) -> str | None:
    mtf = result.get("multi_timeframe") or {}
    tfs = [entry.get("verdict", {}).get("best_tf") for entry in mtf.values()]
    return _mode(tfs)


def aggregate_strategy(strategy_key: str, result: dict) -> dict:
    """Aggregate a full backtest result (all symbols/TFs) into one health card."""
    per = result.get("per_symbol") or {}
    valid = [m for m in per.values() if "error" not in m]
    name = strategy_name(strategy_key)
    if not valid:
        errs = [m.get("error") for m in per.values() if "error" in m]
        return {"strategy": strategy_key, "name": name, "error": errs[0] if errs else "no_result",
                "recommendation": {"badge": "Not Recommended Currently", "tone": "negative",
                                   "reason": "No trades or insufficient history in this window."}}

    trades = sum(m.get("trades") or 0 for m in valid)
    net_pnl = round(sum(m.get("net_pnl") or 0.0 for m in valid), 2)
    total_return = round(sum(m.get("total_return_pct") or 0.0 for m in valid) / len(valid), 3)
    win_w = sum((m.get("win_rate_pct") or 0.0) * (m.get("trades") or 0) for m in valid)
    win_rate = round(win_w / trades, 1) if trades else 0.0
    pfs = [m.get("profit_factor") for m in valid if m.get("profit_factor") is not None]
    pf = round(sum(pfs) / len(pfs), 2) if pfs else None
    max_dd = round(max((m.get("max_drawdown_pct") or 0.0) for m in valid), 2)
    sharpes = [m.get("sharpe") for m in valid if m.get("sharpe") is not None]
    sharpe = round(sum(sharpes) / len(sharpes), 3) if sharpes else None

    tot_mfe = sum((m.get("capture_stats") or {}).get("total_mfe_usd") or 0.0 for m in valid)
    tot_cap = sum((m.get("capture_stats") or {}).get("total_captured_usd") or 0.0 for m in valid)
    tot_left = sum((m.get("capture_stats") or {}).get("total_profit_left_usd") or 0.0 for m in valid)
    capture_rate = round(min(1.0, tot_cap / tot_mfe) * 100.0, 1) if tot_mfe > 0 else None

    regime = _merge_regime(per)
    best_regime = weak_regime = None
    if regime:
        ordered = sorted(regime.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)
        best_regime = ordered[0][0]
        if len(ordered) > 1:
            weak_regime = ordered[-1][0]

    headline = {"total_return_pct": total_return, "net_pnl": net_pnl, "win_rate_pct": win_rate,
                "profit_factor": pf, "max_drawdown_pct": max_dd, "sharpe": sharpe, "trades": trades}

    return {
        "strategy": strategy_key, "name": name,
        "best_timeframe": _best_tf(result),
        "best_exit": _best_exit(result),
        "regime_breakdown": regime,
        "best_regime": best_regime, "weak_regime": weak_regime,
        "capture_rate_pct": capture_rate,
        "total_mfe_usd": round(tot_mfe, 2), "total_captured_usd": round(tot_cap, 2),
        "profit_left_usd": round(tot_left, 2),
        "headline": headline,
        "recommendation": recommendation(headline),
        "per_symbol": {sym: {"trades": m.get("trades"), "total_return_pct": m.get("total_return_pct"),
                             "win_rate_pct": m.get("win_rate_pct"), "profit_factor": m.get("profit_factor"),
                             "max_drawdown_pct": m.get("max_drawdown_pct")}
                       for sym, m in per.items() if "error" not in m},
    }
