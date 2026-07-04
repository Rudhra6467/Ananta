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


def _date(ms) -> str:
    if not ms:
        return "—"
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _config_block(s, run: dict):
    rows = [
        ["Run ID", run.get("id", "—")],
        ["Kind", run.get("kind", "—")],
        ["Symbols", ", ".join(run.get("symbols") or [])],
        ["Period", f'{run.get("period","—")}  ({_date(run.get("start_ms"))} → {_date(run.get("end_ms"))})'],
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
        ["Avg MFE", _fmt(summ.get("avg_mfe_pct"), "%")],
        ["Avg MAE", _fmt(summ.get("avg_mae_pct"), "%")],
        ["Avg trade quality", _fmt(summ.get("avg_trade_quality"))],
    ]
    flow = [Paragraph(title, s["h3"]),
            _kv_table(s, ["Metric", "Value"], rows, [2.6 * inch, 2.0 * inch]), Spacer(1, 8)]
    emb = summ.get("exit_module_breakdown") or {}
    if emb:
        er = [[k, v["n"], f'{v["win_pct"]}%', round(v["net_pnl"], 2)] for k, v in sorted(emb.items())]
        flow += [Paragraph("Exit modules (A-F)", s["h3"]),
                 _kv_table(s, ["Module", "N", "Win%", "Net P&L"], er,
                           [1.6 * inch, 0.9 * inch, 1.0 * inch, 1.2 * inch]), Spacer(1, 8)]
    rb = summ.get("regime_breakdown") or {}
    if rb:
        rr = [[k, v["n"], f'{v["win_pct"]}%', round(v["net_pnl"], 2)] for k, v in sorted(rb.items())]
        flow += [Paragraph("Regime breakdown", s["h3"]),
                 _kv_table(s, ["Regime", "N", "Win%", "Net P&L"], rr,
                           [1.8 * inch, 0.9 * inch, 1.0 * inch, 1.2 * inch]), Spacer(1, 10)]
    return flow


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


def _result_block(s, run: dict):
    kind = run.get("kind")
    res = run.get("result") or {}
    if run.get("status") != "DONE" or not res:
        return [Paragraph("No results — run status: %s" % run.get("status"), s["italic"])]

    if kind == "backtest":
        flow = [Paragraph("BACKTEST RESULTS", s["h2"]), Spacer(1, 4)]
        for sym, summ in (res.get("per_symbol") or {}).items():
            if "error" in summ:
                flow.append(Paragraph(f"{sym}: {summ['error']}", s["italic"]))
            else:
                flow += _summary_metrics(s, sym, summ)
        flow += _multi_tf_block(s, res.get("multi_timeframe") or {})
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
