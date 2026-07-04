"""
Strategy Sandbox (Phase B · DIAGNOSTIC, credit-free).

Five conceptual market-regime strategies evaluated per asset each cycle as pure-math
classifiers (NO LLM). Only the Hunter is allowed to EXECUTE; the other four run in
SHADOW mode (logged + measured, never traded) so strategies can compete for 30-60 days
before any promotion. Signals ride on the existing research_log counterfactual resolver,
so win-rate / expectancy come "for free" as forward returns (24h/72h/7d) resolve.
"""
from __future__ import annotations

import logging

from setup_classifier import adx, atr, ema, percentile_rank, rsi

logger = logging.getLogger("ananta.strategies")

# id -> display metadata.  mode: EXECUTE (live paper trader) | SHADOW (research only)
STRATEGY_DEFS = [
    {"id": "hunter", "name": "Hunter / Aggressive Reversal", "scenario": "Reversal", "mode": "EXECUTE"},
    {"id": "vcp", "name": "Volatility Squeeze / VCP", "scenario": "Uncertain", "mode": "EXECUTE"},
    {"id": "trend_rider", "name": "Relative Strength / Bullish Trend Rider", "scenario": "Bullish", "mode": "SHADOW"},
    {"id": "bear_breakdown", "name": "Bear Breakdown", "scenario": "Bearish", "mode": "SHADOW"},
    {"id": "neutral_crab", "name": "Neutral Crab", "scenario": "Neutral", "mode": "SHADOW"},
]
STRATEGY_IDS = [d["id"] for d in STRATEGY_DEFS]

# WS1: minimum volume expansion (x trailing avg) required to qualify a squeeze breakout.
SQUEEZE_VOL_EXPANSION_MIN = 1.5


def _vol_slope(vols: list[float], window: int = 6) -> float:
    seg = vols[-window:]
    n = len(seg)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(seg) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    return sum((xs[i] - mx) * (seg[i] - my) for i in range(n)) / denom


def _bbwidth_series(closes: list[float], period: int = 20, k: float = 2.0) -> list[float]:
    """Bollinger Band Width % series = (upper-lower)/mid*100. Low = volatility squeeze."""
    out: list[float] = []
    for i in range(len(closes)):
        if i < period - 1:
            continue
        window = closes[i - period + 1:i + 1]
        m = sum(window) / period
        var = sum((c - m) ** 2 for c in window) / period
        sd = var ** 0.5
        out.append((2 * k * sd) / m * 100.0 if m else 0.0)
    return out


