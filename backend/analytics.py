"""
Quantitative Analytics / Research Layer (Phase A).

Pure, side-effect-free helpers for:
  * sector taxonomy + correlation (high-beta) exposure detection
  * entry-time volatility regime tagging (ATR-14 + percentile)
  * performance metrics over a set of closed trades:
      - Statistical Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
      - Profit Factor          = gross_profit / gross_loss
      - win/loss asymmetry, drawdown, friction (fees + slippage)
      - per-volatility-regime breakdown

No network, no DB — the server layer feeds in already-loaded trade docs.
"""
from __future__ import annotations

from setup_classifier import atr, percentile_rank

# ---------------- sector taxonomy ----------------------------------------
HIGH_BETA_SECTOR = "Layer 1 High Beta"
HIGH_BETA_WARNING_THRESHOLD = 3  # >= this many open positions in one high-beta sector

SECTOR_MAP: dict[str, str] = {
    "BTC": "Store of Value",
    "ETH": HIGH_BETA_SECTOR,
    "SOL": HIGH_BETA_SECTOR,
    "ADA": HIGH_BETA_SECTOR,
    "XRP": "Payments",
    "PAXG": "Altcoin / Commodity High Beta",
}
DEFAULT_SECTOR = "Altcoin / Commodity High Beta"


def sector_for_symbol(symbol: str) -> str:
    """Map a trading symbol (e.g. 'ETH/USDC') to its sector. USDC/USD quote
    variants inherit the base coin's sector."""
    if not symbol:
        return DEFAULT_SECTOR
    base = symbol.split("/")[0].upper().strip()
    return SECTOR_MAP.get(base, DEFAULT_SECTOR)


def sector_exposure(positions: list[dict]) -> dict:
    """Group OPEN positions by sector and flag high-beta concentration.

    `positions` is a list of dicts each with at least a 'symbol' (and optional
    'sector'). Returns counts per sector + a high_beta_warning bool that fires
    when >= HIGH_BETA_WARNING_THRESHOLD positions share the Layer-1 High Beta
    sector.
    """
    counts: dict[str, int] = {}
    for p in positions:
        if float(p.get("quantity", 0) or 0) <= 0:
            continue
        sector = p.get("sector") or sector_for_symbol(p.get("symbol", ""))
        counts[sector] = counts.get(sector, 0) + 1
    high_beta_count = counts.get(HIGH_BETA_SECTOR, 0)
    return {
        "counts": counts,
        "high_beta_sector": HIGH_BETA_SECTOR,
        "high_beta_count": high_beta_count,
        "high_beta_threshold": HIGH_BETA_WARNING_THRESHOLD,
        "high_beta_warning": high_beta_count >= HIGH_BETA_WARNING_THRESHOLD,
    }


# ---------------- volatility regime --------------------------------------
def volatility_regime(atr_percentile: float | None) -> str:
    """Bucket an ATR percentile (0-100) into a market-regime tag."""
    if atr_percentile is None:
        return "UNKNOWN"
    if atr_percentile < 40.0:
        return "LOW_COMPRESSION"
    if atr_percentile < 70.0:
        return "NORMAL"
    return "HIGH_PANIC"


def compute_entry_volatility(bars_1h: list[list[float]]) -> tuple[float | None, float | None, str]:
    """Compute ATR(14), its percentile rank (vs the last ~30d of 1h ATRs) and
    the regime tag at the moment of entry. Returns (atr, atr_pct, regime).

    Degrades gracefully to (None, None, 'UNKNOWN') when history is too short.
    """
    if not bars_1h or len(bars_1h) < 15:
        return None, None, "UNKNOWN"
    highs = [b[2] for b in bars_1h]
    lows = [b[3] for b in bars_1h]
    closes = [b[4] for b in bars_1h]
    atr_series = atr(highs, lows, closes, 14)
    if not atr_series:
        return None, None, "UNKNOWN"
    current_atr = atr_series[-1]
    lookback = min(720, len(atr_series))  # 30 days * 24h
    atr_pct = percentile_rank(atr_series[-lookback:], current_atr)
    return round(current_atr, 8), round(atr_pct, 2), volatility_regime(atr_pct)


