import { useEffect, useState } from "react";
import {
    Brain, Database, CalendarRange, ShieldCheck, Rocket, Loader2, Check,
    TrendingUp, ChevronRight, ChevronLeft, Dices, RotateCcw, Clock, Download,
    Award, Layers, Gauge, DoorOpen,
} from "lucide-react";
import { useResearchStore } from "@/lib/researchStore";
import { Switch } from "@/components/ui/switch";
import { downloadPdf } from "@/lib/pdfRegistry";

const PERIODS = [{ k: "1m", l: "1 Month" }, { k: "3m", l: "3 Months" }, { k: "6m", l: "6 Months" }, { k: "1y", l: "1 Year" }];
const TIMEFRAMES = [{ k: "1h", l: "1 Hour" }, { k: "30m", l: "30 Min" }, { k: "15m", l: "15 Min" }];
const STEPS = [
    { icon: Brain, label: "Strategy" }, { icon: Database, label: "Dataset" },
    { icon: CalendarRange, label: "Period" }, { icon: Clock, label: "Timeframe" },
    { icon: ShieldCheck, label: "Validation" }, { icon: Rocket, label: "Run" },
];

/** Guided, visual backtest+validation flow — Strategy → Dataset → Period → Validation → Run → Results. */
export default function ResearchWizard() {
    const {
        step, strategies, assets, strat, showAllStrat, picked, period, timeframes, runMC, exitMethods, useLive,
        phase, progress, runs, metrics,
        init, setStep, setShowAllStrat, setPeriod, toggleTimeframe, setRunMC, toggleExitMethod, setUseLive,
        toggleAsset, toggleStrat, run, reset,
    } = useResearchStore();

    useEffect(() => { init(); }, [init]);

    const canNext = (step === 0 && strat.length) || (step === 1 && picked.length) || step === 2 || step === 3 || step === 4;

    return (
        <div className="panel border-atlas-border rounded-2xl p-5" data-testid="research-wizard">
            {/* stepper header */}
            <div className="flex items-center justify-between mb-6 overflow-x-auto atlas-scroll">
                {STEPS.map((s, i) => {
                    const Icon = i < step ? Check : s.icon;
                    const state = i < step ? "done" : i === step ? "active" : "idle";
                    return (
                        <div key={s.label} className="flex items-center shrink-0">
                            <div className="flex flex-col items-center gap-1.5" data-testid={`wizard-step-${i}`}>
                                <span className={`w-9 h-9 rounded-full grid place-items-center border transition-colors ${
                                    state === "done" ? "border-atlas-cyan bg-atlas-cyan text-atlas-bg"
                                        : state === "active" ? "border-atlas-cyan text-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border text-atlas-textTertiary"}`}>
                                    <Icon className="w-4 h-4" />
                                </span>
                                <span className={`font-mono text-[9px] tracking-widest uppercase ${state === "idle" ? "text-atlas-textTertiary" : "text-atlas-text"}`}>{s.label}</span>
                            </div>
                            {i < STEPS.length - 1 && <div className={`w-8 md:w-14 h-px mx-1 ${i < step ? "bg-atlas-cyan" : "bg-atlas-border"}`} />}
                        </div>
                    );
                })}
            </div>

            {/* step body */}
            {phase !== "running" && phase !== "done" && (
                <div className="min-h-[180px]">
                    {step === 0 && (
                        <StepShell title="Choose strategies" hint="Tick one or more engines to validate together."
                            action={
                                <button data-testid="wizard-step0-next" onClick={() => setStep(1)} disabled={!strat.length}
                                    className="flex items-center gap-1.5 rounded-lg bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-4 py-2 disabled:opacity-40 transition-colors">
                                    NEXT <ChevronRight className="w-4 h-4" />
                                </button>
                            }>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" data-testid="wizard-strategies">
                                {(showAllStrat ? strategies : strategies.slice(0, 3)).map((s) => {
                                    const m = metrics[s.key];
                                    const on = !!m?.enabled && m?.status !== "DISABLED" && m?.status !== "ERROR";
                                    const checked = strat.includes(s.key);
                                    return (
                                        <button key={s.key} data-testid={`wizard-strat-${s.key}`} onClick={() => toggleStrat(s.key)}
                                            role="checkbox" aria-checked={checked}
                                            className={`panel border rounded-lg px-3 py-2.5 text-left transition-colors ${checked ? "border-atlas-cyan bg-atlas-cyan/5" : "border-atlas-border hover:border-atlas-textTertiary"}`}>
                                            <div className="flex items-center justify-between gap-2">
                                                <div className="font-heading text-[13px] text-atlas-text truncate">{s.name}</div>
                                                <span data-testid={`wizard-strat-check-${s.key}`}
                                                    className={`w-4 h-4 rounded grid place-items-center border shrink-0 transition-colors ${checked ? "bg-atlas-cyan border-atlas-cyan text-atlas-bg" : "border-atlas-textTertiary"}`}>
                                                    {checked && <Check className="w-3 h-3" />}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-1.5 mt-1" data-testid={`wizard-strat-status-${s.key}`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${on ? "bg-atlas-positive" : "bg-atlas-textTertiary"}`} />
                                                <span className={`font-mono text-[10px] font-bold ${on ? "text-atlas-positive" : "text-atlas-textTertiary"}`}>{on ? "ON · LIVE" : "OFF"}</span>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                            {strategies.length > 3 && (
                                <button data-testid="wizard-strat-load-more" onClick={() => setShowAllStrat((v) => !v)}
                                    className="mt-2 w-full rounded-lg border border-atlas-border py-2 font-mono text-[11px] text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors">
                                    {showAllStrat ? "Show less" : `Load more (${strategies.length - 3})`}
                                </button>
                            )}
                        </StepShell>
                    )}
                    {step === 1 && (
                        <StepShell title="Choose your dataset" hint="Pick the assets to test against.">
                            <div className="flex flex-wrap gap-2" data-testid="wizard-assets">
                                {assets.map((a) => (
                                    <button key={a} data-testid={`wizard-asset-${a.split("/")[0]}`} onClick={() => toggleAsset(a)}
                                        className={`rounded-lg border px-3 py-2 font-mono text-[11px] transition-colors ${picked.includes(a) ? "border-atlas-cyan text-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>
                                        {a.split("/")[0]}
                                    </button>
                                ))}
                                {assets.length === 0 && <span className="font-mono text-[11px] text-atlas-textTertiary">No cached market data available.</span>}
                            </div>
                        </StepShell>
                    )}
                    {step === 2 && (
                        <StepShell title="Choose a time period" hint="How far back should the backtest run?">
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="wizard-periods">
                                {PERIODS.map((p) => (
                                    <button key={p.k} data-testid={`wizard-period-${p.k}`} onClick={() => setPeriod(p.k)}
                                        className={`panel border rounded-xl p-4 text-center transition-colors ${period === p.k ? "border-atlas-cyan bg-atlas-cyan/5 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>
                                        <CalendarRange className="w-5 h-5 mx-auto mb-2" /><div className="font-heading text-sm">{p.l}</div>
                                    </button>
                                ))}
                            </div>
                        </StepShell>
                    )}
                    {step === 3 && (
                        <StepShell title="Choose timeframe(s)" hint="1H is the live default — add 30m/15m to compare side-by-side.">
                            <div className="grid grid-cols-3 gap-3" data-testid="wizard-timeframes">
                                {TIMEFRAMES.map((tf) => {
                                    const on = timeframes.includes(tf.k);
                                    return (
                                        <button key={tf.k} data-testid={`wizard-timeframe-${tf.k}`} onClick={() => toggleTimeframe(tf.k)}
                                            role="checkbox" aria-checked={on}
                                            className={`panel border rounded-xl p-4 text-center transition-colors relative ${on ? "border-atlas-cyan bg-atlas-cyan/5 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>
                                            <span className={`absolute top-2 right-2 w-4 h-4 rounded grid place-items-center border ${on ? "bg-atlas-cyan border-atlas-cyan text-atlas-bg" : "border-atlas-textTertiary"}`}>{on && <Check className="w-3 h-3" />}</span>
                                            <Clock className="w-5 h-5 mx-auto mb-2" /><div className="font-heading text-sm">{tf.l}</div>
                                            {tf.k === "1h" && <div className="font-mono text-[9px] text-atlas-textTertiary mt-1">DEFAULT</div>}
                                        </button>
                                    );
                                })}
                            </div>
                            <div className="font-mono text-[9px] text-atlas-textTertiary mt-1.5" data-testid="wizard-timeframe-hint">
                                {timeframes.length > 1 ? `${timeframes.join(" · ")} — results shown side-by-side per timeframe.` : "Single timeframe — tick another to compare side-by-side."}
                            </div>
                        </StepShell>
                    )}
                    {step === 4 && (
                        <StepShell title="Choose validation" hint="Backtest always runs. Keep live settings on to mirror paper/live, or override the exit to A/B test.">
                            <div className="space-y-3" data-testid="wizard-validations">
                                <label data-testid="wizard-use-live-toggle" className="panel border-atlas-cyan/40 bg-atlas-cyan/5 rounded-xl p-4 flex items-start gap-3 cursor-pointer">
                                    <Switch data-testid="wizard-use-live-switch" checked={useLive} onCheckedChange={setUseLive} className="mt-0.5" />
                                    <div className="min-w-0">
                                        <div className="font-heading text-sm text-atlas-text">Use my live settings</div>
                                        <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">
                                            {useLive
                                                ? "Replays through your deployed regimes, confidence & exit — the PDF matches paper/live."
                                                : "Manual override — pick an exit below to A/B test (live filters not applied)."}
                                        </div>
                                    </div>
                                </label>
                                <div className={useLive ? "opacity-40 pointer-events-none" : ""} aria-disabled={useLive} data-testid="wizard-exit-strategy-group">
                                    <div className="label-tag mb-2">EXIT STRATEGY</div>
                                    <div className="grid grid-cols-2 gap-3">
                                        {[{ k: "atr", t: "ATR Trailing", d: "Volatility-adaptive trailing stop (default)" }, { k: "fixed", t: "Fixed Target", d: "Fixed $ profit target / stop loss" }].map((em) => {
                                            const on = exitMethods.includes(em.k);
                                            return (
                                                <button key={em.k} data-testid={`wizard-exit-${em.k}`} onClick={() => toggleExitMethod(em.k)}
                                                    className={`panel border rounded-xl p-3.5 flex items-start gap-2.5 text-left transition-colors ${on ? "border-atlas-cyan bg-atlas-cyan/5" : "border-atlas-border hover:border-atlas-textTertiary"}`}>
                                                    <span className={`mt-0.5 w-4 h-4 rounded grid place-items-center border shrink-0 ${on ? "bg-atlas-cyan border-atlas-cyan text-atlas-bg" : "border-atlas-textTertiary"}`}>{on && <Check className="w-3 h-3" />}</span>
                                                    <div><div className="font-heading text-[13px] text-atlas-text">{em.t}</div><div className="font-mono text-[9px] text-atlas-textTertiary mt-0.5">{em.d}</div></div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                    <div className="font-mono text-[9px] text-atlas-textTertiary mt-1.5">{exitMethods.length === 2 ? "Both selected — Ananta runs and reports each exit separately." : "Tick both to compare exits side-by-side."}</div>
                                </div>
                                <label className="panel border-atlas-cyan/40 bg-atlas-cyan/5 rounded-xl p-4 flex items-center gap-3 opacity-90">
                                    <span className="w-5 h-5 rounded grid place-items-center bg-atlas-cyan text-atlas-bg"><Check className="w-3.5 h-3.5" /></span>
                                    <div><div className="font-heading text-sm text-atlas-text">Historical Backtest</div><div className="font-mono text-[10px] text-atlas-textTertiary">Always included</div></div>
                                </label>
                                <button data-testid="wizard-toggle-mc" onClick={() => setRunMC((v) => !v)}
                                    className={`w-full panel border rounded-xl p-4 flex items-center gap-3 text-left transition-colors ${runMC ? "border-atlas-cyan bg-atlas-cyan/5" : "border-atlas-border"}`}>
                                    <span className={`w-5 h-5 rounded grid place-items-center border ${runMC ? "bg-atlas-cyan text-atlas-bg border-atlas-cyan" : "border-atlas-border"}`}>{runMC && <Check className="w-3.5 h-3.5" />}</span>
                                    <Dices className="w-5 h-5 text-atlas-cyan" />
                                    <div><div className="font-heading text-sm text-atlas-text">Monte Carlo Stress-Test</div><div className="font-mono text-[10px] text-atlas-textTertiary">Risk-of-ruin & drawdown distribution</div></div>
                                </button>
                            </div>
                        </StepShell>
                    )}
                </div>
            )}

            {/* running */}
            {phase === "running" && (
                <div className="min-h-[180px] flex flex-col items-center justify-center gap-4 py-8" data-testid="wizard-running">
                    <Loader2 className="w-8 h-8 text-atlas-cyan animate-spin" />
                    <div className="font-heading text-lg text-atlas-text">Running backtest…</div>
                    <div className="w-full max-w-md h-2 rounded-full bg-atlas-panel overflow-hidden">
                        <div className="h-full bg-atlas-cyan rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
                    </div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary">{strat.join(", ")} · {picked.map((p) => p.split("/")[0]).join(", ")} · {period} · {timeframes.join(" · ")} · {useLive ? "LIVE SETTINGS" : `${exitMethods.map((m) => m.toUpperCase()).join(" + ")} exit`}</div>
                    <button data-testid="wizard-new-run" onClick={reset}
                        className="flex items-center gap-1.5 rounded-lg border border-atlas-border px-4 py-2 font-mono text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors">
                        <RotateCcw className="w-3.5 h-3.5" /> NEW RUN
                    </button>
                </div>
            )}

            {/* results */}
            {phase === "done" && runs.length > 0 && (
                <div className="space-y-6" data-testid="wizard-results">
                    <div className="flex items-center justify-between flex-wrap gap-3">
                        <div className="flex items-center gap-2"><TrendingUp className="w-5 h-5 text-atlas-cyan" /><span className="font-heading text-lg text-atlas-text">Results</span></div>
                        <button data-testid="wizard-restart" onClick={reset} className="flex items-center gap-1.5 rounded-lg border border-atlas-border px-3 py-1.5 font-mono text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text"><RotateCcw className="w-3.5 h-3.5" />NEW RUN</button>
                    </div>
                    {runs.map((r) => <Results key={r.method} runItem={r} showLabel={runs.length > 1} />)}
                </div>
            )}
            {phase === "error" && (
                <div className="min-h-[120px] flex flex-col items-center justify-center gap-3 py-6" data-testid="wizard-error">
                    <div className="font-heading text-base text-atlas-negative">Backtest failed.</div>
                    <button onClick={reset} className="rounded-lg border border-atlas-border px-4 py-2 font-mono text-[11px] text-atlas-textSecondary hover:text-atlas-text"><RotateCcw className="w-3.5 h-3.5 inline mr-1.5" />Start over</button>
                </div>
            )}

            {/* nav */}
            {phase !== "running" && phase !== "done" && (
                <div className="flex items-center justify-between mt-6 pt-4 border-t border-atlas-border">
                    <button data-testid="wizard-back" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}
                        className="flex items-center gap-1.5 font-mono text-[11px] tracking-widest text-atlas-textSecondary hover:text-atlas-text disabled:opacity-30">
                        <ChevronLeft className="w-4 h-4" /> BACK
                    </button>
                    {step < 4 ? (
                        <button data-testid="wizard-next" onClick={() => setStep((s) => s + 1)} disabled={!canNext}
                            className="flex items-center gap-1.5 rounded-lg bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-5 py-2.5 disabled:opacity-40 transition-colors">
                            NEXT <ChevronRight className="w-4 h-4" />
                        </button>
                    ) : (
                        <button data-testid="wizard-run" onClick={run} disabled={!picked.length}
                            className="flex items-center gap-2 rounded-lg bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-5 py-2.5 disabled:opacity-40 transition-colors">
                            <Rocket className="w-4 h-4" /> RUN VALIDATION
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

function StepShell({ title, hint, action, children }) {
    return (
        <div>
            <div className="mb-4 flex items-start justify-between gap-3">
                <div><div className="font-heading text-lg text-atlas-text">{title}</div><div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">{hint}</div></div>
                {action}
            </div>
            {children}
        </div>
    );
}

function DownloadPdfButton({ runItem }) {
    const [prog, setProg] = useState(null); // null idle | "prep" | 0-100
    const busy = prog !== null;
    const onClick = async () => {
        setProg("prep");
        try {
            await downloadPdf(runItem.url, `Research_${runItem.method}_report.pdf`, (pct) => setProg(pct == null ? "prep" : pct));
        } catch { /* toast handled by caller */ }
        finally { setProg(null); }
    };
    return (
        <button data-testid={`wizard-download-pdf-${runItem.method}`} onClick={onClick} disabled={busy}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-atlas-cyan/50 bg-atlas-cyan/10 px-3 py-1.5 font-mono text-[10px] tracking-widest font-bold text-atlas-cyan hover:bg-atlas-cyan/20 disabled:opacity-60 transition-colors">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            {busy ? (prog === "prep" ? "PREPARING…" : `${prog}%`) : "DOWNLOAD PDF"}
        </button>
    );
}

const REGIME_LABELS = {
    TREND_UP: "Trend Up", TREND_DOWN: "Trend Down", REVERSAL: "Reversal",
    COMPRESSION: "Compression", RANGE: "Range", NEUTRAL: "Neutral", "—": "Unclassified",
};
const EXIT_MODULE_LABELS = {
    ATR: "ATR Trailing", FIXED_TP: "Fixed Target (TP)", FIXED_SL: "Fixed Stop (SL)",
    A: "Structural / Hard Stop", B: "Momentum Exhaustion", C: "ATR Trail (Universal)",
    D: "EMA / Trend Break", E: "Time Stop", F: "Profit Protection", S: "Breakeven / Structure",
    KILL: "Kill-Switch", EOD: "End of Window", DECL: "Strategy Exit", "—": "Unclassified",
};
const TF_ORDER = ["1h", "30m", "15m"];

const fmtPct = (x, d = 1) => { const n = Number(x); return isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(d)}%` : "—"; };
const fmtPf = (x) => (x == null ? "—" : (x >= 999 ? "∞" : Number(x).toFixed(2)));
const posCls = (x) => (Number(x) >= 0 ? "text-atlas-positive" : "text-atlas-negative");

/** Synthesize a one-glance verdict from the (already-computed) backend analytics. */
function buildVerdict(result) {
    const per = result?.per_symbol || {};
    const syms = Object.entries(per).filter(([, m]) => !m.error);
    const regAgg = {};
    syms.forEach(([, m]) => Object.entries(m.regime_breakdown || {}).forEach(([r, val]) => {
        if (r === "—") return;
        (regAgg[r] || (regAgg[r] = { net: 0 })).net += val.net_pnl || 0;
    }));
    const regRows = Object.entries(regAgg);
    let bestRegime = null, weakRegime = null;
    if (regRows.length) {
        const sorted = [...regRows].sort((a, b) => b[1].net - a[1].net);
        bestRegime = sorted[0][0];
        if (sorted.length > 1) weakRegime = sorted[sorted.length - 1][0];
    }
    const firstMtf = Object.values(result?.multi_timeframe || {})[0];
    const bestTf = firstMtf?.verdict?.best_tf || null;
    const firstEc = Object.values(result?.exit_comparison || {})[0];
    let recExit = null;
    if (firstEc) {
        const b = firstEc["1h"] || Object.values(firstEc)[0];
        const wk = b?.winner_key;
        if (wk) recExit = b.rows?.[wk]?.label || wk;
    }
    return { bestTf, bestRegime, weakRegime, recExit };
}

/** Generic compact metrics table. Cells are strings or {v, cls}. */
function MiniTable({ head, rows, testid }) {
    if (!rows.length) return null;
    return (
        <div className="overflow-x-auto atlas-scroll" data-testid={testid}>
            <table className="w-full text-left font-mono text-[11px]">
                <thead>
                    <tr className="text-atlas-textTertiary">
                        {head.map((h, i) => (
                            <th key={i} className={`py-1.5 pr-3 font-normal uppercase tracking-widest text-[9px] ${i > 0 ? "text-right" : ""}`}>{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, ri) => (
                        <tr key={ri} className="border-t border-atlas-border/60">
                            {r.map((c, ci) => {
                                const cell = c && typeof c === "object" ? c : { v: c };
                                return (
                                    <td key={ci} className={`py-1.5 pr-3 ${ci > 0 ? "text-right tabular-nums" : "text-atlas-text"} ${cell.cls || (ci > 0 ? "text-atlas-textSecondary" : "")}`}>
                                        {cell.v ?? "—"}
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function AnalyticsSection({ icon: Icon, title, hint, children, testid }) {
    return (
        <div className="panel border-atlas-border rounded-xl p-4 space-y-2" data-testid={testid}>
            <div className="flex items-center gap-2"><Icon className="w-4 h-4 text-atlas-cyan" /><span className="label-tag">{title}</span></div>
            {hint && <div className="font-mono text-[9px] text-atlas-textTertiary leading-relaxed">{hint}</div>}
            {children}
        </div>
    );
}

function CaptureCard({ cap }) {
    const cr = cap?.capture_rate_pct;
    if (!cap || cr == null) return null;
    const read = cr >= 60 ? "Exits are banking most of the available move."
        : cr < 40 ? "Exits give back a lot of open profit — try a wider trail or structural exit."
            : "Capture is moderate — test tighter/looser trails to compare.";
    return (
        <AnalyticsSection icon={Gauge} title="MFE / MAE CAPTURE" testid="wizard-capture-card"
            hint="How much of the maximum favourable move the exits actually banked vs. left on the table.">
            <div className="flex items-end gap-3 flex-wrap">
                <div><div className="text-atlas-textTertiary text-[9px] uppercase tracking-widest">Capture Rate</div>
                    <div className={`font-bold text-2xl tabular-nums ${cr >= 60 ? "text-atlas-positive" : cr < 40 ? "text-atlas-negative" : "text-atlas-warning"}`}>{cr.toFixed(0)}%</div></div>
                <div className="h-2 flex-1 min-w-[120px] rounded-full bg-atlas-panel overflow-hidden mb-2">
                    <div className={`h-full rounded-full ${cr >= 60 ? "bg-atlas-positive" : cr < 40 ? "bg-atlas-negative" : "bg-atlas-warning"}`} style={{ width: `${Math.min(100, cr)}%` }} />
                </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-[11px] pt-1">
                <Stat label="Total MFE" value={cap.total_mfe_usd != null ? `$${cap.total_mfe_usd}` : "—"} />
                <Stat label="Captured" value={cap.total_captured_usd != null ? `$${cap.total_captured_usd}` : "—"} cls="text-atlas-positive" />
                <Stat label="Left on Table" value={cap.total_profit_left_usd != null ? `$${cap.total_profit_left_usd}` : "—"} cls="text-atlas-warning" />
                <Stat label="Avg MAE" value={fmtPct(cap.avg_mae_pct)} cls="text-atlas-negative" />
            </div>
            <div className="font-mono text-[9px] text-atlas-textTertiary pt-1">{read}</div>
        </AnalyticsSection>
    );
}

function BreakdownTable({ icon, title, hint, keyLabel, data, labelMap, testid }) {
    const entries = Object.entries(data || {}).filter(([k]) => k !== "—" || Object.keys(data).length === 1);
    if (!entries.length) return null;
    const rows = entries
        .sort((a, b) => (b[1].net_pnl || 0) - (a[1].net_pnl || 0))
        .map(([k, v]) => [
            (labelMap?.[k] || k),
            String(v.n),
            `${Number(v.win_pct ?? 0).toFixed(0)}%`,
            fmtPf(v.profit_factor),
            { v: fmtPct(v.avg_return_pct), cls: posCls(v.avg_return_pct) },
            { v: `$${Number(v.net_pnl ?? 0).toFixed(2)}`, cls: posCls(v.net_pnl) },
        ]);
    return (
        <AnalyticsSection icon={icon} title={title} hint={hint} testid={testid}>
            <MiniTable head={[keyLabel, "N", "Win%", "PF", "Avg Ret", "Net P&L"]} rows={rows} testid={`${testid}-table`} />
        </AnalyticsSection>
    );
}

function MultiTfBlock({ mtf, selectedTfs }) {
    const rowsBySym = Object.entries(mtf || {});
    if (!rowsBySym.length) return null;
    // only render when there is more than one timeframe to compare
    const anyMulti = rowsBySym.some(([, e]) => Object.keys(e.by_tf || {}).length > 1);
    if (!anyMulti) return null;
    const wanted = TF_ORDER.filter((t) => !selectedTfs || selectedTfs.includes(t));
    return (
        <AnalyticsSection icon={Layers} title="MULTI-TIMEFRAME COMPARISON" testid="wizard-multitf"
            hint="Identical window, settings and exit rules replayed per candle size. Compare trade frequency vs. return/drawdown to see which timeframe the edge favours.">
            {rowsBySym.map(([sym, entry]) => {
                const byTf = entry.by_tf || {};
                const tfs = wanted.filter((t) => byTf[t]);
                const rows = tfs.map((tf) => {
                    const m = byTf[tf] || {};
                    if (m.error) return [tf.toUpperCase(), "—", { v: m.error }, "—", "—", "—"];
                    return [
                        tf.toUpperCase(), String(m.trades ?? 0),
                        { v: fmtPct(m.total_return_pct), cls: posCls(m.total_return_pct) },
                        `${Number(m.win_rate_pct ?? 0).toFixed(0)}%`,
                        { v: fmtPct(m.max_drawdown_pct), cls: "text-atlas-negative" },
                        fmtPct(m.avg_mfe_pct),
                    ];
                });
                return (
                    <div key={sym} className="space-y-1.5" data-testid={`wizard-multitf-${sym.split("/")[0]}`}>
                        <div className="font-heading text-[13px] text-atlas-text">{sym.split("/")[0]}</div>
                        <MiniTable head={["TF", "Trades", "Return", "Win%", "Max DD", "Avg MFE"]} rows={rows} />
                        {entry.verdict?.reason && (
                            <div className="font-mono text-[9px] text-atlas-textSecondary">Best: <span className="text-atlas-cyan font-bold">{(entry.verdict.best_tf || "—").toUpperCase()}</span> — {entry.verdict.reason}</div>
                        )}
                    </div>
                );
            })}
        </AnalyticsSection>
    );
}

function ExitComparisonBlock({ exitCmp }) {
    const bySym = Object.entries(exitCmp || {});
    if (!bySym.length) return null;
    return (
        <AnalyticsSection icon={DoorOpen} title="EXIT ENGINE COMPARISON (WHAT-IF)" testid="wizard-exit-comparison"
            hint="Every exit config is replayed on the EXACT same entry signals — a true A/B/C test. ★ = best by return-over-drawdown.">
            {bySym.map(([sym, byTf]) => {
                const tf = byTf["1h"] ? "1h" : Object.keys(byTf)[0];
                const block = byTf[tf] || {};
                if (block.error || !block.rows) return <div key={sym} className="font-mono text-[10px] text-atlas-textTertiary">{sym.split("/")[0]}: no comparison data.</div>;
                const winner = block.winner_key;
                const order = (block.configs || []).map((c) => c.key).filter((k) => block.rows[k]);
                const rows = (order.length ? order : Object.keys(block.rows)).map((k) => {
                    const m = block.rows[k] || {};
                    const name = (m.label || k) + (winner === k ? "  ★" : "");
                    if (m.error) return [{ v: name }, { v: m.error }, "—", "—", "—", "—"];
                    return [
                        { v: name, cls: winner === k ? "text-atlas-cyan font-bold" : "text-atlas-text" },
                        fmtPf(m.profit_factor),
                        `${Number(m.win_rate_pct ?? 0).toFixed(0)}%`,
                        m.expectancy_usd != null ? `$${Number(m.expectancy_usd).toFixed(2)}` : "—",
                        { v: fmtPct(m.total_return_pct), cls: posCls(m.total_return_pct) },
                        { v: fmtPct(m.max_drawdown_pct), cls: "text-atlas-negative" },
                    ];
                });
                return (
                    <div key={sym} className="space-y-1.5" data-testid={`wizard-exitcmp-${sym.split("/")[0]}`}>
                        <div className="font-heading text-[13px] text-atlas-text">{sym.split("/")[0]} · {tf.toUpperCase()} <span className="font-mono text-[9px] text-atlas-textTertiary">· {block.entries ?? "—"} identical entries</span></div>
                        <MiniTable head={["Exit config", "PF", "Win%", "Expect.", "Return", "Max DD"]} rows={rows} />
                    </div>
                );
            })}
        </AnalyticsSection>
    );
}

function SummaryVerdict({ v, verdict }) {
    const parts = [];
    if (v.bestTf) parts.push(`best on ${v.bestTf.toUpperCase()}`);
    if (v.bestRegime) parts.push(`strongest in ${REGIME_LABELS[v.bestRegime] || v.bestRegime}`);
    if (v.weakRegime && v.weakRegime !== v.bestRegime) parts.push(`weakest in ${REGIME_LABELS[v.weakRegime] || v.weakRegime}`);
    const sentence = parts.length ? `Strategy performed ${parts.join(" · ")}.` : "Not enough data yet for a regime / timeframe read — widen the window or add assets.";
    return (
        <div className="panel border-atlas-cyan/40 bg-atlas-cyan/5 rounded-xl p-4" data-testid="wizard-summary-verdict">
            <div className="flex items-center gap-2 mb-2">
                <Award className="w-4 h-4 text-atlas-cyan" /><span className="label-tag">SUMMARY VERDICT</span>
                <span className={`font-mono text-[10px] font-bold tracking-widest ${verdict.cls}`}>{verdict.t}</span>
            </div>
            <div className="font-heading text-sm text-atlas-text leading-relaxed">{sentence}</div>
            {v.recExit && <div className="font-mono text-[10px] text-atlas-textSecondary mt-1.5">Recommended exit: <span className="text-atlas-cyan font-bold">{v.recExit}</span></div>}
        </div>
    );
}

function Results({ runItem, showLabel }) {
    const { result, mc, label, selectedTfs } = runItem;
    const per = result?.per_symbol || {};
    const rows = Object.entries(per).filter(([, m]) => !m.error);
    const avg = (k) => rows.length ? rows.reduce((a, [, m]) => a + (Number(m[k]) || 0), 0) / rows.length : 0;
    const pf = avg("profit_factor"), ret = avg("total_return_pct");
    const verdict = pf >= 1.5 && ret > 0 ? { t: "ROBUST", cls: "text-atlas-positive" } : pf >= 1.0 ? { t: "MARGINAL", cls: "text-atlas-warning" } : { t: "WEAK", cls: "text-atlas-negative" };
    const v = buildVerdict(result);
    return (
        <div className="space-y-4" data-testid={`wizard-result-block-${runItem.method}`}>
            <div className="flex items-center gap-2 flex-wrap">
                {showLabel && <span className="font-mono text-[10px] font-bold tracking-widest uppercase px-2.5 py-1 rounded-full border border-atlas-cyan/40 bg-atlas-cyan/10 text-atlas-cyan" data-testid={`wizard-result-exit-${runItem.method}`}>{label} Exit</span>}
                <span className={`font-mono text-[11px] font-bold tracking-widest ${verdict.cls}`}>· {verdict.t}</span>
                <DownloadPdfButton runItem={runItem} />
            </div>

            <SummaryVerdict v={v} verdict={verdict} />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="wizard-result-cards">
                {rows.map(([sym, m]) => (
                    <div key={sym} className="panel border-atlas-border rounded-xl p-4" data-testid={`wizard-result-${sym.split("/")[0]}`}>
                        <div className="font-heading text-sm text-atlas-text mb-2">{sym.split("/")[0]}</div>
                        <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                            <Stat label="Return" value={fmtPct(m.total_return_pct)} cls={posCls(m.total_return_pct)} />
                            <Stat label="Win Rate" value={`${Number(m.win_rate_pct ?? 0).toFixed(0)}%`} />
                            <Stat label="Profit Factor" value={fmtPf(m.profit_factor)} />
                            <Stat label="Max DD" value={`${Number(m.max_drawdown_pct ?? 0).toFixed(1)}%`} cls="text-atlas-negative" />
                        </div>
                    </div>
                ))}
            </div>

            {/* Deep analytics — computed backend-side, surfaced per symbol. */}
            {rows.map(([sym, m]) => (
                <div key={`ax-${sym}`} className="space-y-3" data-testid={`wizard-analytics-${sym.split("/")[0]}`}>
                    {rows.length > 1 && <div className="label-tag text-atlas-textSecondary">{sym.split("/")[0]}</div>}
                    <CaptureCard cap={m.capture_stats} />
                    <BreakdownTable icon={DoorOpen} title="EXIT MODULE PERFORMANCE" keyLabel="Exit module"
                        hint="Which exit actually closed each trade, and how each performed."
                        data={m.exit_module_breakdown} labelMap={EXIT_MODULE_LABELS} testid={`wizard-exitmodule-${sym.split("/")[0]}`} />
                    <BreakdownTable icon={Gauge} title="REGIME BREAKDOWN" keyLabel="Regime"
                        hint="Performance split by the market regime at entry — exactly which conditions the strategy makes or loses money in."
                        data={m.regime_breakdown} labelMap={REGIME_LABELS} testid={`wizard-regime-${sym.split("/")[0]}`} />
                </div>
            ))}

            <MultiTfBlock mtf={result?.multi_timeframe} selectedTfs={selectedTfs} />
            <ExitComparisonBlock exitCmp={result?.exit_comparison} />

            {mc && (
                <div className="panel border-atlas-border rounded-xl p-4" data-testid="wizard-mc-result">
                    <div className="flex items-center gap-2 mb-2"><Dices className="w-4 h-4 text-atlas-cyan" /><span className="label-tag">MONTE CARLO</span>
                        <span className={`font-mono text-[10px] font-bold ${mc.verdict === "ROBUST" ? "text-atlas-positive" : mc.verdict === "ACCEPTABLE" ? "text-atlas-warning" : "text-atlas-negative"}`}>{mc.verdict}</span></div>
                    <div className="font-mono text-[11px] text-atlas-textSecondary">Risk of ruin: <span className="text-atlas-text font-bold">{(mc.risk_of_ruin_pct ?? mc.ruin_probability_pct ?? 0)}%</span> · median drawdown {Number(mc.median_max_drawdown_pct ?? mc.p50_max_drawdown_pct ?? 0).toFixed(1)}%</div>
                </div>
            )}
        </div>
    );
}

function Stat({ label, value, cls = "text-atlas-text" }) {
    return (<div><div className="text-atlas-textTertiary text-[9px] uppercase tracking-widest">{label}</div><div className={`font-bold tabular-nums ${cls}`}>{value}</div></div>);
}