def scan_strategies(
    price: float,
    bars_4h: list[list[float]],
    relative_strength_btc: float | None,
    hunter_triggered: bool,
    support_zone: dict | None,
) -> dict:
    """Per-strategy research pipeline (pure compute, credit-free).

    Each strategy emits its OWN ``{detected, qualified, evidence}`` — Hunter filters
    are NEVER forced onto the others. ``detected`` = a raw opportunity exists;
    ``qualified`` = it survives that strategy's specific qualification framework.
    The breaker_state is attached by the caller (same for every strategy in a cycle).
    """
    blank = {
        d["id"]: {"detected": False, "qualified": False, "evidence": {"reason": "insufficient_bars"}}
        for d in STRATEGY_DEFS
    }
    if not bars_4h or len(bars_4h) < 60 or not price:
        return blank
    closes = [b[4] for b in bars_4h]
    highs = [b[2] for b in bars_4h]
    lows = [b[3] for b in bars_4h]
    vols = [b[5] for b in bars_4h]
    try:
        r = rsi(closes)[-1]
        ema50_series = ema(closes, 50)
        ema50 = ema50_series[-1]
        ema_rising = ema50 > ema50_series[-6]
        adx_val = adx(highs, lows, closes)[-1]
        atr_series = atr(highs, lows, closes)
        atr_pct = percentile_rank(atr_series, atr_series[-1])  # 0..100; low = coiling
        bbw = _bbwidth_series(closes)
        bbw_pct = percentile_rank(bbw, bbw[-1]) if len(bbw) > 5 else 100.0  # low = squeeze
        vslope = _vol_slope(vols)
        # WS1: squeeze breakout must show real volume expansion (1.5-1.8x trailing avg).
        _prior_vol = vols[-7:-1]
        _avg_prior_vol = (sum(_prior_vol) / len(_prior_vol)) if _prior_vol else 0.0
        vol_expansion = (vols[-1] / _avg_prior_vol) if _avg_prior_vol > 0 else 0.0
        rs = relative_strength_btc or 0.0
        sup_low = (support_zone or {}).get("low")
        touches = (support_zone or {}).get("touches") or 0
    except Exception as e:  # never let a math edge-case stall a cycle
        logger.warning("scan_strategies failed: %s", e)
        return blank

    # --- Hunter / Aggressive Reversal: support zone (detect) + RSI reset + volume exhaustion (qualify) ---
    hunter_detected = support_zone is not None
    hunter_qualified = bool(hunter_triggered)

    # --- Volatility Squeeze / VCP: ATR/BBWidth compression (detect) + tight squeeze + volume-expansion breakout (qualify) ---
    vcp_detected = atr_pct <= 40.0 or bbw_pct <= 40.0
    vcp_qualified = bool(atr_pct <= 25.0 and bbw_pct <= 25.0 and vslope > 0 and vol_expansion >= SQUEEZE_VOL_EXPANSION_MIN)

    # --- Relative Strength: outperforming BTC (detect) + positive trend structure + sector-beat proxy (qualify) ---
    rs_detected = rs > 0
    rs_qualified = bool(rs > 0 and price > ema50 and ema_rising and rs >= 0.02)

    # --- Bear Breakdown: below 50EMA (detect) + falling 50EMA + support breakdown + momentum (qualify) ---
    bear_detected = price < ema50
    bear_qualified = bool(
        price < ema50 and not ema_rising and sup_low is not None and price < sup_low and r < 45
    )

    # --- Neutral Crab: low ADX (detect) + established range + multiple S/R touches (qualify) ---
    crab_detected = adx_val < 25.0
    crab_qualified = bool(adx_val < 20.0 and 40 <= r <= 60 and touches >= 2)

    return {
        "hunter": {
            "detected": hunter_detected, "qualified": hunter_qualified,
            "evidence": {"rsi": round(r, 2), "has_support_zone": hunter_detected},
        },
        "vcp": {
            "detected": vcp_detected, "qualified": vcp_qualified,
            "evidence": {"atr_percentile": round(atr_pct, 1), "bbwidth_percentile": round(bbw_pct, 1),
                         "volume_slope": round(vslope, 4), "vol_expansion": round(vol_expansion, 2)},
        },
        "trend_rider": {
            "detected": rs_detected, "qualified": rs_qualified,
            "evidence": {"rs_vs_btc": round(rs, 3), "above_ema50": price > ema50, "ema_rising": ema_rising},
        },
        "bear_breakdown": {
            "detected": bear_detected, "qualified": bear_qualified,
            "evidence": {"below_ema50": price < ema50, "rsi": round(r, 2),
                         "support_break": bool(sup_low is not None and price < sup_low)},
        },
        "neutral_crab": {
            "detected": crab_detected, "qualified": crab_qualified,
            "evidence": {"adx": round(adx_val, 1), "rsi": round(r, 2), "sr_touches": touches},
        },
    }


# ---------- aggregation for the Scoreboard (reads research_log; resolved cf = win data) ----------
def _cf(r: dict):
    for f in ("cf_ret_72h", "cf_ret_7d", "cf_ret_24h"):
        if r.get(f) is not None:
            return r.get(f)
    return None


