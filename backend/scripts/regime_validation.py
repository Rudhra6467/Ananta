"""Regime-enforcement validation re-run.

Compares, per strategy, over the SAME symbols / period / position size:
  * UNCONSTRAINED  — every strategy enabled across ALL 6 regimes (old "trade everywhere").
  * RECOMMENDED    — the shipped Recommended Matrix (per-strategy allowed_regimes + Tier-3 OFF).

Goal: show the regime filter is actually constraining entries (fewer trades, clustered in the
configured regimes only). Pure compute, zero LLM. Uses a per-symbol regime memo so we compute
classify_regime ONCE per symbol instead of once per strategy run.
"""
from __future__ import annotations

import json
import sys
import time

import lab.backtest as backtest
from lab import data_store as ds
import strategy_profiles as sp
from models import RiskSettings
import regime as _regime

LOT = 75.0
TP = round(LOT * 0.05, 4)     # 5% target profit ($)
SL = round(LOT * 0.035, 4)    # 3.5% target loss ($)
TIMEFRAME = "1h"

STRATEGIES = list(sp.RECOMMENDED.keys())  # 12 declarative + hunter (native aliases fire via engine)
SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD",
           "LINK/USD", "AAVE/USD", "PAXG/USD", "AVAX/USD", "RENDER/USD", "ARB/USD"]

_REGIME_MEMO: dict = {}
_real_classify = _regime.classify_regime


def _memo_classify(window):
    if not window:
        return _real_classify(window)
    key = (len(window), window[0][0], window[-1][0])
    r = _REGIME_MEMO.get(key)
    if r is None:
        r = _real_classify(window)
        _REGIME_MEMO[key] = r
    return r


def run_symbol(symbol: str):
    bars = ds.load_candles(symbol, TIMEFRAME)
    if len(bars) < backtest.WARMUP_BARS + 50:
        return None
    start, end = bars[backtest.WARMUP_BARS][0], bars[-1][0]
    s = RiskSettings()
    s.normal_lot_usd = LOT
    s.continuation_enabled = True

    _REGIME_MEMO.clear()
    unconstrained_prof = {k: {"enabled": True, "allowed_regimes": list(sp.REGIMES)} for k in STRATEGIES}
    recommended_prof = sp.recommended_matrix()

    out = {}
    for strat in STRATEGIES:
        res = {}
        for label, prof in (("unconstrained", unconstrained_prof), ("recommended", recommended_prof)):
            r = backtest.run_backtest(
                symbol, start, end, settings=s, strategies=[strat],
                exit_method="fixed", target_profit=TP, target_loss=SL,
                profile_overrides={strat: prof[strat]} if strat in prof else {strat: {"enabled": False}},
            )
            res[label] = {
                "entries": r.get("entries", 0),
                "trades": r.get("trades", 0),
                "net_pnl": round(r.get("net_pnl", 0.0) or 0.0, 2),
                "win_rate_pct": r.get("win_rate_pct"),
                "regime_breakdown": r.get("regime_breakdown", {}),
            }
        out[strat] = res
    return {"symbol": symbol, "period": [start, end], "bars": len(bars), "strategies": out}


def main():
    backtest.classify_regime = _memo_classify  # per-symbol memo (cleared each symbol)
    t0 = time.time()
    results = []
    syms = [x for x in SYMBOLS if ds.coverage(x, TIMEFRAME).get("count", 0) > backtest.WARMUP_BARS + 50] \
        if hasattr(ds.coverage(SYMBOLS[0], TIMEFRAME), "get") else SYMBOLS
    # coverage() may return a dict; fall back to trying all symbols
    syms = SYMBOLS
    for sym in syms:
        st = time.time()
        r = run_symbol(sym)
        if r is None:
            print(f"[skip] {sym} — insufficient candles", flush=True)
            continue
        results.append(r)
        print(f"[done] {sym} in {time.time()-st:.0f}s", flush=True)

    # ---- aggregate per strategy across symbols ----
    agg = {}
    for strat in STRATEGIES:
        a = {"unconstrained": {"entries": 0, "net_pnl": 0.0}, "recommended": {"entries": 0, "net_pnl": 0.0},
             "rec_regimes": sp.recommended_profile(strat).get("allowed_regimes"),
             "enabled": sp.recommended_profile(strat).get("enabled"),
             "rec_regime_breakdown": {}}
        for r in results:
            sres = r["strategies"].get(strat, {})
            for label in ("unconstrained", "recommended"):
                a[label]["entries"] += sres.get(label, {}).get("entries", 0)
                a[label]["net_pnl"] += sres.get(label, {}).get("net_pnl", 0.0)
            rb = sres.get("recommended", {}).get("regime_breakdown", {}) or {}
            for rk, rv in rb.items():
                cur = a["rec_regime_breakdown"].get(rk, 0)
                cnt = rv.get("trades") if isinstance(rv, dict) else rv
                a["rec_regime_breakdown"][rk] = cur + (cnt or 0)
        a["unconstrained"]["net_pnl"] = round(a["unconstrained"]["net_pnl"], 2)
        a["recommended"]["net_pnl"] = round(a["recommended"]["net_pnl"], 2)
        agg[strat] = a

    total_unc = sum(a["unconstrained"]["entries"] for a in agg.values())
    total_rec = sum(a["recommended"]["entries"] for a in agg.values())
    pnl_unc = round(sum(a["unconstrained"]["net_pnl"] for a in agg.values()), 2)
    pnl_rec = round(sum(a["recommended"]["net_pnl"] for a in agg.values()), 2)

    report = {
        "config": {"lot_usd": LOT, "tp_usd": TP, "sl_usd": SL, "tp_pct": 5.0, "sl_pct": 3.5,
                   "timeframe": TIMEFRAME, "symbols": [r["symbol"] for r in results]},
        "matrix_version": sp.MATRIX_VERSION,
        "totals": {"unconstrained_entries": total_unc, "recommended_entries": total_rec,
                   "unconstrained_net_pnl": pnl_unc, "recommended_net_pnl": pnl_rec,
                   "entry_reduction_pct": round(100 * (total_unc - total_rec) / total_unc, 1) if total_unc else None},
        "per_strategy": agg,
        "per_symbol": results,
        "took_seconds": round(time.time() - t0, 1),
    }
    with open("/app/backend/scripts/regime_validation_result.json", "w") as f:
        json.dump(report, f, indent=2)

    # ---- console table ----
    print("\n================ REGIME VALIDATION ================", flush=True)
    print(f"lot=${LOT}  TP=${TP}(5%)  SL=${SL}(3.5%)  tf={TIMEFRAME}  symbols={len(results)}  matrix={sp.MATRIX_VERSION}")
    print(f"{'strategy':<22} {'unc_ent':>8} {'rec_ent':>8} {'unc_pnl':>10} {'rec_pnl':>10}  rec_regimes")
    for strat, a in agg.items():
        tag = "" if a["enabled"] else " (OFF)"
        print(f"{strat:<22} {a['unconstrained']['entries']:>8} {a['recommended']['entries']:>8} "
              f"{a['unconstrained']['net_pnl']:>10} {a['recommended']['net_pnl']:>10}  "
              f"{a['rec_regimes']}{tag}", flush=True)
    print("-" * 66)
    print(f"{'TOTAL':<22} {total_unc:>8} {total_rec:>8} {pnl_unc:>10} {pnl_rec:>10}", flush=True)
    print(f"entry reduction: {report['totals']['entry_reduction_pct']}%")
    print("saved -> /app/backend/scripts/regime_validation_result.json", flush=True)


if __name__ == "__main__":
    main()
