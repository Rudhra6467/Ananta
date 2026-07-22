"""
PDF report generation for the CryptoAtlas competition demo.
Produces a clean, judge-ready PDF containing:
  - Portfolio summary
  - Current risk / kill-switch status
  - AI reasoning timeline (chronological, oldest first)
  - Trade log
"""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from io import BytesIO
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ----- palette (mirrors the dashboard) -----
BG = colors.HexColor("#FFFFFF")
TEXT = colors.HexColor("#0B0E12")
MUTED = colors.HexColor("#5A6470")
SUBTLE = colors.HexColor("#9099A3")
CYAN = colors.HexColor("#007D88")
POS = colors.HexColor("#0B8A3E")
NEG = colors.HexColor("#C02018")
WARN = colors.HexColor("#A37200")
RULE = colors.HexColor("#D5DAE0")
PANEL = colors.HexColor("#F4F6F8")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=TEXT,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=MUTED,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=TEXT,
            spaceBefore=14,
            spaceAfter=6,
            textTransform="uppercase",
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=TEXT,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=SUBTLE,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=TEXT,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=8,
            leading=10.5,
            textColor=TEXT,
        ),
        "mono_small": ParagraphStyle(
            "mono_small",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
        "italic": ParagraphStyle(
            "italic",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
    }


def _bias_color(bias: str):
    return {"BULLISH": POS, "BEARISH": NEG, "NEUTRAL": WARN}.get((bias or "").upper(), MUTED)


def _decision_color(decision: str):
    return {"BUY": POS, "SELL": NEG, "HOLD": MUTED, "BLOCKED": NEG}.get((decision or "").upper(), MUTED)


def _header_footer(canvas, doc):
    canvas.saveState()
    width, height = LETTER
    # header rule
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.6 * inch, height - 0.55 * inch, width - 0.6 * inch, height - 0.55 * inch)
    # brand
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(TEXT)
    canvas.drawString(0.6 * inch, height - 0.45 * inch, "ANANTA.AI")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(
        width - 0.6 * inch,
        height - 0.45 * inch,
        f"VALIDATION REPORT · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
    )
    # footer
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SUBTLE)
    canvas.drawString(
        0.6 * inch,
        0.4 * inch,
        "Algorithmic swing-trading · technical-first Hunter · PAPER validation · capital preservation first",
    )
    canvas.drawRightString(width - 0.6 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _portfolio_block(s, portfolio: dict, risk: dict) -> Iterable:
    pnl = portfolio.get("total_pnl", 0.0) or 0.0
    pnl_pct = portfolio.get("total_pnl_pct", 0.0) or 0.0
    daily_pct = portfolio.get("daily_pnl_pct", 0.0) or 0.0
    pnl_color = POS if pnl > 0 else NEG if pnl < 0 else MUTED

    head = [
        [
            Paragraph("SIMULATED PORTFOLIO", s["label"]),
            Paragraph("RISK STATUS", s["label"]),
        ],
        [
            Paragraph(
                f"<font size=20><b>${portfolio.get('equity', 0):.2f}</b></font>"
                f"<font color='{pnl_color.hexval()}'> &nbsp; {'+' if pnl > 0 else ''}${pnl:.2f} ({'+' if pnl_pct > 0 else ''}{pnl_pct:.2f}%)</font>",
                s["body"],
            ),
            Paragraph(
                f"<b>{'SAFE' if risk['status']['overall_safe'] else 'TERMINATED'}</b>"
                f"<font color='{MUTED.hexval()}' size=8> &nbsp; {risk.get('trading_mode', 'PAPER')} MODE</font>",
                s["body"],
            ),
        ],
    ]
    head_tbl = Table(head, colWidths=[3.6 * inch, 3.6 * inch])
    head_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
                ("LINEBELOW", (0, 1), (-1, 1), 0.5, RULE),
            ]
        )
    )

    # metric row
    metrics = [
        ("CASH", f"${portfolio.get('cash', 0):.2f}"),
        ("POSITIONS", f"${portfolio.get('positions_value', 0):.2f}"),
        ("DAILY P&L", f"{'+' if daily_pct > 0 else ''}{daily_pct:.2f}%"),
        ("REALIZED", f"${portfolio.get('realized_pnl', 0):.2f}"),
        ("STARTED", f"${portfolio.get('starting_balance', 100):.2f}"),
    ]
    metric_rows = [[Paragraph(k, s["label"]) for k, _ in metrics],
                   [Paragraph(v, s["body"]) for _, v in metrics]]
    metric_tbl = Table(metric_rows, colWidths=[1.44 * inch] * 5)
    metric_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    # kill-switch row
    ks = risk["status"]
    th = risk["thresholds"]
    sw_rows = [
        ["SPREAD", f"{ks['details'].get('spread_pct', 0):.3f}% / ≤{th['max_spread_pct']}%", "TRIPPED" if ks["spread_breach"] else "OK"],
        ["DAILY LOSS", f"{ks['details'].get('daily_change_pct', 0):.2f}% / ≥-{th['max_daily_loss_pct']}%", "TRIPPED" if ks["daily_loss_breach"] else "OK"],
        ["AI CONFIDENCE", f"{ks['details'].get('macro_confidence', 0):.2f} / ≥{th['min_confidence']}", "BLOCK" if ks["confidence_breach"] else "OK"],
        ["MANUAL KILL", "ENGAGED" if ks["manual_kill"] else "RELEASED", "TRIPPED" if ks["manual_kill"] else "OK"],
    ]
    sw_table_data = [[Paragraph("KILL-SWITCH", s["label"]), Paragraph("VALUE / THRESHOLD", s["label"]), Paragraph("STATE", s["label"])]]
    for row in sw_rows:
        state_color = NEG if row[2] in ("TRIPPED", "BLOCK") else POS
        sw_table_data.append([
            Paragraph(row[0], s["body"]),
            Paragraph(row[1], s["mono"]),
            Paragraph(f"<font color='{state_color.hexval()}'><b>{row[2]}</b></font>", s["body"]),
        ])
    sw_tbl = Table(sw_table_data, colWidths=[1.6 * inch, 4.0 * inch, 1.6 * inch])
    sw_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("BACKGROUND", (0, 0), (-1, 0), PANEL),
            ]
        )
    )
    return [head_tbl, Spacer(1, 8), metric_tbl, Spacer(1, 12), sw_tbl]