# ---------------- performance metrics ------------------------------------
def _safe_mean(xs: list[float]) -> float:
    return (sum(xs) / len(xs)) if xs else 0.0


def _max_drawdown(realized_pnls_in_time_order: list[float]) -> float:
    """Max drawdown (in USD) of the cumulative realized-PnL curve."""
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in realized_pnls_in_time_order:
        cum += p
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return round(max_dd, 4)


def compute_performance(trades: list[dict]) -> dict:
    """Compute the quantitative metrics over a window of trade docs.

    `trades` may contain both BUY and SELL legs. Closed round-trips are the
    SELL legs (which carry realized `pnl`). Friction (fees + slippage) is summed
    across ALL legs in the window.
    """
    # Closed trades = SELL legs (realized pnl lives there), oldest-first for DD.
    sells = [t for t in trades if t.get("side") == "SELL" and t.get("status", "FILLED") == "FILLED"]
    sells_time_sorted = sorted(sells, key=lambda t: t.get("timestamp", ""))

    pnls = [float(t.get("pnl", 0.0) or 0.0) for t in sells]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)

    win_rate = (len(wins) / n) if n else 0.0
    loss_rate = (len(losses) / n) if n else 0.0
    avg_win = _safe_mean(wins)
    avg_loss = _safe_mean([abs(p) for p in losses])  # positive magnitude
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

    gross_profit = sum(wins)
    gross_loss = sum(abs(p) for p in losses)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    total_fees = sum(float(t.get("fee_usd", 0.0) or 0.0) for t in trades)
    total_slippage = sum(float(t.get("slippage_usd", 0.0) or 0.0) for t in trades)

    # Per-regime breakdown (attributed to the entry regime carried on the SELL).
    regime_pnls: dict[str, list[float]] = {}
    for t in sells:
        regime = t.get("volatility_regime") or "UNKNOWN"
        regime_pnls.setdefault(regime, []).append(float(t.get("pnl", 0.0) or 0.0))
    regimes = {r: _regime_stats(p) for r, p in regime_pnls.items()}

    return {
        "closed_trades": n,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round(win_rate * 100.0, 2),
        "loss_rate_pct": round(loss_rate * 100.0, 2),
        "avg_win_usd": round(avg_win, 4),
        "avg_loss_usd": round(avg_loss, 4),
        "expectancy_usd": round(expectancy, 4),
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "gross_profit_usd": round(gross_profit, 4),
        "gross_loss_usd": round(gross_loss, 4),
        "net_pnl_usd": round(sum(pnls), 4),
        "win_loss_asymmetry": round(avg_win / avg_loss, 3) if avg_loss > 0 else None,
        "max_drawdown_usd": _max_drawdown([float(t.get("pnl", 0.0) or 0.0) for t in sells_time_sorted]),
        "total_fees_usd": round(total_fees, 4),
        "total_slippage_usd": round(total_slippage, 4),
        "total_friction_usd": round(total_fees + total_slippage, 4),
        "regime_breakdown": regimes,
    }


def _regime_stats(pnls: list[float]) -> dict:
    """Full per-regime stat block (expectancy, profit factor, win rate)."""
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / n) if n else 0.0
    loss_rate = (len(losses) / n) if n else 0.0
    avg_win = _safe_mean(wins)
    avg_loss = _safe_mean([abs(p) for p in losses])
    gross_profit = sum(wins)
    gross_loss = sum(abs(p) for p in losses)
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate * 100.0, 2),
        "avg_win_usd": round(avg_win, 4),
        "avg_loss_usd": round(avg_loss, 4),
        "expectancy_usd": round((win_rate * avg_win) - (loss_rate * avg_loss), 4),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "net_pnl_usd": round(sum(pnls), 4),
    }


MIN_TRADES_FOR_INSIGHT = 5


