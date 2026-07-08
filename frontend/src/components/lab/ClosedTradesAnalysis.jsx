import { useEffect, useState } from "react";
import { FileText, Radio, Download, ExternalLink, Sparkles, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import api, { API } from "@/lib/api";
import { useAppData } from "@/context/AppDataContext";
import { useAuth } from "@/context/AuthContext";

const isPaper = (t) => ["PAPER", "DRY_RUN"].includes(t.mode);
const isLive = (t) => t.mode === "LIVE";
const pnlCls = (v) => (v > 0 ? "text-atlas-positive" : v < 0 ? "text-atlas-negative" : "text-atlas-textSecondary");

/**
 * Two books — Closed Paper Trades & Closed Live Trades. Each lists the trades and
 * an "Analyse Trades" button that produces a report (AI review + PDF download + open on web).
 */
export default function ClosedTradesAnalysis({ isOwner }) {
    const { trades } = useAppData();
    const [modal, setModal] = useState(null); // 'paper' | 'live'

    const closed = (trades || []).filter((t) => t.side === "SELL" && (t.status || "FILLED") === "FILLED" && t.pnl != null);
    const paper = closed.filter(isPaper);
    const live = closed.filter(isLive);

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4" data-testid="closed-trades-analysis">
            <Box testid="closed-paper-box" icon={FileText} title="Closed Paper Trades" mode="paper" rows={paper} onAnalyse={() => setModal("paper")} isOwner={isOwner} />
            <Box testid="closed-live-box" icon={Radio} title="Closed Live Trades" mode="live" rows={live} onAnalyse={() => setModal("live")} isOwner={isOwner} />
            {modal && <ReportModal mode={modal} isOwner={isOwner} onClose={() => setModal(null)} />}
        </div>
    );
}

function Box({ testid, icon: Icon, title, mode, rows, onAnalyse, isOwner }) {
    const net = rows.reduce((a, t) => a + (t.pnl || 0), 0);
    const wins = rows.filter((t) => (t.pnl || 0) > 0).length;
    const wr = rows.length ? Math.round((100 * wins) / rows.length) : 0;
    return (
        <div data-testid={testid} className="panel border-atlas-border rounded-2xl p-5 flex flex-col">
            <div className="flex items-center gap-2.5 mb-3">
                <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Icon className="w-4.5 h-4.5 text-atlas-cyan" /></span>
                <div><div className="font-heading text-base text-atlas-text leading-none">{title}</div>
                    <div className="label-tag mt-1 text-[9px] text-atlas-textTertiary">{rows.length} closed · {wr}% win rate</div></div>
                <span className={`ml-auto font-mono text-sm font-bold tabular-nums ${pnlCls(net)}`}>{net >= 0 ? "+" : ""}${net.toFixed(2)}</span>
            </div>
            <div className="flex-1 min-h-[120px] max-h-56 overflow-y-auto atlas-scroll rounded-lg border border-atlas-border divide-y divide-atlas-border">
                {rows.length === 0 ? (
                    <div className="p-6 text-center font-mono text-[11px] text-atlas-textTertiary" data-testid={`${testid}-empty`}>No closed {mode} trades yet.</div>
                ) : rows.slice(0, 40).map((t) => (
                    <div key={t.id} className="px-3 py-2 flex items-center justify-between font-mono text-[11px]" data-testid={`${testid}-row`}>
                        <span className="text-atlas-text font-bold">{(t.symbol || "").split("/")[0]}</span>
                        <span className="text-atlas-textTertiary truncate mx-2 flex-1">{t.exit_reason || "-"}</span>
                        <span className={`tabular-nums font-bold ${pnlCls(t.pnl)}`}>{t.pnl >= 0 ? "+" : ""}${(t.pnl || 0).toFixed(2)}</span>
                    </div>
                ))}
            </div>
            <div className="flex justify-end mt-3">
                <button data-testid={`analyse-${mode}-btn`} onClick={onAnalyse} disabled={!isOwner}
                    className="flex items-center gap-2 rounded-lg bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-4 py-2.5 transition-colors disabled:opacity-40"
                    title={isOwner ? "Generate a report for these trades" : "Owner login required"}>
                    <Sparkles className="w-3.5 h-3.5" /> ANALYSE TRADES
                </button>
            </div>
        </div>
    );
}

function ReportModal({ mode, isOwner, onClose }) {
    const [loading, setLoading] = useState(true);
    const [review, setReview] = useState(null);

    useEffect(() => {
        let alive = true;
        api.coachTradesReview(mode)
            .then((r) => alive && setReview(r))
            .catch((e) => { if (alive) { setReview({ review: `Could not generate review: ${e?.response?.data?.detail || e?.message}` }); } })
            .finally(() => alive && setLoading(false));
        return () => { alive = false; };
    }, [mode]);

    const pdfUrl = (inline) => `${API}/report/trades.pdf?mode=${mode}${inline ? "&inline=true" : ""}`;

    return (
        <div className="fixed inset-0 z-[60] bg-atlas-bg/90 backdrop-blur-md flex items-center justify-center p-4" data-testid="trades-report-modal">
            <div className="w-full max-w-2xl panel border-atlas-border rounded-2xl overflow-hidden">
                <div className="flex items-center justify-between px-5 py-4 border-b border-atlas-border">
                    <div className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-atlas-cyan" />
                        <span className="font-heading text-base text-atlas-text capitalize">{mode} Trades — Analysis</span></div>
                    <button data-testid="report-close" onClick={onClose} className="text-atlas-textTertiary hover:text-atlas-text"><X className="w-4 h-4" /></button>
                </div>
                <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto atlas-scroll">
                    <div className="panel border-atlas-border rounded-xl p-4" data-testid="report-ai-review">
                        <div className="label-tag mb-2 text-atlas-cyan">AI REVIEW · uses credits</div>
                        {loading ? (
                            <div className="flex items-center gap-2 font-mono text-[11px] text-atlas-textSecondary"><Loader2 className="w-4 h-4 animate-spin" /> Reviewing your {mode} trades…</div>
                        ) : (
                            <p className="font-mono text-[12px] text-atlas-text leading-relaxed whitespace-pre-wrap">{review?.review}</p>
                        )}
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                        <a data-testid="report-download-pdf" href={pdfUrl(false)} target="_blank" rel="noreferrer"
                            onClick={() => toast.success("PDF download started")}
                            className="flex items-center gap-2 rounded-lg border border-atlas-border px-4 py-2.5 font-mono text-[11px] tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-cyan transition-colors">
                            <Download className="w-4 h-4" /> DOWNLOAD PDF
                        </a>
                        <a data-testid="report-open-web" href={pdfUrl(true)} target="_blank" rel="noreferrer"
                            className="flex items-center gap-2 rounded-lg border border-atlas-cyan/40 text-atlas-cyan hover:bg-atlas-cyan/10 px-4 py-2.5 font-mono text-[11px] tracking-widest transition-colors">
                            <ExternalLink className="w-4 h-4" /> OPEN ON WEB
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}