def _reasoning_block(s, reasoning_items: list[dict]) -> Iterable:
    flow = [Paragraph("AI REASONING LOG · EXPLAINABLE AI · GEMINI 3 PRO", s["h2"])]
    if not reasoning_items:
        flow.append(Paragraph("No evaluation cycles recorded yet.", s["italic"]))
        return flow

    for _idx, r in enumerate(reasoning_items):
        bias_c = _bias_color(r.get("bias", ""))
        dec_c = _decision_color(r.get("decision", ""))
        ts = r.get("timestamp", "")
        try:
            ts_fmt = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            ts_fmt = ts

        # header row: time | symbol | BIAS | confidence | DECISION
        hdr = [[
            Paragraph(f"<font color='{MUTED.hexval()}'>{ts_fmt}</font>", s["mono"]),
            Paragraph(f"<b>{r.get('symbol', '')}</b>", s["body"]),
            Paragraph(f"<font color='{bias_c.hexval()}'><b>{r.get('bias', '')}</b></font>", s["body"]),
            Paragraph(f"<font color='{CYAN.hexval()}'><b>{float(r.get('confidence', 0)):.2f}</b></font>", s["body"]),
            Paragraph(f"<font color='{dec_c.hexval()}'><b>{r.get('decision', '')}</b></font>", s["body"]),
        ]]
        hdr_tbl = Table(hdr, colWidths=[1.7 * inch, 0.75 * inch, 0.95 * inch, 0.6 * inch, 0.95 * inch])
        hdr_tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, 0), PANEL),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ]
            )
        )

        # detail block
        ev = r.get("evidence", {}) or {}
        details = [
            [Paragraph("LLM REASONING", s["label"])],
            [Paragraph(r.get("reason", "") or "—", s["body"])],
            [Paragraph("FUSION SUMMARY", s["label"])],
            [Paragraph(ev.get("fusion_summary", "—") or "—", s["mono"])],
        ]
        if r.get("blocked_reasons"):
            details.append([Paragraph("BLOCKED REASONS", s["label"])])
            blocked_html = "<br/>".join(f"<font color='{NEG.hexval()}'>· {b}</font>" for b in r["blocked_reasons"])
            details.append([Paragraph(blocked_html, s["mono"])])

        details.append([Paragraph("EVIDENCE", s["label"])])
        ev_line = (
            f"price=${ev.get('price', 0):,.2f} &nbsp; bid=${ev.get('bid', 0):,.2f} &nbsp; "
            f"ask=${ev.get('ask', 0):,.2f} &nbsp; spread={ev.get('spread_pct', 0):.3f}% &nbsp; "
            f"ob_imbalance={ev.get('orderbook_imbalance', 0):+.3f} &nbsp; exchange={ev.get('exchange', '—').upper()}"
        )
        details.append([Paragraph(ev_line, s["mono_small"])])
        details.append([Paragraph("NEWS INPUT", s["label"])])
        details.append([Paragraph(f"\u201c{r.get('news_summary', '')}\u201d", s["italic"])])

        det_tbl = Table(details, colWidths=[7.2 * inch])
        det_tbl.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )

        block = KeepTogether([hdr_tbl, Spacer(1, 2), det_tbl, Spacer(1, 10)])
        flow.append(block)
    return flow