def _parse_ts(ts: str):
    """Parse an ISO timestamp; return None on failure."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _equity_drawdown_pct(pnls_time_sorted: list[float], starting_equity: float) -> float:
    """Max peak-to-trough drawdown of the equity curve (start + cumulative pnl), in %."""
    if starting_equity <= 0:
        return 0.0
    equity = starting_equity
    peak = starting_equity
    max_dd_pct = 0.0
    for p in pnls_time_sorted:
        equity += p
        peak = max(peak, equity)
        if peak > 0:
            dd = (peak - equity) / peak * 100.0
            max_dd_pct = max(max_dd_pct, dd)
    return round(max_dd_pct, 3)


def graduation_readiness(
    trades: list[dict],
    starting_equity: float = 300.0,
    account_max_drawdown_pct: float = 20.0,
    regime_concentration_cap_pct: float = 60.0,
    stability_min_days: int = 30,
    sideways_trade_rate_multiple: float = 1.5,
    single_trade_profit_cap_pct: float = 20.0,
) -> dict:
    """Objective 10-gate graduation scorecard: paper -> $300 live.

    The goal is NOT profitability — it is proving a *repeatable edge that
    survives fees, slippage and different market regimes*. Returns each gate
    with target/actual/passed plus transparent supporting metrics.
    """
    from datetime import datetime, timezone

    sells = [t for t in trades if t.get("side") == "SELL" and t.get("status", "FILLED") == "FILLED"]
    sells = sorted(sells, key=lambda t: t.get("timestamp", ""))
    pnls = [float(t.get("pnl", 0.0) or 0.0) for t in sells]
    n = len(pnls)

    perf = compute_performance(trades)
    expectancy = perf["expectancy_usd"]
    profit_factor = perf["profit_factor"]
    gross_profit = perf["gross_profit_usd"]
    net_pnl = perf["net_pnl_usd"]

    max_dd_pct = _equity_drawdown_pct(pnls, starting_equity)

    # ---- regime net P&L (gate 5) ----
    regime_net: dict[str, float] = {}
    for t in sells:
        r = t.get("volatility_regime") or "UNKNOWN"
        regime_net[r] = regime_net.get(r, 0.0) + float(t.get("pnl", 0.0) or 0.0)
    positive_regimes = {r: v for r, v in regime_net.items() if v > 0 and r != "UNKNOWN"}
    regime_total_positive = sum(positive_regimes.values())
    top_regime_share = (
        round(max(positive_regimes.values()) / regime_total_positive * 100.0, 2)
        if regime_total_positive > 0 else 0.0
    )
    regime_ok = len(positive_regimes) >= 2 and top_regime_share <= regime_concentration_cap_pct

    # ---- sideways overtrading (gate 7) ----
    sideways = [t for t in sells if (t.get("volatility_regime") == "LOW_COMPRESSION")]
    sideways_pnls = [float(t.get("pnl", 0.0) or 0.0) for t in sideways]
    sideways_expectancy = round(_safe_mean(sideways_pnls), 4)
    # daily trade rates
    def _days_span(items: list[dict]) -> float:
        ts = [_parse_ts(t.get("timestamp", "")) for t in items]
        ts = [x for x in ts if x is not None]
        if len(ts) < 2:
            return 0.0
        return max((max(ts) - min(ts)).total_seconds() / 86400.0, 0.0)
    overall_days = _days_span(sells)
    overall_rate = (n / overall_days) if overall_days > 0 else 0.0
    sideways_days = _days_span(sideways)
    sideways_rate = (len(sideways) / sideways_days) if sideways_days > 0 else 0.0
    sideways_overtrading = (
        sideways_rate > sideways_trade_rate_multiple * overall_rate and overall_rate > 0
    )
    sideways_ok = (len(sideways) == 0) or (sideways_expectancy >= 0 and not sideways_overtrading)

    # ---- stability across weeks (gate 8) ----
    now = datetime.now(timezone.utc)
    observation_days = round(overall_days, 2)
    weekly_positive = 0
    weekly_windows = []
    for w in range(3):  # 3 most-recent 7-day windows
        start = now.timestamp() - (w + 1) * 7 * 86400
        end = now.timestamp() - w * 7 * 86400
        wnet = 0.0
        wcount = 0
        for t in sells:
            ts = _parse_ts(t.get("timestamp", ""))
            if ts is not None and start <= ts.timestamp() < end:
                wnet += float(t.get("pnl", 0.0) or 0.0)
                wcount += 1
        weekly_windows.append({"window": f"-{w*7}..-{(w+1)*7}d", "net_pnl": round(wnet, 4), "trades": wcount})
        if wnet > 0:
            weekly_positive += 1
    stability_ok = observation_days >= stability_min_days and weekly_positive >= 2

    # ---- account survival (gate 9) ----
    survival_ok = max_dd_pct < account_max_drawdown_pct

    # ---- risk consistency (gate 10) ----
    wins = [p for p in pnls if p > 0]
    largest_win = max(wins) if wins else 0.0
    largest_win_share = round(largest_win / gross_profit * 100.0, 2) if gross_profit > 0 else 0.0
    risk_consistency_ok = gross_profit > 0 and largest_win_share <= single_trade_profit_cap_pct

    # ---- friction accounting (gate 6) ----
    friction = perf["total_friction_usd"]
    friction_pct_of_gross = round(friction / gross_profit * 100.0, 2) if gross_profit > 0 else None
    friction_ok = n > 0  # every leg stores fee + slippage; pnl is net of fees

    # ---- exit-quality + chase-risk metrics ----
    sl_exits = [t for t in sells if t.get("exit_reason") == "SL_HIT"]
    trail_exits = [t for t in sells if t.get("exit_reason") == "TRAIL_HIT"]
    trail_pnls = [float(t.get("pnl", 0.0) or 0.0) for t in trail_exits]
    trail_positive = sum(1 for p in trail_pnls if p > 0)
    ext_vals = [float(t["entry_extension_pct"]) for t in sells if t.get("entry_extension_pct") is not None]

    criteria = [
        {"id": "min_trades", "label": "≥ 50 completed round-trips",
         "target": "≥ 50", "actual": f"{n}", "passed": n >= 50},
        {"id": "positive_expectancy", "label": "Positive expectancy",
         "target": "> $0", "actual": f"${expectancy:+.2f}/trade", "passed": expectancy > 0},
        {"id": "profit_factor", "label": "Profit factor > 1.3",
         "target": "> 1.3", "actual": f"{profit_factor:.2f}" if profit_factor is not None else "n/a",
         "passed": profit_factor is not None and profit_factor > 1.3},
        {"id": "max_drawdown", "label": "Max drawdown < 15%",
         "target": "< 15%", "actual": f"{max_dd_pct:.1f}%", "passed": max_dd_pct < 15.0},
        {"id": "regime_diversification", "label": "No single regime carries profits",
         "target": f"≥2 regimes +, top ≤ {regime_concentration_cap_pct:.0f}%",
         "actual": f"{len(positive_regimes)} reg +, top {top_regime_share:.0f}%", "passed": regime_ok},
        {"id": "friction_accounted", "label": "Fees + slippage fully accounted",
         "target": "tracked, net-of-fees",
         "actual": f"${friction:.2f}" + (f" ({friction_pct_of_gross:.0f}% of gross)" if friction_pct_of_gross is not None else ""),
         "passed": friction_ok},
        {"id": "no_sideways_overtrading", "label": "No overtrading in sideways markets",
         "target": f"exp ≥ 0 & rate ≤ {sideways_trade_rate_multiple}×",
         "actual": f"exp ${sideways_expectancy:+.2f}, {len(sideways)} chop trades", "passed": sideways_ok},
        {"id": "stability", "label": f"Stable across ≥ {stability_min_days} days",
         "target": f"≥ {stability_min_days}d & 2/3 weeks +",
         "actual": f"{observation_days:.0f}d, {weekly_positive}/3 weeks +", "passed": stability_ok},
        {"id": "account_survival", "label": "Account survival (no ruin-line breach)",
         "target": f"DD never ≥ {account_max_drawdown_pct:.0f}%",
         "actual": f"peak DD {max_dd_pct:.1f}%", "passed": survival_ok},
        {"id": "risk_consistency", "label": "No single outlier carries results",
         "target": f"top trade ≤ {single_trade_profit_cap_pct:.0f}% of profit",
         "actual": f"top trade {largest_win_share:.0f}% of profit", "passed": risk_consistency_ok},
    ]
    passed_count = sum(1 for c in criteria if c["passed"])
    total = len(criteria)

    return {
        "passed_count": passed_count,
        "total_gates": total,
        "all_passed": passed_count == total,
        "verdict": "READY" if passed_count == total else "NOT READY",
        "headline": f"{passed_count}/{total} PASSED — {'READY' if passed_count == total else 'NOT READY'}",
        "criteria": criteria,
        "metrics": {
            "closed_trades": n,
            "expectancy_usd": expectancy,
            "profit_factor": profit_factor,
            "net_pnl_usd": net_pnl,
            "max_drawdown_pct": max_dd_pct,
            "stop_loss_frequency_pct": round(len(sl_exits) / n * 100.0, 2) if n else 0.0,
            "trail_exit_count": len(trail_exits),
            "trail_exit_avg_pnl_usd": round(_safe_mean(trail_pnls), 4),
            "trail_exit_win_pct": round(trail_positive / len(trail_exits) * 100.0, 2) if trail_exits else 0.0,
            "total_fees_usd": perf["total_fees_usd"],
            "total_slippage_usd": perf["total_slippage_usd"],
            "total_friction_usd": friction,
            "friction_pct_of_gross": friction_pct_of_gross,
            "avg_entry_extension_pct": round(_safe_mean(ext_vals), 3) if ext_vals else None,
            "max_entry_extension_pct": round(max(ext_vals), 3) if ext_vals else None,
            "entry_extension_sample": len(ext_vals),
            "regime_net_pnl": {r: round(v, 4) for r, v in regime_net.items()},
            "weekly_windows": weekly_windows,
            "observation_days": observation_days,
        },
    }


def regime_insight(trades: list[dict]) -> dict:
    """"Best Regime to Trade" research insight.

    Determines which volatility regime carries the highest statistical
    expectancy across all closed trades. Returns ``ready=False`` until at least
    ``MIN_TRADES_FOR_INSIGHT`` round-trips exist so the UI can show a graceful
    "accumulating data" placeholder instead of noisy/div-by-zero output.
    """
    sells = [t for t in trades if t.get("side") == "SELL" and t.get("status", "FILLED") == "FILLED"]
    total = len(sells)

    regime_pnls: dict[str, list[float]] = {}
    for t in sells:
        regime = t.get("volatility_regime") or "UNKNOWN"
        regime_pnls.setdefault(regime, []).append(float(t.get("pnl", 0.0) or 0.0))
    regimes = {r: _regime_stats(p) for r, p in regime_pnls.items()}

    ready = total >= MIN_TRADES_FOR_INSIGHT
    best_regime: str | None = None
    best_expectancy: float | None = None
    insight_text = (
        f"Analyzing Market Regimes... (Accumulating Trade Data Base — "
        f"{total}/{MIN_TRADES_FOR_INSIGHT} round-trips)"
    )

    if ready and regimes:
        # ignore UNKNOWN-regime trades when ranking (untagged legacy fills)
        ranked = {r: s for r, s in regimes.items() if r != "UNKNOWN"} or regimes
        best_regime = max(ranked, key=lambda r: ranked[r]["expectancy_usd"])
        best_expectancy = ranked[best_regime]["expectancy_usd"]
        if best_expectancy > 0:
            s = ranked[best_regime]
            insight_text = (
                f"Your statistical edge is concentrated in {best_regime} regimes: "
                f"expectancy ${best_expectancy:+.2f}/trade over {s['trades']} trades "
                f"(win rate {s['win_rate_pct']}%). Prioritise entries when ATR sits in this band."
            )
        else:
            insight_text = (
                "No volatility regime shows a positive expectancy yet — tighten entry "
                "filters or reduce size before scaling exposure."
            )

    return {
        "ready": ready,
        "total_completed_trades": total,
        "min_trades_required": MIN_TRADES_FOR_INSIGHT,
        "best_regime": best_regime,
        "best_expectancy_usd": best_expectancy,
        "insight_text": insight_text,
        "regimes": regimes,
    }