def summarize_strategy_sandbox(rows: list[dict], band_pct: float = 1.0, min_promote: int = 30) -> dict:
    """Competition scoreboard across the 5 strategies. Per strategy: signals, currently
    active, win rate, avg return, expectancy, net counterfactual P&L + a promotion verdict."""
    # latest row per symbol -> "active now" snapshot
    latest_active = {sid: 0 for sid in STRATEGY_IDS}
    seen_symbol = set()
    for r in sorted(rows, key=lambda x: x.get("timestamp", ""), reverse=True):
        sym = r.get("symbol")
        sig = r.get("strategy_signals") or {}
        if sym in seen_symbol:
            continue
        seen_symbol.add(sym)
        for sid in STRATEGY_IDS:
            if (sig.get(sid) or {}).get("active"):
                latest_active[sid] += 1

    out = []
    for d in STRATEGY_DEFS:
        sid = d["id"]
        signals = [r for r in rows if ((r.get("strategy_signals") or {}).get(sid) or {}).get("active")]
        resolved = [r for r in signals if _cf(r) is not None]
        rets = [_cf(r) for r in resolved]
        wins = [x for x in rets if x > band_pct]
        losses = [x for x in rets if x < -band_pct]
        win_rate = round(len(wins) / len(resolved) * 100, 1) if resolved else None
        avg_ret = round(sum(rets) / len(rets), 3) if rets else None
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        wr = (len(wins) / len(resolved)) if resolved else 0.0
        expectancy = round(wr * avg_win + (1 - wr) * avg_loss, 3) if resolved else None

        verdict = "Accumulating data…"
        if len(resolved) >= min_promote and expectancy is not None:
            if expectancy > 0 and (win_rate or 0) >= 50:
                verdict = "PROMOTION CANDIDATE" if d["mode"] == "SHADOW" else "Validated"
            else:
                verdict = "Underperforming"

        out.append({
            **d,
            "signals": len(signals),
            "resolved": len(resolved),
            "active_now": latest_active[sid],
            "win_rate_pct": win_rate,
            "avg_return_pct": avg_ret,
            "expectancy_pct": expectancy,
            "net_cf_pnl_pct": round(sum(rets), 3) if rets else None,
            "verdict": verdict,
        })
    return {"strategies": out, "promote_threshold": min_promote}


# ---------- Structure-based staged-exit shadow sim ("33/66/99", but level-driven) ----------
def simulate_staged_exit(
    avg_cost: float, qty: float, trough_price: float | None,
    structural_stop: float | None, support_low: float | None, actual_exit_price: float,
) -> dict | None:
    """Shadow-test Raunak's staged cut, but structure-driven (NOT round %):
      Tier 1 (33%): structure weakens -> price breaks the support-zone low
      Tier 2 (33%): trend breaks      -> price breaks the structural stop
      Tier 3 (34%): deep hard stop    -> structural stop * 0.985
    Each tranche is filled at its level if the trough reached it, else at the actual exit.
    Returns theoretical staged P&L vs the actual single-exit P&L."""
    if not avg_cost or avg_cost <= 0 or qty <= 0:
        return None
    sl = support_low or (structural_stop / 0.98 if structural_stop else None)
    ss = structural_stop or (sl * 0.98 if sl else None)
    if sl is None or ss is None:
        return None
    levels = {"L1": sl, "L2": ss, "L3": ss * 0.985}
    tranches = [(0.33, levels["L1"]), (0.33, levels["L2"]), (0.34, levels["L3"])]
    staged_unit = 0.0
    for frac, level in tranches:
        sell_px = level if (trough_price is not None and trough_price <= level) else actual_exit_price
        staged_unit += frac * (sell_px - avg_cost)
    staged_pnl = staged_unit * qty
    actual_pnl = (actual_exit_price - avg_cost) * qty
    return {
        "actual_pnl": round(actual_pnl, 6),
        "staged_pnl": round(staged_pnl, 6),
        "delta": round(staged_pnl - actual_pnl, 6),
        "levels": {k: round(v, 6) for k, v in levels.items()},
        "trough_price": trough_price,
        "actual_exit_price": actual_exit_price,
    }


def summarize_staged_exit(logs: list[dict]) -> dict:
    """Compare cumulative Actual (current structural hard-stop) vs Theoretical
    (structure-staged 33/33/34) performance across all closed shadow sims."""
    rows = [l for l in logs if l.get("actual_pnl") is not None and l.get("staged_pnl") is not None]
    actual = round(sum(l["actual_pnl"] for l in rows), 4)
    staged = round(sum(l["staged_pnl"] for l in rows), 4)
    better = len([l for l in rows if l["staged_pnl"] > l["actual_pnl"] + 1e-9])
    return {
        "sample": len(rows),
        "actual_pnl_total": actual,
        "staged_pnl_total": staged,
        "delta_total": round(staged - actual, 4),
        "staged_better_count": better,
        "verdict": "Accumulating data…" if len(rows) < 10 else (
            "Staged outperforms" if staged > actual else "Current rule outperforms"),
    }