def _trades_block(s, trades: list[dict]) -> Iterable:
    flow = [Paragraph("TRADE EXECUTION LOG", s["h2"])]
    if not trades:
        flow.append(Paragraph("No trades executed yet.", s["italic"]))
        return flow

    header = ["TIME (UTC)", "SYMBOL", "SIDE", "QTY", "PRICE", "NOTIONAL", "CONF", "P&L", "MODE"]
    data = [[Paragraph(h, s["label"]) for h in header]]
    for t in trades:
        ts = t.get("timestamp", "")
        with contextlib.suppress(Exception):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%m-%d %H:%M:%S")
        side = t.get("side", "")
        side_color = POS if side == "BUY" else NEG
        pnl = t.get("pnl", 0.0) or 0.0
        pnl_color = POS if pnl > 0 else NEG if pnl < 0 else MUTED
        row = [
            Paragraph(ts, s["mono"]),
            Paragraph(t.get("symbol", ""), s["mono"]),
            Paragraph(f"<font color='{side_color.hexval()}'><b>{side}</b></font>", s["body"]),
            Paragraph(f"{float(t.get('quantity', 0)):.6f}", s["mono"]),
            Paragraph(f"${float(t.get('price', 0)):,.2f}", s["mono"]),
            Paragraph(f"${float(t.get('notional', 0)):,.2f}", s["mono"]),
            Paragraph(f"{float(t.get('confidence', 0)):.2f}", s["mono"]),
            Paragraph(
                f"<font color='{pnl_color.hexval()}'>{('+' if pnl > 0 else '') + format(pnl, '.4f') if pnl else '—'}</font>",
                s["body"],
            ),
            Paragraph(t.get("mode", "PAPER"), s["mono"]),
        ]
        data.append(row)
    tbl = Table(
        data,
        colWidths=[1.1 * inch, 0.7 * inch, 0.5 * inch, 0.85 * inch, 0.9 * inch, 0.85 * inch, 0.5 * inch, 0.95 * inch, 0.55 * inch],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, 0), PANEL),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    flow.append(tbl)
    return flow


