"""
lab/lab_report.py — standalone Research Lab PDF report for a completed lab_run.

Reuses the shared reportlab styling from pdf_report so lab reports match the app's
research PDFs. Renders config + git-hash provenance, then a kind-specific section
(backtest metrics / grid ranking / sensitivity curve / walk-forward folds), all with
the Phase-F quantitative telemetry (MFE/MAE, exit-module A-F, regime breakdown).
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from pdf_report import _fmt, _kv_table, _styles

# Friendly names for the raw exit-module codes emitted by the replay engine / Universal Exit Engine.
_EXIT_MODULE_LABELS = {
    "ATR": "ATR Trailing Stop", "FIXED_TP": "Fixed Target (TP)", "FIXED_SL": "Fixed Stop (SL)",
    "A": "Structural / Hard Stop", "B": "Momentum Exhaustion", "C": "ATR Trail (Universal)",
    "D": "EMA / Trend Break", "E": "Time Stop", "F": "Profit Protection", "S": "Breakeven / Structure",
    "KILL": "Kill-Switch", "EOD": "End of Window", "—": "Unclassified",
}


def _mod_label(code) -> str:
    return _EXIT_MODULE_LABELS.get(code, str(code))


def _pf(v) -> str:
    if v is None:
        return "—"
    return "∞" if v >= 999 else f"{v:.2f}"


def _date(ms) -> str:
    if not ms:
        return "—"
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _exit_label(run: dict) -> str:
    res = run.get("result") or {}
    if res.get("exit_method_label"):
        return res["exit_method_label"]
    if run.get("exit_method") == "fixed":
        return f'Fixed $ Target (TP ${run.get("target_profit", 5):g} / SL ${run.get("target_loss", 4):g})'
    return "Native Strategy Exit (Universal Engine)"


def _exit_params_rows(run: dict):
    """Exit-parameter provenance rows for the config block (position size, targets/%, ATR params)."""
    res = run.get("result") or {}
    ps = res.get("position_size_usd") or 75
    rows = [["Position size", f"${ps:g}"]]
    em = run.get("exit_method")
    if em == "fixed":
        tp, tl = run.get("target_profit", 5), run.get("target_loss", 4)
        rows.append(["Profit target", f"${tp:g}  (≈{tp / ps * 100:.2f}% of trade value)"])
        rows.append(["Stop loss", f"${tl:g}  (≈{tl / ps * 100:.2f}% of trade value)"])
    elif em == "atr":
        a = res.get("atr_params") or run.get("atr_params") or {}
        if a:
            rows.append(["ATR parameters",
                         f"×{a.get('multiplier')} stop · {int(a.get('period', 14))}p · "
                         f"arm {a.get('trail_activation_pct')}% · trail ×{a.get('trail_distance')}"])
    return rows


def _config_block(s, run: dict):
    rows = [
        ["Run ID", run.get("id", "—")],
        ["Kind", run.get("kind", "—")],
        ["Symbols", ", ".join(run.get("symbols") or [])],
        ["Period", f'{run.get("period","—")}  ({_date(run.get("start_ms"))} → {_date(run.get("end_ms"))})'],
        ["Exit method", _exit_label(run)],
        ["Exit settings", "Live Exit Engine (deployed config)"
            if ((run.get("result") or {}).get("exit_source") or run.get("exit_source")) == "live"
            else "Manual override (selected for this run)"],
        *_exit_params_rows(run),
        ["Strategies", ", ".join(run.get("strategies") or ["hunter", "squeeze", "continuation"])],
        ["Metric", run.get("metric", "—")],
        ["Git commit", run.get("git_hash", "—")],
        ["Created", (run.get("created_at") or "—")[:19]],
        ["Baseline capital", "$1,200"],
    ]
    if run.get("label"):
        rows.insert(1, ["Label", run["label"]])
    return [Paragraph("RUN CONFIGURATION &amp; PROVENANCE", s["h2"]),
            Paragraph("Every run stores its exact inputs + the git commit that produced it — "
                      "fully reproducible.", s["subtitle"]), Spacer(1, 6),
            _kv_table(s, ["Field", "Value"], rows, [1.8 * inch, 4.4 * inch]), Spacer(1, 12)]


def _summary_metrics(s, title, summ: dict):
    rows = [
        ["Total return", _fmt(summ.get("total_return_pct"), "%")],
        ["Trades", str(summ.get("trades", 0))],
        ["Win rate", _fmt(summ.get("win_rate_pct"), "%")],
        ["Max drawdown", _fmt(summ.get("max_drawdown_pct"), "%")],
        ["Sharpe (per-trade)", _fmt(summ.get("sharpe"))],
        ["Sortino (per-trade)", _fmt(summ.get("sortino"))],
        ["Profit factor", _fmt(summ.get("profit_factor"))],
        ["Net P&L", (f"${summ['net_pnl']:g}" if summ.get("net_pnl") is not None else "—")],
        ["Avg MFE", _fmt(summ.get("avg_mfe_pct"), "%")],
        ["Avg MAE", _fmt(summ.get("avg_mae_pct"), "%")],
        ["Avg profit left on table", (f"${summ['avg_profit_left_usd']:g}" if summ.get("avg_profit_left_usd") is not None else "—")],
        ["Total profit left on table", (f"${summ['total_profit_left_usd']:g}" if summ.get("total_profit_left_usd") is not None else "—")],
        ["Avg trade quality", _fmt(summ.get("avg_trade_quality"))],
    ]
    flow = [Paragraph(title, s["h3"]),
            _kv_table(s, ["Metric", "Value"], rows, [2.6 * inch, 2.0 * inch]), Spacer(1, 6)]
    if summ.get("recommendation"):
        flow += [Paragraph(f"<b>Recommendation:</b> {summ['recommendation']}", s["italic"]), Spacer(1, 8)]

    # ---- Exit Efficiency — MFE / MAE capture ----
    cap = summ.get("capture_stats") or {}
    if cap:
        cr = cap.get("capture_rate_pct")
        cap_rows = [
            ["MFE capture rate", (f"{cr:g}%" if cr is not None else "—")],
            ["Total favourable move (MFE)", (f"${cap['total_mfe_usd']:g}" if cap.get("total_mfe_usd") is not None else "—")],
            ["Captured by exits", (f"${cap['total_captured_usd']:g}" if cap.get("total_captured_usd") is not None else "—")],
            ["Profit left on table", (f"${cap['total_profit_left_usd']:g}" if cap.get("total_profit_left_usd") is not None else "—")],
            ["Avg MFE / trade", _fmt(cap.get("avg_mfe_pct"), "%")],
            ["Avg MAE / trade", _fmt(cap.get("avg_mae_pct"), "%")],
            ["Avg profit left / trade", (f"${cap['avg_profit_left_usd']:g}" if cap.get("avg_profit_left_usd") is not None else "—")],
        ]
        flow += [Paragraph("Exit Efficiency — MFE / MAE Capture", s["h3"]),
                 Paragraph("How much of the maximum favourable move (MFE) the exits actually banked vs. "
                           "left on the table. A low capture rate with high 'profit left' points at the "
                           "<b>exit logic</b> as the bottleneck — not the entries.", s["subtitle"]),
                 _kv_table(s, ["Exit efficiency", "Value"], cap_rows, [2.6 * inch, 2.0 * inch])]
        if cr is not None:
            verdict = ("exits are banking most of the available move." if cr >= 60
                       else "exits are giving back a lot of open profit — try a wider trail or a structural exit."
                       if cr < 40 else "exit capture is moderate; test tighter/looser trails to compare.")
            flow.append(Paragraph(f"<b>Read:</b> {cr:g}% capture — {verdict}", s["italic"]))
        flow.append(Spacer(1, 8))

    # ---- Exit Module Performance ----
    emb = summ.get("exit_module_breakdown") or {}
    if emb:
        er = [[_mod_label(k), v["n"], f'{v["win_pct"]}%', _pf(v.get("profit_factor")),
               _fmt(v.get("avg_return_pct"), "%"), round(v["net_pnl"], 2)]
              for k, v in sorted(emb.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)]
        flow += [Paragraph("Exit Module Performance", s["h3"]),
                 Paragraph("Which exit actually closed each trade, and how each performed. Use this to pick "
                           "the exit method that is genuinely working for this strategy.", s["subtitle"]),
                 _kv_table(s, ["Exit module", "N", "Win%", "PF", "Avg Ret", "Net P&L"], er,
                           [1.9 * inch, 0.55 * inch, 0.75 * inch, 0.6 * inch, 0.8 * inch, 0.95 * inch]),
                 Spacer(1, 8)]

    # ---- Regime-wise Breakdown ----
    rb = summ.get("regime_breakdown") or {}
    if rb:
        rr = [[k, v["n"], f'{v["win_pct"]}%', _pf(v.get("profit_factor")),
               _fmt(v.get("avg_return_pct"), "%"), round(v["net_pnl"], 2)]
              for k, v in sorted(rb.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)]
        flow += [Paragraph("Regime-wise Breakdown", s["h3"]),
                 Paragraph("Performance split by the market regime at entry (TREND_UP, REVERSAL, "
                           "COMPRESSION, NEUTRAL). Shows exactly which conditions the strategy makes "
                           "or loses money in.", s["subtitle"]),
                 _kv_table(s, ["Regime", "N", "Win%", "PF", "Avg Ret", "Net P&L"], rr,
                           [1.9 * inch, 0.55 * inch, 0.75 * inch, 0.6 * inch, 0.8 * inch, 0.95 * inch]),
                 Spacer(1, 10)]
    return flow


def _trade_log_block(s, summ: dict):
    """Full per-trade log for the report: timestamps, entry/exit fills, position size, P&L."""
    trades = summ.get("trade_log") or []
    if not trades:
        return []

    def _t(iso):
        return (iso or "—").replace("T", " ")[:16]

    def _p(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "—"
        return f"{v:,.2f}" if v >= 1000 else (f"{v:.4f}" if v >= 1 else f"{v:.6f}")

    rows = []
    for i, t in enumerate(trades, 1):
        rows.append([
            str(i), _t(t.get("entry_ts")), _t(t.get("exit_ts")),
            _p(t.get("entry_price")), _p(t.get("exit_price")),
            f'{float(t.get("qty", 0)):.4g}', f'{float(t.get("pnl", 0)):+.2f}',
            _mod_label(t.get("exit_module", "—")),
        ])
    return [Paragraph("Full trade log", s["h3"]),
            Paragraph("Timestamps (UTC), entry/exit fills, position size and net P&amp;L per trade.", s["subtitle"]),
            _kv_table(s, ["#", "Entry (UTC)", "Exit (UTC)", "Entry", "Exit", "Size", "P&L $", "Exit"], rows,
                      [0.35 * inch, 1.15 * inch, 1.15 * inch, 0.85 * inch, 0.85 * inch,
                       0.7 * inch, 0.7 * inch, 0.75 * inch]),
            Spacer(1, 10)]


def _multi_tf_block(s, multi_tf: dict):
    """Per-symbol execution-timeframe comparison (15m / 30m / 1h) — same window & params
    replayed on each candle size so the operator can see which timeframe the edge favours."""
    if not multi_tf:
        return []
    order = ["15m", "30m", "1h"]
    flow = [PageBreak(),
            Paragraph("MULTI-TIMEFRAME COMPARISON", s["h2"]),
            Paragraph("Identical window, settings and exit rules replayed on 15m, 30m and the 1h "
                      "live-execution baseline. Compare trade frequency vs. return/drawdown to judge "
                      "which candle size the strategy's edge actually favours.", s["subtitle"]),
            Spacer(1, 8)]
    for sym, entry in multi_tf.items():
        by_tf = entry.get("by_tf") or {}
        verdict = entry.get("verdict") or {}
        rows = []
        for tf in order:
            m = by_tf.get(tf) or {}
            if "error" in m:
                rows.append([tf, "—", m["error"], "—", "—", "—", "—"])
                continue
            rows.append([
                tf, str(m.get("trades", 0)),
                _fmt(m.get("total_return_pct"), "%"), _fmt(m.get("win_rate_pct"), "%"),
                _fmt(m.get("max_drawdown_pct"), "%"), _fmt(m.get("avg_mfe_pct"), "%"),
                _fmt(m.get("avg_mae_pct"), "%"),
            ])
        flow += [Paragraph(sym, s["h3"]),
                 _kv_table(s, ["TF", "Trades", "Return", "Win%", "MaxDD", "Avg MFE", "Avg MAE"], rows,
                           [0.8 * inch, 0.8 * inch, 0.9 * inch, 0.8 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch])]
        if verdict.get("reason"):
            best = verdict.get("best_tf") or "—"
            flow.append(Paragraph(f"Best timeframe: <b>{best}</b> — {verdict['reason']}", s["italic"]))
        flow.append(Spacer(1, 10))
    return flow


def _exit_comparison_block(s, res: dict):
    """Exit-engine A/B/C comparison — each config replayed on the IDENTICAL entry set
    (two-pass engine: entries scanned once, exit-agnostic; only exits vary). One table per
    symbol × timeframe, best engine ranked by return-over-drawdown."""
    cmp = res.get("exit_comparison") or {}
    if not cmp:
        return []
    flow = [PageBreak(),
            Paragraph("EXIT ENGINE COMPARISON", s["h2"]),
            Paragraph("Every configuration below is replayed on the EXACT same entry signals "
                      "(the engine scans entries once, exit-agnostic, then simulates each exit "
                      "engine independently). This isolates the exit as the sole variable, so the "
                      "tables are a true A/B/C test. Best engine is ranked by return-over-drawdown. "
                      "Percentage columns are marked with %; expectancy is average net P&amp;L per trade.",
                      s["subtitle"]),
            Spacer(1, 8)]
    for sym, by_tf in cmp.items():
        for tf, block in (by_tf or {}).items():
            if not block or block.get("error"):
                flow.append(Paragraph(f"{sym} · {tf}: {(block or {}).get('error', 'no data')}", s["italic"]))
                continue
            rows_data = block.get("rows") or {}
            winner = block.get("winner_key")
            order = [c["key"] for c in (block.get("configs") or [])] or list(rows_data.keys())
            table_rows = []
            for key in order:
                m = rows_data.get(key) or {}
                label = m.get("label", key)
                if winner and key == winner:
                    label = f"{label}  ★ best"
                if m.get("error"):
                    table_rows.append([label, m["error"], "—", "—", "—", "—"])
                    continue
                pf = m.get("profit_factor")
                exp = m.get("expectancy_usd")
                table_rows.append([
                    label,
                    ("—" if pf is None else f"{pf:.2f}"),
                    f'{m.get("win_rate_pct", 0):.1f}%',
                    ("—" if exp is None else f"${exp:+.2f}"),
                    f'{m.get("total_return_pct", 0):+.2f}%',
                    f'{m.get("max_drawdown_pct", 0):.2f}%',
                ])
            flow += [Paragraph(f"{sym} · {tf}  —  identical entries: {block.get('entries', '—')}", s["h3"]),
                     _kv_table(s, ["Exit config", "Profit factor", "Win rate", "Expectancy",
                                   "Net return", "Max DD"], table_rows,
                               [1.9 * inch, 1.0 * inch, 0.85 * inch, 0.95 * inch, 0.9 * inch, 0.8 * inch]),
                     Spacer(1, 6)]
            if winner:
                wm = rows_data.get(winner) or {}
                flow.append(Paragraph(
                    f"Best engine (return/drawdown): <b>{wm.get('label', winner)}</b> — "
                    f"{wm.get('total_return_pct', 0):+.2f}% net return at {wm.get('win_rate_pct', 0):.1f}% "
                    f"win rate, profit factor {wm.get('profit_factor', '—')}, "
                    f"{wm.get('max_drawdown_pct', 0):.2f}% max drawdown over {wm.get('trades', 0)} trades.",
                    s["italic"]))
            flow.append(Spacer(1, 10))
    return flow


def _health_block(s, res: dict):
    """Full Strategy Health sweep report — one section per strategy with its recommendation,
    headline metrics, best timeframe/exit and regime performance."""
    cards = res.get("strategies") or []
    flow = [Paragraph("STRATEGY HEALTH — FULL ANALYSIS", s["h2"]),
            Paragraph(f"Pre-computed sweep across {', '.join(res.get('symbols') or [])} on 1H · 30m · 15m "
                      f"over the {res.get('period', '3m')} window. Each strategy is replayed in isolation; "
                      f"generated {(res.get('generated_at') or '')[:19]} UTC.", s["subtitle"]),
            Spacer(1, 8)]
    # ranked: recommended first
    order = {"Good for Paper Trading": 0, "Needs Improvement": 1, "Not Recommended Currently": 2}
    cards = sorted(cards, key=lambda c: order.get((c.get("recommendation") or {}).get("badge"), 3))
    for c in cards:
        rec = c.get("recommendation") or {}
        flow.append(Paragraph(f'{c.get("name", c.get("strategy"))} — <b>{rec.get("badge", "—")}</b>', s["h3"]))
        if c.get("error"):
            flow += [Paragraph(f"Error: {c['error']}", s["italic"]), Spacer(1, 8)]
            continue
        h = c.get("headline") or {}
        rows = [
            ["Recommendation", rec.get("badge", "—")],
            ["Why", rec.get("reason", "—")],
            ["Best timeframe", (c.get("best_timeframe") or "—")],
            ["Best exit", (c.get("best_exit") or "—")],
            ["Best regime", (c.get("best_regime") or "—")],
            ["Weakest regime", (c.get("weak_regime") or "—")],
            ["Total return", _fmt(h.get("total_return_pct"), "%")],
            ["Win rate", _fmt(h.get("win_rate_pct"), "%")],
            ["Profit factor", _pf(h.get("profit_factor"))],
            ["Max drawdown", _fmt(h.get("max_drawdown_pct"), "%")],
            ["Trades", str(h.get("trades", 0))],
            ["MFE capture", (f"{c['capture_rate_pct']:g}%" if c.get("capture_rate_pct") is not None else "—")],
            ["Profit left on table", (f"${c['profit_left_usd']:g}" if c.get("profit_left_usd") is not None else "—")],
        ]
        flow.append(_kv_table(s, ["Field", "Value"], rows, [1.9 * inch, 4.3 * inch]))
        rb = c.get("regime_breakdown") or {}
        if rb:
            rr = [[k, v["n"], f'{v["win_pct"]}%', _fmt(v.get("avg_return_pct"), "%"), round(v["net_pnl"], 2)]
                  for k, v in sorted(rb.items(), key=lambda kv: kv[1]["net_pnl"], reverse=True)]
            flow += [Spacer(1, 4), _kv_table(s, ["Regime", "N", "Win%", "Avg Ret", "Net P&L"], rr,
                                             [1.6 * inch, 0.7 * inch, 0.9 * inch, 1.0 * inch, 1.1 * inch])]
        flow.append(Spacer(1, 12))
    return flow


def _result_block(s, run: dict):
    kind = run.get("kind")
    res = run.get("result") or {}
    if run.get("status") != "DONE" or not res:
        return [Paragraph("No results — run status: %s" % run.get("status"), s["italic"])]

    if kind == "health_sweep":
        return _health_block(s, res)

    if kind == "backtest":
        flow = [Paragraph("BACKTEST RESULTS", s["h2"]),
                Paragraph(f"<b>Exit method used:</b> {_exit_label(run)}", s["italic"]), Spacer(1, 4)]
        for sym, summ in (res.get("per_symbol") or {}).items():
            if "error" in summ:
                flow.append(Paragraph(f"{sym}: {summ['error']}", s["italic"]))
            else:
                flow += _summary_metrics(s, sym, summ)
                flow += _trade_log_block(s, summ)
        flow += _multi_tf_block(s, res.get("multi_timeframe") or {})
        flow += _exit_comparison_block(s, res)
        return flow

    if kind == "grid_search":
        ranked = res.get("ranked", [])[:15]
        rows = [[str(r["params"]), _fmt(r["metric"]), r["trades"],
                 _fmt(r["total_return_pct"], "%"), _fmt(r["win_rate_pct"], "%"),
                 _fmt(r["max_drawdown_pct"], "%")] for r in ranked]
        return [Paragraph("PARAMETER GRID SEARCH", s["h2"]),
                Paragraph(f"{res.get('combos_tested')} combos ranked by {res.get('metric')}. "
                          "Prefer a robust plateau of good neighbours over a single peak.", s["subtitle"]),
                Spacer(1, 6),
                _kv_table(s, ["Params", "Metric", "N", "Ret", "Win%", "MaxDD"], rows,
                          [2.4 * inch, 0.9 * inch, 0.5 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch])]

    if kind == "sensitivity":
        rows = [[_fmt(c["value"]), _fmt(c["metric"]), c["trades"], _fmt(c["total_return_pct"], "%")]
                for c in res.get("curve", [])]
        return [Paragraph("PARAMETER SENSITIVITY", s["h2"]),
                Paragraph(f"Target: {res.get('target')} · metric: {res.get('metric')} · "
                          f"CV: {res.get('coeff_variation')}", s["subtitle"]), Spacer(1, 6),
                _kv_table(s, ["Value", "Metric", "N", "Return"], rows,
                          [1.6 * inch, 1.4 * inch, 1.0 * inch, 1.4 * inch]), Spacer(1, 8),
                Paragraph(f"VERDICT: {res.get('verdict')}", s["h3"])]

    if kind == "walk_forward":
        rows = []
        for f in res.get("fold_reports", []):
            if "is_window" in f:
                rows.append([f["fold"], str(f.get("best_params")), _fmt(f.get("is_metric")),
                             _fmt(f.get("oos_metric")), f.get("oos_trades"),
                             _fmt(f.get("oos_return_pct"), "%")])
        return [Paragraph("WALK-FORWARD ANALYSIS", s["h2"]),
                Paragraph("Rolling In-Sample optimize → Out-of-Sample test. WFA efficiency (OOS/IS) "
                          "near 1.0 = the edge survives unseen data; low = overfit.", s["subtitle"]),
                Spacer(1, 6),
                _kv_table(s, ["Fold", "Best params (IS)", "IS", "OOS", "OOS N", "OOS Ret"], rows,
                          [0.6 * inch, 2.2 * inch, 0.8 * inch, 0.8 * inch, 0.7 * inch, 0.9 * inch]),
                Spacer(1, 8),
                _kv_table(s, ["Aggregate", "Value"], [
                    ["Avg IS metric", _fmt(res.get("avg_is_metric"))],
                    ["Avg OOS metric", _fmt(res.get("avg_oos_metric"))],
                    ["WFA efficiency (OOS/IS)", _fmt(res.get("wfa_efficiency"))],
                    ["OOS positive folds", res.get("oos_positive_folds", "—")],
                ], [2.6 * inch, 2.0 * inch]), Spacer(1, 8),
                Paragraph(f"VERDICT: {res.get('verdict')}", s["h3"])]

    return [Paragraph("Unknown run kind.", s["italic"])]


def build_lab_report(run: dict) -> bytes:
    s = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=48, bottomMargin=40,
                            leftMargin=42, rightMargin=42, title="Ananta Research Lab Report")
    flow = [
        Paragraph("ANANTA RESEARCH LAB", s["title"]),
        Paragraph("Strategy Validation Report · offline historical simulation · parity with live engine",
                  s["subtitle"]),
        Spacer(1, 14),
    ]
    flow += _config_block(s, run)
    flow.append(PageBreak())
    flow += _result_block(s, run)
    doc.build(flow)
    return buf.getvalue()
