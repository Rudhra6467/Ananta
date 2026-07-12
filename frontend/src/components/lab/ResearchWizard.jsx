import { useEffect } from "react";
import {
    Brain, Database, CalendarRange, ShieldCheck, Rocket, Loader2, Check,
    TrendingUp, ChevronRight, ChevronLeft, Dices, RotateCcw, Clock,
} from "lucide-react";
import { useResearchStore } from "@/lib/researchStore";

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
        step, strategies, assets, strat, showAllStrat, picked, period, timeframe, runMC,
        phase, progress, result, mc, metrics,
        init, setStep, setShowAllStrat, setPeriod, setTimeframe, setRunMC,
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
                        <StepShell title="Choose strategies" hint="Tick one or more engines to validate together.">
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
                        <StepShell title="Choose a timeframe" hint="Candle size the engine replays on. 1H is the live default; 30m/15m react faster.">
                            <div className="grid grid-cols-3 gap-3" data-testid="wizard-timeframes">
                                {TIMEFRAMES.map((tf) => (
                                    <button key={tf.k} data-testid={`wizard-timeframe-${tf.k}`} onClick={() => setTimeframe(tf.k)}
                                        className={`panel border rounded-xl p-4 text-center transition-colors ${timeframe === tf.k ? "border-atlas-cyan bg-atlas-cyan/5 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>
                                        <Clock className="w-5 h-5 mx-auto mb-2" /><div className="font-heading text-sm">{tf.l}</div>
                                        {tf.k === "1h" && <div className="font-mono text-[9px] text-atlas-textTertiary mt-1">DEFAULT</div>}
                                    </button>
                                ))}
                            </div>
                        </StepShell>
                    )}
                    {step === 4 && (
                        <StepShell title="Choose validation" hint="Backtest runs by default. Add Monte Carlo for a robustness stress-test.">
                            <div className="space-y-3" data-testid="wizard-validations">
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
                    <div className="font-mono text-[10px] text-atlas-textTertiary">{strat.join(", ")} · {picked.map((p) => p.split("/")[0]).join(", ")} · {period} · {timeframe}</div>
                    <button data-testid="wizard-new-run" onClick={reset}
                        className="flex items-center gap-1.5 rounded-lg border border-atlas-border px-4 py-2 font-mono text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors">
                        <RotateCcw className="w-3.5 h-3.5" /> NEW RUN
                    </button>
                </div>
            )}

            {/* results */}
            {phase === "done" && result && <Results result={result} mc={mc} onReset={reset} />}
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

function StepShell({ title, hint, children }) {
    return (
        <div>
            <div className="mb-4"><div className="font-heading text-lg text-atlas-text">{title}</div><div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">{hint}</div></div>
            {children}
        </div>
    );
}

function Results({ result, mc, onReset }) {
    const per = result?.per_symbol || {};
    const rows = Object.entries(per).filter(([, m]) => !m.error);
    const avg = (k) => rows.length ? rows.reduce((a, [, m]) => a + (Number(m[k]) || 0), 0) / rows.length : 0;
    const pf = avg("profit_factor"), ret = avg("total_return_pct");
    const verdict = pf >= 1.5 && ret > 0 ? { t: "ROBUST", cls: "text-atlas-positive" } : pf >= 1.0 ? { t: "MARGINAL", cls: "text-atlas-warning" } : { t: "WEAK", cls: "text-atlas-negative" };
    return (
        <div className="space-y-4" data-testid="wizard-results">
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-2"><TrendingUp className="w-5 h-5 text-atlas-cyan" /><span className="font-heading text-lg text-atlas-text">Results</span>
                    <span className={`font-mono text-[11px] font-bold tracking-widest ${verdict.cls}`}>· {verdict.t}</span></div>
                <button data-testid="wizard-restart" onClick={onReset} className="flex items-center gap-1.5 rounded-lg border border-atlas-border px-3 py-1.5 font-mono text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text"><RotateCcw className="w-3.5 h-3.5" />NEW RUN</button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="wizard-result-cards">
                {rows.map(([sym, m]) => (
                    <div key={sym} className="panel border-atlas-border rounded-xl p-4" data-testid={`wizard-result-${sym.split("/")[0]}`}>
                        <div className="font-heading text-sm text-atlas-text mb-2">{sym.split("/")[0]}</div>
                        <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                            <Stat label="Return" value={`${(m.total_return_pct ?? 0) >= 0 ? "+" : ""}${Number(m.total_return_pct ?? 0).toFixed(1)}%`} cls={(m.total_return_pct ?? 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative"} />
                            <Stat label="Win Rate" value={`${Number(m.win_rate_pct ?? 0).toFixed(0)}%`} />
                            <Stat label="Profit Factor" value={Number(m.profit_factor ?? 0).toFixed(2)} />
                            <Stat label="Max DD" value={`${Number(m.max_drawdown_pct ?? 0).toFixed(1)}%`} cls="text-atlas-negative" />
                        </div>
                    </div>
                ))}
            </div>
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