def _kv_table(s, header: list[str], rows: list[list], col_widths: list) -> Table:
    head = [[Paragraph(h, s["label"]) for h in header]]
    body = [[Paragraph(str(c), s["body"]) for c in r] for r in rows]
    tbl = Table(head + body, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _fmt(v, suffix="", dash="—"):
    return f"{v}{suffix}" if v is not None else dash


def _research_block(s, research: dict) -> Iterable:
    """Phase B research & analytics section for offline analysis."""
    flow = [Paragraph("RESEARCH &amp; ANALYTICS (DIAGNOSTIC)", s["h2"]),
            Paragraph("Evidence-gathering only — no entry logic was changed. Counterfactual-based metrics "
                      "fill in as forward returns (24h/72h/7d) resolve.", s["subtitle"]), Spacer(1, 8)]

    funnel = (research.get("funnel") or {}).get("funnel") or research.get("funnel") or {}
    br = funnel.get("breaker") or {}
    if funnel:
        flow += [Paragraph("Setup Funnel", s["h3"]),
                 _kv_table(s, ["Detected", "Qualified", "PASS", "CAUTION", "VETO", "Executed"],
                           [[funnel.get("detected", 0), funnel.get("qualified", 0), br.get("PASS", 0),
                             br.get("CAUTION", 0), br.get("VETO", 0), funnel.get("executed", 0)]],
                           [1.1 * inch] * 6), Spacer(1, 10)]

    lb = research.get("rejections") or {}
    board = lb.get("rejection_leaderboard") or []
    if board:
        rows = [[b.get("code"), b.get("count"), f"{b.get('pct_of_evals')}%"] for b in board[:12]]
        flow += [Paragraph("Rejection Leaderboard", s["h3"]),
                 _kv_table(s, ["Reason Code", "Count", "% Evals"], rows, [3.4 * inch, 1.1 * inch, 1.1 * inch]),
                 Spacer(1, 10)]

    wp = research.get("winner_profile") or {}
    if wp.get("sample"):
        w, lo = wp.get("winners", {}), wp.get("losers", {})
        rows = [
            ["RSI at entry", _fmt(w.get("avg_rsi")), _fmt(lo.get("avg_rsi"))],
            ["Dist from 50% (%)", _fmt(w.get("avg_distance_from_midpoint_pct")), _fmt(lo.get("avg_distance_from_midpoint_pct"))],
            ["Rel strength vs BTC", _fmt(w.get("avg_relative_strength")), _fmt(lo.get("avg_relative_strength"))],
            ["Support zone score", _fmt(w.get("avg_support_zone_score")), _fmt(lo.get("avg_support_zone_score"))],
            ["MFE (%)", _fmt(w.get("avg_mfe_pct")), _fmt(lo.get("avg_mfe_pct"))],
            ["MAE (%)", _fmt(w.get("avg_mae_pct")), _fmt(lo.get("avg_mae_pct"))],
        ]
        flow += [Paragraph(f"Winning Trade Profile (win rate {wp.get('win_rate_pct')}%, N={wp.get('sample')})", s["h3"]),
                 _kv_table(s, ["Feature", "Winners", "Losers"], rows, [2.6 * inch, 1.6 * inch, 1.6 * inch]),
                 Spacer(1, 10)]

    rsi = (research.get("rsi_distribution") or {}).get("buckets") or []
    if any(b.get("count") for b in rsi):
        rows = [[b["bucket"], b["count"], f"{b['win_rate_pct']}%", _fmt(b["avg_return_pct"], "%"), _fmt(b["avg_drawdown_pct"], "%")] for b in rsi]
        flow += [Paragraph("RSI Distribution Study", s["h3"]),
                 _kv_table(s, ["RSI Band", "Count", "Win Rate", "Avg Ret", "Avg DD"], rows,
                           [1.2 * inch, 1.0 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch]), Spacer(1, 10)]

    miss = (research.get("missed_opportunities") or {}).get("buckets") or []
    if any(b.get("rejected_resolved") for b in miss):
        rows = [[b["filter"], b["rejected_resolved"], b["later_profitable"], b["later_unprofitable"], _fmt(b["net_cf_pnl_pct"], "%")] for b in miss]
        flow += [Paragraph("Missed-Opportunity Analysis", s["h3"]),
                 _kv_table(s, ["Filter", "Resolved", "Later +", "Later −", "Net CF P&L"], rows,
                           [2.0 * inch, 1.0 * inch, 0.9 * inch, 0.9 * inch, 1.1 * inch]), Spacer(1, 10)]

    zones = (research.get("zone_effectiveness") or {}).get("by_symbol") or []
    if zones:
        rows = [[z["symbol"], z["touches"], z["successful_bounces"], z["failed_bounces"], _fmt(z["avg_return_pct"], "%")] for z in zones[:12]]
        flow += [Paragraph("Support-Zone Effectiveness", s["h3"]),
                 _kv_table(s, ["Symbol", "Touches", "Bounces", "Fails", "Avg Ret"], rows,
                           [1.4 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.1 * inch]), Spacer(1, 10)]

    sb = (research.get("strategy_lab") or research.get("strategy_sandbox") or {}).get("strategies") or []
    if sb:
        rows = [[x["name"].split(" / ")[0], x["mode"], x.get("detected", 0), x.get("qualified", 0),
                 x.get("resolved", 0), _fmt(x.get("win_rate_pct"), "%"), _fmt(x.get("avg_return_pct"), "%"),
                 _fmt(x.get("expected_value_pct"), "%"), _fmt(x.get("profit_factor")), x.get("verdict", "")] for x in sb]
        flow += [Paragraph("Strategy Research Laboratory (sorted by Expected Value · Hunter = benchmark)", s["h3"]),
                 _kv_table(s, ["Strategy", "Mode", "Det.", "Qual.", "Resolved", "Win%", "AvgRet", "EV", "PF", "Verdict"], rows,
                           [1.3 * inch, 0.6 * inch, 0.5 * inch, 0.5 * inch, 0.7 * inch, 0.55 * inch, 0.6 * inch, 0.55 * inch, 0.5 * inch, 1.15 * inch]),
                 Spacer(1, 10)]

    se = research.get("staged_exit") or {}
    if se.get("sample"):
        rows = [["Actual (current hard stop)", f"${se['actual_pnl_total']}"],
                ["Theoretical (33/33/34 structure)", f"${se['staged_pnl_total']}"],
                ["Delta", f"${se['delta_total']}"],
                ["Sample / Staged better", f"{se['sample']} / {se['staged_better_count']}"],
                ["Verdict", se["verdict"]]]
        flow += [Paragraph("33/66/99 Staged-Exit Simulation (structure-based)", s["h3"]),
                 _kv_table(s, ["Metric", "Value"], rows, [3.4 * inch, 2.4 * inch]), Spacer(1, 10)]

    return flow


def _reason_chain_block(s, trades: list[dict], limit: int = 6) -> Iterable:
    """Phase E strict Reason-Chain matrix for graded entries: regime + routing,
    indicator matrix, competing hypotheses, and the OHLCV market-state snapshot."""
    graded = []
    for t in trades:
        attr = t.get("entry_attribution") or {}
        rc = attr.get("reason_chain")
        if rc and (attr.get("entry_quality") or {}).get("grade"):
            graded.append((t, attr, rc))
    flow = [Paragraph("REASON CHAIN · DECISION MATRIX (PHASE E)", s["h2"]),
            Paragraph("Per-entry audit trail: which independent model fired, in what regime, on what "
                      "evidence, against which competing hypotheses. Newest first.", s["subtitle"]), Spacer(1, 6)]
    if not graded:
        flow.append(Paragraph("No graded entries recorded yet — populates as Hunter/Squeeze take trades.", s["italic"]))
        return flow

    for t, attr, rc in graded[:limit]:
        eq = attr.get("entry_quality") or {}
        iv = rc.get("indicator_values") or {}
        routing = rc.get("routing") or {}
        # header
        hdr = [[
            Paragraph(f"<b>{t.get('symbol','')}</b>", s["body"]),
            Paragraph(f"<font color='{CYAN.hexval()}'><b>{(attr.get('strategy') or '—').upper()}</b></font>", s["body"]),
            Paragraph(f"{attr.get('entry_profile','—')}", s["mono"]),
            Paragraph(f"GRADE <b>{eq.get('grade','—')}</b> ({eq.get('pct','—')})", s["body"]),
            Paragraph(f"{rc.get('regime','—')}", s["body"]),
        ]]
        hdr_tbl = Table(hdr, colWidths=[0.9 * inch, 1.0 * inch, 1.9 * inch, 1.6 * inch, 1.8 * inch])
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PANEL), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ]))

        rule = f"Route: {routing.get('rationale','—')}"
        ind = (f"RSI={_fmt(iv.get('rsi_4h'))} ADX={_fmt(iv.get('adx'))} ATR%={_fmt(iv.get('atr_percentile'))} "
               f"BBW%={_fmt(iv.get('bbwidth_percentile'))} EMA={_fmt(iv.get('ema_stack'))} "
               f"RS-BTC={_fmt(iv.get('relative_strength_btc'))} BTCregime={_fmt(iv.get('btc_macro_regime'))}")
        comp = rc.get("competing_hypotheses") or []
        comp_line = "  ".join(
            f"{c.get('strategy')}[{'D' if c.get('detected') else '-'}{'Q' if c.get('qualified') else '-'}]"
            for c in comp) or "—"

        meta = Table([
            [Paragraph("ROUTING", s["label"])], [Paragraph(rule, s["mono"])],
            [Paragraph("INDICATOR MATRIX", s["label"])], [Paragraph(ind, s["mono_small"])],
            [Paragraph("COMPETING HYPOTHESES (Detected/Qualified)", s["label"])], [Paragraph(comp_line, s["mono_small"])],
        ], colWidths=[7.2 * inch])
        meta.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

        # OHLCV matrix
        snap = rc.get("market_state_snapshot") or []
        mtx = [[Paragraph(h, s["label"]) for h in ["#", "OPEN", "HIGH", "LOW", "CLOSE", "VOL"]]]
        for i, b in enumerate(snap):
            mtx.append([
                Paragraph(str(i + 1), s["mono_small"]),
                Paragraph(f"{b.get('o', 0):,.4f}", s["mono_small"]),
                Paragraph(f"{b.get('h', 0):,.4f}", s["mono_small"]),
                Paragraph(f"{b.get('l', 0):,.4f}", s["mono_small"]),
                Paragraph(f"{b.get('c', 0):,.4f}", s["mono_small"]),
                Paragraph(f"{b.get('v', 0):,.2f}", s["mono_small"]),
            ])
        mtx_tbl = Table(mtx, colWidths=[0.5 * inch, 1.34 * inch, 1.34 * inch, 1.34 * inch, 1.34 * inch, 1.34 * inch], repeatRows=1)
        mtx_tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, RULE), ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
            ("BACKGROUND", (0, 0), (-1, 0), PANEL),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))

        flow.append(KeepTogether([hdr_tbl, Spacer(1, 2), meta, Spacer(1, 3),
                                  Paragraph("MARKET-STATE SNAPSHOT (4H OHLCV)", s["label"]), mtx_tbl, Spacer(1, 12)]))
    return flow


