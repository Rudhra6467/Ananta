import { useEffect, useRef, useState } from "react";
import {
    Activity, Award, Clock, DoorOpen, Gauge, Loader2, Play, RefreshCw,
    Download, AlertTriangle, CheckCircle2, XCircle, MinusCircle,
} from "lucide-react";
import { toast } from "sonner";
import api, { API } from "@/lib/api";
import { downloadPdf, registerPdf } from "@/lib/pdfRegistry";

const REGIME_LABELS = {
    TREND_UP: "Trend Up", TREND_DOWN: "Trend Down", REVERSAL: "Reversal",
    COMPRESSION: "Compression", RANGE: "Range", NEUTRAL: "Neutral",
};
const BADGE = {
    positive: { icon: CheckCircle2, cls: "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10" },
    warning: { icon: MinusCircle, cls: "text-atlas-warning border-atlas-warning/40 bg-atlas-warning/10" },
    negative: { icon: XCircle, cls: "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/10" },
};
const PERIODS = [{ k: "3m", l: "3 Months" }, { k: "6m", l: "6 Months" }, { k: "1y", l: "1 Year" }];
const fmtPct = (x, d = 1) => { const n = Number(x); return isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(d)}%` : "—"; };
const fmtPf = (x) => (x == null ? "—" : (x >= 999 ? "∞" : Number(x).toFixed(2)));
const posCls = (x) => (Number(x) >= 0 ? "text-atlas-positive" : "text-atlas-negative");

/** Strategy Health Dashboard — reads the pre-computed daily/manual sweep (instant, no compute). */
export default function StrategyHealthPanel({ isOwner }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [active, setActive] = useState(null);   // in-flight sweep {status, progress_pct}
    const [showRun, setShowRun] = useState(false);
    const [period, setPeriod] = useState("3m");
    const [scope, setScope] = useState("full");
    const [busy, setBusy] = useState(false);
    const pollRef = useRef(null);

    const load = async () => {
        try {
            const d = await api.labHealth();
            setData(d?.ready ? d : null);
            setActive(d?.active || null);
            if (d?.active) startPolling();
        } catch { /* read-only endpoint; ignore */ }
        finally { setLoading(false); }
    };

    const startPolling = () => {
        if (pollRef.current) return;
        pollRef.current = setInterval(async () => {
            try {
                const s = await api.labHealthStatus();
                if (s?.active) {
                    setActive(s.active);
                } else {
                    clearInterval(pollRef.current); pollRef.current = null;
                    setActive(null);
                    const d = await api.labHealth();
                    setData(d?.ready ? d : null);
                    toast.success("Strategy Health updated", { description: "Fresh analysis is ready." });
                }
            } catch { /* keep polling */ }
        }, 3000);
    };

    useEffect(() => {
        load();
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, []);

    const runSweep = async () => {
        setBusy(true);
        try {
            const r = await api.labHealthRun({ scope, period });
            setShowRun(false);
            setActive({ status: "QUEUED", progress_pct: 0 });
            toast.info("Full analysis started", { description: `${r.strategy_count} strategies · runs in the background (several minutes).` });
            startPolling();
        } catch (e) {
            toast.error("Could not start analysis", { description: String(e?.response?.data?.detail || e?.message) });
        } finally { setBusy(false); }
    };

    const [pdfBusy, setPdfBusy] = useState(false);
    const downloadReport = async () => {
        if (!data?.run_id) return;
        setPdfBusy(true);
        const url = `${API}/lab/runs/${data.run_id}/pdf`;
        try {
            await downloadPdf(url, `Strategy_Health_${(data.period || "3m")}.pdf`);
            registerPdf({ title: `Strategy Health · full analysis · ${data.period}`, type: "lab", url });
            toast.success("Report downloaded", { description: "Also added to AI Analysis › Reports." });
        } catch (e) {
            toast.error("Download failed", { description: String(e?.message) });
        } finally { setPdfBusy(false); }
    };

    const cards = (data?.strategies || []).slice().sort((a, b) => {
        const ord = { positive: 0, warning: 1, negative: 2 };
        return (ord[a.recommendation?.tone] ?? 3) - (ord[b.recommendation?.tone] ?? 3);
    });

    return (
        <div className="space-y-4" data-testid="strategy-health-panel">
            {/* header */}
            <div className="panel border-atlas-border rounded-2xl p-4 flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-2.5">
                    <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Activity className="w-4 h-4 text-atlas-cyan" /></span>
                    <div>
                        <div className="font-heading text-lg text-atlas-text leading-none">Strategy Health</div>
                        <div className="label-tag mt-1 text-[9px] text-atlas-textTertiary">
                            {data?.generated_at ? `Updated ${data.generated_at.slice(0, 16).replace("T", " ")} UTC · ${(data.symbols || []).map((x) => x.split("/")[0]).join(" · ")} · ${data.period}` : "Pre-computed daily analysis"}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {data?.run_id && (
                        <button data-testid="health-download-pdf" onClick={downloadReport} disabled={pdfBusy}
                            className="flex items-center gap-1.5 rounded-lg border border-atlas-cyan/50 bg-atlas-cyan/10 px-3 py-2 font-mono text-[10px] tracking-widest font-bold text-atlas-cyan hover:bg-atlas-cyan/20 disabled:opacity-60 transition-colors">
                            {pdfBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} PDF
                        </button>
                    )}
                    {isOwner && !active && (
                        <button data-testid="health-run-toggle" onClick={() => setShowRun((v) => !v)}
                            className="flex items-center gap-1.5 rounded-lg bg-atlas-cyan text-atlas-bg px-3.5 py-2 font-mono text-[10px] tracking-widest font-bold hover:brightness-110 transition-all">
                            <Play className="w-3.5 h-3.5" /> RUN FULL ANALYSIS
                        </button>
                    )}
                </div>
            </div>

            {/* run confirmation / warning */}
            {showRun && isOwner && !active && (
                <div className="panel border-atlas-warning/40 bg-atlas-warning/5 rounded-2xl p-4 space-y-3" data-testid="health-run-warning">
                    <div className="flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-atlas-warning" /><span className="font-heading text-sm text-atlas-text">Run a full deep analysis?</span></div>
                    <div className="font-mono text-[10px] text-atlas-textSecondary leading-relaxed">
                        This replays every strategy across BTC · ETH · SOL on 1H · 30m · 15m. It runs in the background and can take <b>several minutes</b>. The dashboard keeps working while it computes. (No LLM credits — pure local compute.)
                    </div>
                    <div className="flex items-center gap-4 flex-wrap">
                        <div className="flex items-center gap-2">
                            <span className="label-tag">SCOPE</span>
                            {[{ k: "full", l: "All strategies" }, { k: "scoped", l: "Core + enabled" }].map((o) => (
                                <button key={o.k} data-testid={`health-scope-${o.k}`} onClick={() => setScope(o.k)}
                                    className={`rounded-lg border px-2.5 py-1.5 font-mono text-[10px] transition-colors ${scope === o.k ? "border-atlas-cyan text-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border text-atlas-textSecondary"}`}>{o.l}</button>
                            ))}
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="label-tag">WINDOW</span>
                            {PERIODS.map((p) => (
                                <button key={p.k} data-testid={`health-period-${p.k}`} onClick={() => setPeriod(p.k)}
                                    className={`rounded-lg border px-2.5 py-1.5 font-mono text-[10px] transition-colors ${period === p.k ? "border-atlas-cyan text-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border text-atlas-textSecondary"}`}>{p.l}</button>
                            ))}
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button data-testid="health-run-confirm" onClick={runSweep} disabled={busy}
                            className="flex items-center gap-1.5 rounded-lg bg-atlas-cyan text-atlas-bg px-4 py-2 font-mono text-[10px] tracking-widest font-bold hover:brightness-110 disabled:opacity-60 transition-all">
                            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />} YES, RUN IT
                        </button>
                        <button onClick={() => setShowRun(false)} className="rounded-lg border border-atlas-border px-4 py-2 font-mono text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text">CANCEL</button>
                    </div>
                </div>
            )}

            {/* active sweep progress */}
            {active && (
                <div className="panel border-atlas-cyan/40 bg-atlas-cyan/5 rounded-2xl p-4 space-y-2" data-testid="health-progress">
                    <div className="flex items-center gap-2"><Loader2 className="w-4 h-4 text-atlas-cyan animate-spin" /><span className="font-heading text-sm text-atlas-text">Analyzing strategies… <span className="font-mono text-[11px] text-atlas-textTertiary">({active.label === "daily" ? "scheduled" : "manual"} · runs in background)</span></span></div>
                    <div className="w-full h-2 rounded-full bg-atlas-panel overflow-hidden">
                        <div className="h-full bg-atlas-cyan rounded-full transition-all duration-500" style={{ width: `${Math.max(3, active.progress_pct || 0)}%` }} />
                    </div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary">{Math.round(active.progress_pct || 0)}% · you can leave this tab; results appear automatically.</div>
                </div>
            )}

            {/* content */}
            {loading ? (
                <div className="panel border-atlas-border rounded-2xl p-8 flex items-center justify-center gap-2 text-atlas-textTertiary" data-testid="health-loading">
                    <Loader2 className="w-4 h-4 animate-spin" /><span className="font-mono text-[11px]">Loading…</span>
                </div>
            ) : !data ? (
                <div className="panel border-atlas-border rounded-2xl p-8 text-center space-y-3" data-testid="health-empty">
                    <Activity className="w-8 h-8 text-atlas-textTertiary mx-auto" />
                    <div className="font-heading text-base text-atlas-text">No analysis yet</div>
                    <div className="font-mono text-[11px] text-atlas-textTertiary max-w-md mx-auto">A scoped analysis runs automatically each day. {isOwner ? "You can also run a full analysis now with the button above." : "Check back once the daily analysis has completed."}</div>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3" data-testid="health-cards">
                    {cards.map((c) => <HealthCard key={c.strategy} card={c} />)}
                </div>
            )}
        </div>
    );
}

function HealthCard({ card }) {
    const rec = card.recommendation || {};
    const badge = BADGE[rec.tone] || BADGE.negative;
    const Icon = badge.icon;
    const h = card.headline || {};
    const cr = card.capture_rate_pct;
    return (
        <div className="panel border-atlas-border rounded-xl p-4 space-y-3" data-testid={`health-card-${card.strategy}`}>
            <div className="flex items-start justify-between gap-2">
                <div className="font-heading text-sm text-atlas-text">{card.name}</div>
                <span className={`flex items-center gap-1 font-mono text-[9px] font-bold tracking-widest uppercase px-2 py-1 rounded-full border shrink-0 ${badge.cls}`} data-testid={`health-badge-${card.strategy}`}>
                    <Icon className="w-3 h-3" /> {rec.badge}
                </span>
            </div>
            {card.error ? (
                <div className="font-mono text-[10px] text-atlas-textTertiary">{rec.reason || card.error}</div>
            ) : (
                <>
                    <div className="font-mono text-[10px] text-atlas-textSecondary leading-relaxed">{rec.reason}</div>
                    <div className="grid grid-cols-2 gap-2">
                        <MiniStat icon={Clock} label="Best Timeframe" value={(card.best_timeframe || "—").toUpperCase()} />
                        <MiniStat icon={DoorOpen} label="Best Exit" value={card.best_exit || "—"} />
                    </div>
                    <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 font-mono text-[11px] border-t border-atlas-border/60 pt-2.5">
                        <Stat label="Return" value={fmtPct(h.total_return_pct)} cls={posCls(h.total_return_pct)} />
                        <Stat label="Win" value={`${Number(h.win_rate_pct ?? 0).toFixed(0)}%`} />
                        <Stat label="PF" value={fmtPf(h.profit_factor)} />
                        <Stat label="Max DD" value={`${Number(h.max_drawdown_pct ?? 0).toFixed(1)}%`} cls="text-atlas-negative" />
                        <Stat label="Trades" value={String(h.trades ?? 0)} />
                    </div>
                    {cr != null && (
                        <div data-testid={`health-capture-${card.strategy}`}>
                            <div className="flex items-center justify-between font-mono text-[9px] text-atlas-textTertiary mb-1">
                                <span className="flex items-center gap-1"><Gauge className="w-3 h-3" /> MFE CAPTURE</span>
                                <span>{cr.toFixed(0)}% · ${card.profit_left_usd} left on table</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-atlas-panel overflow-hidden">
                                <div className={`h-full rounded-full ${cr >= 60 ? "bg-atlas-positive" : cr < 40 ? "bg-atlas-negative" : "bg-atlas-warning"}`} style={{ width: `${Math.min(100, cr)}%` }} />
                            </div>
                        </div>
                    )}
                    <div className="flex items-center gap-2 flex-wrap text-[9px] font-mono">
                        {card.best_regime && <span className="flex items-center gap-1 px-2 py-1 rounded-full border border-atlas-positive/40 bg-atlas-positive/10 text-atlas-positive"><Award className="w-3 h-3" /> Best: {REGIME_LABELS[card.best_regime] || card.best_regime}</span>}
                        {card.weak_regime && card.weak_regime !== card.best_regime && <span className="px-2 py-1 rounded-full border border-atlas-negative/40 bg-atlas-negative/10 text-atlas-negative">Weak: {REGIME_LABELS[card.weak_regime] || card.weak_regime}</span>}
                    </div>
                </>
            )}
        </div>
    );
}

function MiniStat({ icon: Icon, label, value }) {
    return (
        <div className="rounded-lg border border-atlas-border px-2.5 py-2">
            <div className="flex items-center gap-1 text-atlas-textTertiary text-[9px] uppercase tracking-widest"><Icon className="w-3 h-3" /> {label}</div>
            <div className="font-heading text-[13px] text-atlas-text mt-0.5 truncate">{value}</div>
        </div>
    );
}

function Stat({ label, value, cls = "text-atlas-text" }) {
    return (<div><div className="text-atlas-textTertiary text-[9px] uppercase tracking-widest">{label}</div><div className={`font-bold tabular-nums ${cls}`}>{value}</div></div>);
}
