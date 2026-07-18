import { useState, useEffect, useCallback, useRef } from "react";
import { FileText, Loader2, Download, Sparkles, Trash2, RefreshCw, Clock, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { downloadPdf, PDFS_EVENT } from "@/lib/pdfRegistry";

const KIND_LABELS = {
    backtest: "Validation",
    grid_search: "Grid Search",
    sensitivity: "Sensitivity",
    walk_forward: "Walk-Forward",
    health_sweep: "Health Sweep",
};
const EXIT_LABELS = {
    fixed: "Fixed % Target",
    atr: "ATR Trail",
    native: "Full Engine",
    engine: "Full Engine",
};
const PERIOD_LABELS = {
    "1m": "1 month", "2m": "2 months", "3m": "3 months", quarter: "1 quarter",
    "6m": "6 months", "1y": "1 year", "2y": "2 years", custom: "Custom",
};

const fmtDate = (iso) => { try { return new Date(iso).toLocaleString(); } catch { return "—"; } };
const stratList = (r) => {
    if (r.kind === "health_sweep") return "All strategies";
    const s = r.strategies || [];
    if (!s.length) return "—";
    return s.join(" + ");
};

/**
 * Server-backed "My Reports History" — reads GET /api/lab/runs so validation reports
 * persist across browser sessions and devices. Replaces the old browser-local PDF list.
 * Shared by Research › AI Analysis, Exit Engine › AI Analysis and Workspace › AI Analytics.
 */
export default function AnantaPdfs({ isOwner }) {
    const [runs, setRuns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState(null); // "owner" | "load" | null
    const [prog, setProg] = useState({}); // id -> pct | 'prep' | 'err' | 100
    const inflight = useRef(false);

    const load = useCallback(async () => {
        if (inflight.current) return;
        inflight.current = true;
        try {
            const d = await api.labRuns(50);
            // "My Reports" = user-initiated validations. Automated daily health sweeps have
            // their own HEALTH dashboard, so keep them out of this history list.
            setRuns((d.runs || []).filter((r) => r.kind !== "health_sweep").slice(0, 30));
            setErr(null);
        } catch (e) {
            const st = e?.response?.status;
            setErr(st === 401 || st === 403 ? "owner" : "load");
        } finally {
            inflight.current = false;
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
        const h = () => load();
        window.addEventListener(PDFS_EVENT, h); // a new validation run just finished → refresh
        return () => window.removeEventListener(PDFS_EVENT, h);
    }, [load]);

    // Poll while any run is still QUEUED/RUNNING so progress + completion surface live.
    useEffect(() => {
        const active = runs.some((r) => r.status === "QUEUED" || r.status === "RUNNING");
        if (!active) return;
        const t = setInterval(load, 5000);
        return () => clearInterval(t);
    }, [runs, load]);

    const download = async (r) => {
        setProg((s) => ({ ...s, [r.id]: "prep" }));
        try {
            const fname = `Ananta_${KIND_LABELS[r.kind] || r.kind}_${r.id.slice(0, 8)}.pdf`;
            await downloadPdf(`/lab/runs/${r.id}/pdf`, fname, (pct) => setProg((s) => ({ ...s, [r.id]: pct == null ? "prep" : pct })));
            setProg((s) => ({ ...s, [r.id]: 100 }));
            toast.success("Download complete");
            setTimeout(() => setProg((s) => { const n = { ...s }; delete n[r.id]; return n; }), 2500);
        } catch (e) {
            setProg((s) => ({ ...s, [r.id]: "err" }));
            toast.error(String(e?.message || e));
        }
    };

    const analyse = (r) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        const title = `${KIND_LABELS[r.kind] || r.kind} · ${stratList(r)}`;
        window.dispatchEvent(new CustomEvent("ananta:ask", { detail: { text: `Analyse my "${title}" validation report and give me the key takeaways, risks and one improvement.` } }));
        toast.success("Ask Ananta is reviewing your report");
    };

    const remove = async (r) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        if (!window.confirm("Delete this report permanently? This cannot be undone.")) return;
        try {
            await api.deleteLabRun(r.id);
            setRuns((list) => list.filter((x) => x.id !== r.id));
            toast.success("Report deleted");
        } catch (e) {
            toast.error(String(e?.response?.data?.detail || e?.message || e));
        }
    };

    const label = (v) => (v === "prep" ? "Preparing…" : v === "err" ? "Retry" : v === 100 ? "Done" : `${v}%`);

    if (loading) {
        return (
            <div className="panel border-atlas-border rounded-xl p-5" data-testid="reports-history">
                <div className="py-8 grid place-items-center text-atlas-textTertiary" data-testid="reports-loading">
                    <Loader2 className="w-5 h-5 animate-spin" />
                </div>
            </div>
        );
    }

    if (err === "owner") {
        return (
            <div className="panel border-atlas-border rounded-xl p-5" data-testid="reports-history">
                <div className="py-6 text-center font-mono text-[11px] text-atlas-textTertiary" data-testid="reports-owner-gate">
                    Owner login required to view your reports history.
                </div>
            </div>
        );
    }

    if (err === "load") {
        return (
            <div className="panel border-atlas-border rounded-xl p-5" data-testid="reports-history">
                <div className="py-6 flex flex-col items-center gap-3 text-center" data-testid="reports-error">
                    <span className="font-mono text-[11px] text-atlas-negative">Couldn&apos;t load your reports.</span>
                    <button data-testid="reports-retry" onClick={load}
                        className="flex items-center gap-1.5 rounded-lg border border-atlas-border px-3 py-1.5 font-mono text-[10px] text-atlas-text hover:border-atlas-cyan hover:text-atlas-cyan transition-colors">
                        <RefreshCw className="w-3.5 h-3.5" /> Retry
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="panel border-atlas-border rounded-xl p-5" data-testid="reports-history">
            {runs.length === 0 ? (
                <div className="py-6 text-center font-mono text-[11px] text-atlas-textTertiary" data-testid="reports-empty">
                    No reports yet. Complete a Research validation run and it&apos;ll appear here — saved to your account across every device.
                </div>
            ) : (
                <div className="rounded-lg border border-atlas-border divide-y divide-atlas-border max-h-[28rem] overflow-y-auto atlas-scroll">
                    {runs.map((r) => {
                        const st = prog[r.id];
                        const busy = st !== undefined && st !== "err";
                        const pct = typeof st === "number" ? st : null;
                        const done = r.status === "DONE";
                        const running = r.status === "QUEUED" || r.status === "RUNNING";
                        const failed = r.status === "FAILED" || r.status === "ERROR";
                        return (
                            <div key={r.id} className="px-3 py-3 flex items-start gap-3" data-testid="report-row">
                                <FileText className="w-4 h-4 text-atlas-cyan shrink-0 mt-0.5" />
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-mono text-[12px] text-atlas-text truncate" data-testid="report-title">
                                            {KIND_LABELS[r.kind] || r.kind} · {stratList(r)}
                                        </span>
                                        <StatusBadge status={r.status} pct={r.progress_pct} />
                                    </div>
                                    {/* meta chips */}
                                    <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                                        <Chip>TF {r.timeframe || "1h"}{r.compare_timeframes ? " · MTF" : ""}</Chip>
                                        {r.exit_method && <Chip>{EXIT_LABELS[r.exit_method] || r.exit_method}</Chip>}
                                        <Chip>{PERIOD_LABELS[r.period] || r.period}</Chip>
                                        {(r.symbols || []).length > 0 && <Chip>{(r.symbols || []).length} asset{(r.symbols || []).length > 1 ? "s" : ""}</Chip>}
                                    </div>
                                    {st !== undefined ? (
                                        <div className="mt-2 flex items-center gap-2" data-testid="report-progress">
                                            <div className="h-1 flex-1 rounded-full bg-atlas-border overflow-hidden">
                                                <div className={`h-full ${st === "err" ? "bg-atlas-negative" : "bg-atlas-cyan"} transition-all`} style={{ width: pct != null ? `${pct}%` : "35%" }} />
                                            </div>
                                            <span className={`font-mono text-[9px] ${st === "err" ? "text-atlas-negative" : "text-atlas-cyan"}`}>{label(st)}</span>
                                        </div>
                                    ) : (
                                        <div className="mt-1 font-mono text-[9px] text-atlas-textTertiary" data-testid="report-date">{fmtDate(r.finished_at || r.created_at)}</div>
                                    )}
                                </div>
                                <div className="flex items-center gap-1.5 shrink-0">
                                    <button data-testid="report-download" onClick={() => download(r)} disabled={busy || !done} title={done ? "Download PDF" : "Report not ready"}
                                        className="p-1.5 rounded-lg border border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                                        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                                    </button>
                                    <button data-testid="report-analyse" onClick={() => analyse(r)} disabled={!done} title="Ask Ananta to analyse"
                                        className="p-1.5 rounded-lg border border-atlas-cyan/40 text-atlas-cyan hover:bg-atlas-cyan/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"><Sparkles className="w-3.5 h-3.5" /></button>
                                    <button data-testid="report-delete" onClick={() => remove(r)} disabled={running} title="Delete"
                                        className="p-1.5 rounded-lg border border-atlas-border text-atlas-textSecondary hover:text-atlas-negative hover:border-atlas-negative/40 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"><Trash2 className="w-3.5 h-3.5" /></button>
                                </div>
                                {failed && <span className="sr-only">failed</span>}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function Chip({ children }) {
    return <span className="font-mono text-[9px] tracking-wide text-atlas-textSecondary bg-atlas-panel border border-atlas-border rounded px-1.5 py-0.5">{children}</span>;
}

function StatusBadge({ status, pct }) {
    if (status === "DONE") return (
        <span className="flex items-center gap-1 font-mono text-[9px] text-atlas-positive" data-testid="report-status"><CheckCircle2 className="w-3 h-3" /> DONE</span>
    );
    if (status === "FAILED" || status === "ERROR") return (
        <span className="flex items-center gap-1 font-mono text-[9px] text-atlas-negative" data-testid="report-status"><XCircle className="w-3 h-3" /> FAILED</span>
    );
    return (
        <span className="flex items-center gap-1 font-mono text-[9px] text-atlas-cyan" data-testid="report-status">
            <Clock className="w-3 h-3 animate-pulse" /> {status === "RUNNING" ? `RUNNING ${Math.round(pct || 0)}%` : "QUEUED"}
        </span>
    );
}