def _exit_engine_block(s, trades: list[dict]) -> Iterable:
    """Phase F Universal Exit Engine analytics: per-module distribution + MFE/MAE
    capture efficiency. Built from closed SELL legs (research, not advice)."""
    sells = [t for t in trades if t.get("side") == "SELL" and (t.get("exit_module") or t.get("exit_reason"))]
    flow = [Paragraph("UNIVERSAL EXIT ENGINE · RESEARCH (PHASE F)", s["h2"]),
            Paragraph("Decoupled Trade Manager. Modules A-F evaluated every cycle; deterministic priority "
                      "arbitration executes the single highest-priority action. MFE/MAE capture efficiency "
                      "shows how much of the best achievable move each exit kept.", s["subtitle"]), Spacer(1, 8)]
    if not sells:
        flow.append(Paragraph("No engine-managed exits recorded yet — populates as positions close.", s["italic"]))
        return flow

    _names = {
        "A": "A · Structural Failure", "B": "B · Momentum Exhaustion (50%)", "C": "C · ATR Trail",
        "D": "D · EMA Trend Loss", "E": "E · Time Exit", "F": "F · Profit Protection", "KILL": "Kill / Emergency",
    }
    # group by module (fall back to legacy exit_reason)
    groups: dict[str, list[dict]] = {}
    for t in sells:
        key = t.get("exit_module") or {"SL_HIT": "A", "TRAIL_HIT": "C"}.get(t.get("exit_reason"), "—")
        groups.setdefault(key, []).append(t)

    rows = []
    for key in sorted(groups):
        g = groups[key]
        n = len(g)
        wins = sum(1 for t in g if (t.get("pnl") or 0) > 0)
        rets = [t.get("return_pct") for t in g if t.get("return_pct") is not None]
        mfes = [t.get("mfe_pct") for t in g if t.get("mfe_pct") is not None]
        maes = [t.get("mae_pct") for t in g if t.get("mae_pct") is not None]
        avg_ret = round(sum(rets) / len(rets), 2) if rets else None
        avg_mfe = round(sum(mfes) / len(mfes), 2) if mfes else None
        avg_mae = round(sum(maes) / len(maes), 2) if maes else None
        rows.append([_names.get(key, key), n, f"{round(wins / n * 100)}%",
                     _fmt(avg_ret, "%"), _fmt(avg_mfe, "%"), _fmt(avg_mae, "%")])
    flow += [Paragraph("Exit-Module Distribution", s["h3"]),
             _kv_table(s, ["Exit Module", "Count", "Win%", "Avg Ret", "Avg MFE", "Avg MAE"], rows,
                       [2.4 * inch, 0.8 * inch, 0.8 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch]), Spacer(1, 10)]

    # capture efficiency: realized return vs the best achievable (MFE)
    eff = [t for t in sells if t.get("return_pct") is not None and t.get("mfe_pct")]
    if eff:
        caps = [max(-100.0, min(200.0, (t["return_pct"] / t["mfe_pct"]) * 100.0)) for t in eff if t["mfe_pct"] > 0]
        avg_cap = round(sum(caps) / len(caps), 1) if caps else None
        avg_mfe = round(sum(t["mfe_pct"] for t in eff) / len(eff), 2)
        avg_ret = round(sum(t["return_pct"] for t in eff) / len(eff), 2)
        rows = [
            ["Closed exits analysed", str(len(eff))],
            ["Avg MFE (best achievable)", f"{avg_mfe}%"],
            ["Avg realized return", f"{avg_ret}%"],
            ["Avg capture of MFE", f"{avg_cap}%" if avg_cap is not None else "—"],
        ]
        flow += [Paragraph("MFE Capture Efficiency", s["h3"]),
                 _kv_table(s, ["Metric", "Value"], rows, [3.6 * inch, 2.2 * inch]), Spacer(1, 10)]
    return flow


def build_report(
    portfolio: dict,
    risk: dict,
    reasoning_items: list[dict],
    trades: list[dict],
    settings: dict,
    research: dict | None = None,
) -> bytes:
    """Return the PDF bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.6 * inch,
        title="Ananta AI - Validation & Research Report",
        author="Ananta.AI",
    )
    s = _styles()

    flow = []
    # title
    flow.append(Paragraph("Ananta AI · Validation &amp; Research Report", s["title"]))
    flow.append(
        Paragraph(
            "Scale-independent multi-asset swing framework. Technical-first Hunter · tri-state Circuit "
            "Breaker · PAPER validation · counterfactual evidence — research &amp; analytics, not advice.",
            s["subtitle"],
        )
    )
    flow.extend(_portfolio_block(s, portfolio, risk))
    if research:
        flow.append(PageBreak())
        flow.extend(_research_block(s, research))
    flow.append(PageBreak())
    flow.extend(_exit_engine_block(s, list(reversed(trades))))
    flow.append(PageBreak())
    flow.extend(_reason_chain_block(s, list(reversed(trades))))
    flow.append(PageBreak())
    # reasoning (chronological oldest-first reads more naturally in a report)
    flow.extend(_reasoning_block(s, list(reversed(reasoning_items))))
    flow.append(PageBreak())
    flow.extend(_trades_block(s, list(reversed(trades))))

    doc.build(flow, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()


def _trades_summary_block(s, summary: dict) -> Iterable:
    """Plain-English performance summary header for the trade-history export."""
    wr = summary.get("win_rate_pct", 0.0)
    lr = summary.get("loss_rate_pct", 0.0)
    net = summary.get("net_pnl_usd", 0.0)
    exp = summary.get("expectancy_usd", 0.0)
    closed = summary.get("closed_trades", 0)
    net_c = POS if net > 0 else NEG if net < 0 else MUTED
    exp_c = POS if exp > 0 else NEG if exp < 0 else MUTED

    cells = [
        ("CLOSED TRADES", f"{closed}", TEXT),
        ("WIN RATE", f"{wr:.1f}%", POS if wr >= 50 else MUTED),
        ("LOSS RATE", f"{lr:.1f}%", NEG if lr > 50 else MUTED),
        ("EXPECTANCY / TRADE", f"{'+' if exp > 0 else ''}${exp:.2f}", exp_c),
        ("NET REALIZED P&L", f"{'+' if net > 0 else ''}${net:.2f}", net_c),
    ]
    head = [[Paragraph(k, s["label"]) for k, _, _ in cells]]
    vals = [[Paragraph(f"<font color='{c.hexval()}'><b>{v}</b></font>", s["body"]) for _, v, c in cells]]
    tbl = Table(head + vals, colWidths=[1.44 * inch] * 5)
    tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
                ("BACKGROUND", (0, 0), (-1, 0), PANEL),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return [Paragraph("PERFORMANCE SUMMARY", s["h2"]), tbl, Spacer(1, 12)]


def build_trades_report(
    trades: list[dict],
    start_label: str | None = None,
    end_label: str | None = None,
    summary: dict | None = None,
    scorecard_strategy: str | None = "squeeze",
) -> bytes:
    """Clean, chronological printout of EXECUTED trades over a date range.

    `trades` should already be filtered to FILLED trades; this builder sorts
    oldest-first and renders a performance summary (win/loss rate, expectancy,
    net P&L) followed by the chronological trade table.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.6 * inch,
        title="Ananta AI - Trade History",
        author="Ananta.AI",
    )
    s = _styles()

    def _ts_key(t: dict) -> str:
        return t.get("timestamp", "") or ""

    ordered = sorted(trades, key=_ts_key)  # chronological, oldest-first

    rng = "All executed trades"
    if start_label or end_label:
        rng = f"{start_label or 'beginning'} → {end_label or 'now'}"

    flow = [
        Paragraph("Ananta AI · Trade History", s["title"]),
        Paragraph(
            f"Chronological export of executed trades. Range: {rng}. "
            f"Total executed legs: {len(ordered)}.",
            s["subtitle"],
        ),
    ]
    if summary:
        flow.extend(_trades_summary_block(s, summary))
    if scorecard_strategy:
        flow.extend(_scorecard_block(s, ordered, strategy=scorecard_strategy))
    flow.extend(_trades_block(s, ordered))  # already oldest-first

    doc.build(flow, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()



# ---------------------------------------------------------------------------
# Daily paper-test scorecard — tracks a strategy's live paper trades against the
# user's aggressive targets (win rate 38-48%, profit factor 1.4-1.8) plus Max
# Drawdown and MFE capture. Renders even with zero trades (shows the targets).
# ---------------------------------------------------------------------------
def _band_status(v, lo, hi):
    if v is None:
        return "—"
    if v < lo:
        return "BELOW TARGET"
    if v > hi:
        return "ABOVE TARGET"
    return "ON TARGET"


def _scorecard_block(s, trades: list, strategy: str = "squeeze",
                     win_target=(38.0, 48.0), pf_target=(1.4, 1.8),
                     base_equity: float = 1200.0):
    label = strategy.replace("_", " ").title()
    sells = [t for t in trades
             if t.get("side") == "SELL" and (t.get("strategy") or "").lower() == strategy.lower()
             and (t.get("status", "FILLED") or "FILLED") == "FILLED"]
    header = ["Metric", "Value", "Target", "Status"]
    widths = [1.7 * inch, 1.4 * inch, 1.5 * inch, 1.7 * inch]
    title = [Paragraph(f"{label} Paper-Test Scorecard", s["h2"]),
             Paragraph("Live paper trades for this strategy vs the aggressive validation targets. "
                       "Populates as the 7-10 day test accumulates closed trades.", s["subtitle"])]
    if not sells:
        rows = [
            ["Win rate", "no trades yet", f"{win_target[0]:g}-{win_target[1]:g}%", "AWAITING DATA"],
            ["Profit factor", "no trades yet", f"{pf_target[0]:g}-{pf_target[1]:g}", "AWAITING DATA"],
            ["Max drawdown", "no trades yet", "lower is better", "AWAITING DATA"],
            ["MFE capture", "no trades yet", "higher is better", "AWAITING DATA"],
        ]
        return title + [_kv_table(s, header, rows, widths),
                        Paragraph(f"No closed {label} trades in this range yet.", s["italic"]),
                        Spacer(1, 12)]

    n = len(sells)
    pnls = [float(t.get("pnl", 0.0) or 0.0) for t in sells]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    win_rate = round(wins / n * 100, 1)
    pf = round(gw / gl, 2) if gl > 0 else (None if gw == 0 else 999.99)
    # Max drawdown on the chronological realised-P&L equity curve.
    eq = base_equity
    peak = eq
    maxdd = 0.0
    for t in sorted(sells, key=lambda x: x.get("timestamp", "")):
        eq += float(t.get("pnl", 0.0) or 0.0)
        peak = max(peak, eq)
        if peak > 0:
            maxdd = max(maxdd, (peak - eq) / peak * 100.0)
    maxdd = round(maxdd, 2)
    # MFE capture: aggregate realised return vs aggregate favourable excursion.
    tot_mfe = sum(float(t.get("mfe_pct") or 0.0) for t in sells if (t.get("mfe_pct") or 0) > 0)
    tot_ret = sum(float(t.get("return_pct") or 0.0) for t in sells)
    capture = round(tot_ret / tot_mfe * 100, 1) if tot_mfe > 0 else None

    pf_disp = ("∞" if (pf and pf >= 999) else (f"{pf:.2f}" if pf is not None else "—"))
    rows = [
        ["Win rate", f"{win_rate}%", f"{win_target[0]:g}-{win_target[1]:g}%", _band_status(win_rate, *win_target)],
        ["Profit factor", pf_disp, f"{pf_target[0]:g}-{pf_target[1]:g}", _band_status(pf, *pf_target)],
        ["Max drawdown", f"{maxdd}%", "lower is better", ("WATCH" if maxdd >= 10 else "OK")],
        ["MFE capture", (f"{capture}%" if capture is not None else "—"), "higher is better",
         ("STRONG" if (capture or 0) >= 40 else "LOW" if capture is not None else "—")],
    ]
    note = Paragraph(
        f"Based on {n} closed {label} trade{'s' if n != 1 else ''}. Small samples are directional; "
        f"re-read after ~30-40 trades. Drawdown vs a ${base_equity:g} baseline.", s["italic"])
    return title + [_kv_table(s, header, rows, widths), note, Spacer(1, 12)]
