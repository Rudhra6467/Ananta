import { useEffect, useRef, useState } from "react";
import {
    Target, Activity, GitBranch, ShieldCheck, PieChart, TrendingDown, Clock, Wind,
    Layers, Coins, Globe, ChevronRight, Loader2, Play, Rocket, CheckCircle2, FlaskConical, ArrowLeft,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"];
const CORE = ["hunter", "squeeze", "continuation"];

const SCOPES = [
    { id: "strategy", name: "Modify Exit for a Strategy", desc: "Apply this exit to one alpha model (Hunter / Squeeze / Continuation).", icon: Layers },
    { id: "coin", name: "Modify Exit for a Specific Coin", desc: "Override the exit for a single market, e.g. BTC/USD.", icon: Coins },
    { id: "global", name: "Modify Global Exit", desc: "Applies to everything — the default exit for all strategies and coins.", icon: Globe },
];

// engine = backend exit_method used for the REAL backtest ("fixed" | "atr" | "native")
const METHODS = [
    { id: "fixed_pct", name: "Fixed % Target + Stop", desc: "Simple target and stop. Best for beginners and clear risk-reward.", icon: Target, engine: "fixed" },
    { id: "atr_trailing", name: "ATR Trailing Stop", desc: "Volatility-based trailing. Good for trending markets.", icon: Activity, engine: "atr" },
    { id: "structural_trail", name: "Structural Stop + Trail", desc: "Based on swing low/high. Best for Hunter and pullback styles.", icon: GitBranch, engine: "native" },
    { id: "breakeven_trail", name: "Breakeven + Trail", desc: "Moves stop to breakeven after profit. Protects winners.", icon: ShieldCheck, engine: "native" },
    { id: "partial_profit", name: "Partial Profit Taking", desc: "Take 40-50% at target and trail the rest.", icon: PieChart, engine: "native" },
    { id: "momentum_exhaustion", name: "Momentum Exhaustion", desc: "Exit when momentum dies. Avoids giving back profits.", icon: TrendingDown, engine: "native" },
    { id: "time_based", name: "Time-Based Exit", desc: "Exit after a set number of hours / candles. Capital efficiency.", icon: Clock, engine: "native" },
    { id: "chandelier", name: "Chandelier Exit", desc: "Classic volatility trail. Works well in strong trends.", icon: Wind, engine: "atr" },
];

const ENGINE_LABEL = { fixed: "Fixed $ target engine", atr: "ATR trailing engine", native: "Universal Exit Engine (modules A-F)" };
const DEFAULTS = {
    fixed_pct: { target_pct: 3.0, stop_pct: 2.2 },
    atr_trailing: { atr_mult: 2.5, atr_period: 14, trail_arm: 1.6, trail_dist: 2.0 },
    structural_trail: { trail_atr_mult: 2.0, profit_arm_pct: 3.0 },
    breakeven_trail: { breakeven_r: 1.0, profit_arm_pct: 3.0 },
    partial_profit: { profit_arm_pct: 3.0 },
    momentum_exhaustion: {},
    time_based: { time_exit_hours: 48 },
    chandelier: { atr_period: 22, atr_mult: 3.0 },
};

export default function ExitEngineWorkflow() {
    const { isOwner } = useAuth();
    const [step, setStep] = useState(1);
    const [scope, setScope] = useState(null);
    const [strategy, setStrategy] = useState("hunter");
    const [coin, setCoin] = useState("BTC/USD");
    const [method, setMethod] = useState(null);
    const [cfg, setCfg] = useState({});
    const [testing, setTesting] = useState(false);
    const [deploying, setDeploying] = useState(false);
    const [result, setResult] = useState(null);
    const pollRef = useRef(null);

    useEffect(() => () => clearInterval(pollRef.current), []);

    const pick = (m) => { setMethod(m); setCfg({ ...DEFAULTS[m.id] }); setResult(null); setStep(3); };
    const reset = () => { setStep(1); setScope(null); setMethod(null); setResult(null); };
    const setF = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

    const buildSpec = () => {
        const spec = { kind: "backtest", symbols: SYMBOLS, period: "3m", timeframe: "1h",
            strategies: scope === "strategy" ? [strategy] : CORE, exit_method: method.engine };
        if (method.engine === "fixed") {
            const lot = 75;
            spec.target_profit = +(lot * (cfg.target_pct / 100)).toFixed(2);
            spec.target_loss = +(lot * (cfg.stop_pct / 100)).toFixed(2);
        } else if (method.engine === "atr") {
            spec.atr_params = {
                multiplier: cfg.atr_mult, period: cfg.atr_period || 14,
                trail_activation_pct: cfg.trail_arm ?? 3.0, trail_distance: cfg.trail_dist ?? 2.0,
            };
        }
        return spec;
    };

    const runTest = async () => {
        if (!isOwner) { toast.error("Owner login required to run a backtest"); return; }
        setTesting(true); setResult(null);
        try {
            const { id } = await api.labCreateRun(buildSpec());
            toast.info("Running historical backtest on 3 assets (3-month window)…");
            pollRef.current = setInterval(async () => {
                try {
                    const run = await api.labRun(id);
                    if (run.status === "DONE" || run.status === "ERROR") {
                        clearInterval(pollRef.current);
                        setTesting(false);
                        if (run.status === "ERROR") { toast.error("Backtest failed", { description: run.error || "" }); return; }
                        setResult(run.result || {});
                        toast.success("Backtest complete — see performance + What-If below.");
                    }
                } catch { /* keep polling */ }
            }, 2500);
        } catch (e) {
            setTesting(false);
            toast.error("Could not start backtest", { description: String(e?.response?.data?.detail || e?.message) });
        }
    };

    const deploy = async () => {
        if (!isOwner) { toast.error("Owner login required to deploy"); return; }
        setDeploying(true);
        try {
            const patch = { exit_method_pref: method.id };
            if (method.id === "fixed_pct") { patch.stop_loss_pct = cfg.stop_pct; }
            if (method.id === "atr_trailing" || method.id === "chandelier") {
                patch.trail_arm_pct = cfg.trail_arm ?? 1.6; patch.trail_distance_pct = cfg.trail_dist ?? 0.9;
            }
            if (method.id === "breakeven_trail" || method.id === "structural_trail") patch.profit_protection_enabled = true;
            const prof = {};
            if (cfg.trail_atr_mult != null) prof.trail_atr_mult = cfg.trail_atr_mult;
            if (cfg.profit_arm_pct != null) prof.profit_arm_pct = cfg.profit_arm_pct;
            if (cfg.time_exit_hours != null) prof.time_exit_hours = cfg.time_exit_hours;

            if (scope === "strategy" && Object.keys(prof).length) patch.profile_overrides = { [strategy]: prof };
            if (scope === "coin") patch.asset_exit_overrides = { [coin]: { method: method.id, ...cfg } };
            await api.updateSettings(patch);
            const where = scope === "strategy" ? `strategy "${strategy}"` : scope === "coin" ? coin : "all markets (global)";
            toast.success(`Deployed ${method.name}`, { description: `Applied to ${where}. Live on the next trading cycle.` });
        } catch (e) {
            toast.error("Deploy failed", { description: String(e?.response?.data?.detail || e?.message) });
        } finally { setDeploying(false); }
    };

    return (
        <div className="space-y-5" data-testid="exit-workflow">
            <StepDots step={step} />

            {step === 1 && (
                <Block title="Step 1 — What do you want to modify?" hint="Pick the scope this exit rule will apply to.">
                    <div className="grid gap-3">
                        {SCOPES.map((s) => (
                            <Card key={s.id} testId={`scope-${s.id}`} icon={s.icon} name={s.name} desc={s.desc}
                                active={scope === s.id} onClick={() => setScope(s.id)} />
                        ))}
                    </div>
                    {scope === "strategy" && (
                        <ChipRow label="Strategy" items={CORE} value={strategy} onPick={setStrategy} prefix="wf-strat" />
                    )}
                    {scope === "coin" && (
                        <ChipRow label="Coin" items={SYMBOLS} value={coin} onPick={setCoin} prefix="wf-coin" />
                    )}
                    <Primary testId="wf-next-1" disabled={!scope} onClick={() => setStep(2)} label="Continue" />
                </Block>
            )}

            {step === 2 && (
                <Block title="Step 2 — Choose an exit method" hint="Eight proven exit styles. Pick the one that fits your trading approach.">
                    <div className="grid sm:grid-cols-2 gap-3">
                        {METHODS.map((m) => (
                            <Card key={m.id} testId={`method-${m.id}`} icon={m.icon} name={m.name} desc={m.desc}
                                active={method?.id === m.id} onClick={() => pick(m)}
                                tag={m.engine !== "fixed" && m.engine !== "atr" ? "Universal Engine" : null} />
                        ))}
                    </div>
                    <BackBtn onClick={() => setStep(1)} />
                </Block>
            )}

            {step === 3 && method && (
                <Block title={`Step 3 — Configure: ${method.name}`} hint="Only the parameters relevant to this method are shown.">
                    <div className="panel border-atlas-border rounded-xl p-5 space-y-4">
                        {method.id === "fixed_pct" && (<>
                            <Num label="Take-Profit target (%)" v={cfg.target_pct} on={(x) => setF("target_pct", x)} testId="cfg-target-pct" />
                            <Num label="Stop-Loss (%)" v={cfg.stop_pct} on={(x) => setF("stop_pct", x)} testId="cfg-stop-pct" />
                        </>)}
                        {method.id === "atr_trailing" && (<>
                            <Num label="ATR stop multiple (×)" v={cfg.atr_mult} on={(x) => setF("atr_mult", x)} step={0.1} testId="cfg-atr-mult" />
                            <Num label="ATR period" v={cfg.atr_period} on={(x) => setF("atr_period", x)} testId="cfg-atr-period" />
                            <Num label="Trail arm (%)" v={cfg.trail_arm} on={(x) => setF("trail_arm", x)} step={0.1} testId="cfg-trail-arm" />
                            <Num label="Trail distance (×ATR)" v={cfg.trail_dist} on={(x) => setF("trail_dist", x)} step={0.1} testId="cfg-trail-dist" />
                        </>)}
                        {method.id === "structural_trail" && (<>
                            <Num label="Trail ATR multiple (×)" v={cfg.trail_atr_mult} on={(x) => setF("trail_atr_mult", x)} step={0.1} testId="cfg-satr" />
                            <Num label="Profit-protect arm (%)" v={cfg.profit_arm_pct} on={(x) => setF("profit_arm_pct", x)} step={0.1} testId="cfg-parm" />
                        </>)}
                        {method.id === "breakeven_trail" && (<>
                            <Num label="Breakeven at (R multiple)" v={cfg.breakeven_r} on={(x) => setF("breakeven_r", x)} step={0.1} testId="cfg-ber" />
                            <Num label="Profit-floor arm (%)" v={cfg.profit_arm_pct} on={(x) => setF("profit_arm_pct", x)} step={0.1} testId="cfg-parm2" />
                        </>)}
                        {method.id === "partial_profit" && (<>
                            <Num label="Profit-protect arm (%)" v={cfg.profit_arm_pct} on={(x) => setF("profit_arm_pct", x)} step={0.1} testId="cfg-parm3" />
                            <Hint>Takes 50% off at the momentum-exhaustion target, then trails the remainder (engine default).</Hint>
                        </>)}
                        {method.id === "momentum_exhaustion" && (
                            <Hint>No parameters — exits the full position when momentum dies (overbought zone + volume climax + exhaustion candle).</Hint>
                        )}
                        {method.id === "time_based" && (
                            <Num label="Time exit (hours)" v={cfg.time_exit_hours} on={(x) => setF("time_exit_hours", x)} testId="cfg-time" />
                        )}
                        {method.id === "chandelier" && (<>
                            <Num label="ATR period" v={cfg.atr_period} on={(x) => setF("atr_period", x)} testId="cfg-ch-period" />
                            <Num label="ATR multiple (×)" v={cfg.atr_mult} on={(x) => setF("atr_mult", x)} step={0.1} testId="cfg-ch-mult" />
                        </>)}
                        {method.engine === "native" || method.id === "chandelier" ? (
                            <div className="flex items-center gap-2 text-[11px] font-mono text-atlas-warning bg-atlas-warning/10 border border-atlas-warning/30 rounded-lg px-3 py-2">
                                <FlaskConical className="w-3.5 h-3.5 shrink-0" />
                                Tested via the closest supported engine: <b className="text-atlas-text">{ENGINE_LABEL[method.engine]}</b>.
                            </div>
                        ) : null}
                    </div>
                    <div className="flex gap-2">
                        <BackBtn onClick={() => setStep(2)} />
                        <Primary testId="wf-next-3" onClick={() => setStep(4)} label="Continue to Test / Deploy" />
                    </div>
                </Block>
            )}

            {step === 4 && method && (
                <Block title="Step 4 — Test or Deploy" hint="Test on historical data first, then deploy to paper/live when you're confident.">
                    <div className="panel border-atlas-border rounded-xl p-4 flex items-center justify-between flex-wrap gap-2">
                        <div className="font-mono text-[11px] text-atlas-textSecondary">
                            <span className="text-atlas-textTertiary">Scope</span> <b className="text-atlas-text">{scope === "strategy" ? strategy : scope === "coin" ? coin : "Global"}</b>
                            <span className="mx-2 text-atlas-border">·</span>
                            <span className="text-atlas-textTertiary">Method</span> <b className="text-atlas-text">{method.name}</b>
                        </div>
                    </div>
                    <div className="flex gap-3">
                        <button data-testid="wf-test" onClick={runTest} disabled={testing}
                            className="flex-1 flex items-center justify-center gap-2 rounded-lg border border-atlas-cyan/50 text-atlas-cyan hover:bg-atlas-cyan/10 font-mono text-xs font-bold tracking-widest py-3.5 transition-colors disabled:opacity-50">
                            {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} TEST THIS EXIT
                        </button>
                        <button data-testid="wf-deploy" onClick={deploy} disabled={deploying}
                            className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-atlas-cyan text-atlas-bg hover:brightness-110 font-mono text-xs font-bold tracking-widest py-3.5 transition-all disabled:opacity-50">
                            {deploying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />} DEPLOY
                        </button>
                    </div>
                    <BackBtn onClick={() => setStep(3)} />
                    {result && <TestResult result={result} method={method} />}
                    <button data-testid="wf-restart" onClick={reset}
                        className="w-full text-center font-mono text-[10px] tracking-widest text-atlas-textTertiary hover:text-atlas-text py-2">
                        START OVER
                    </button>
                </Block>
            )}
        </div>
    );
}

/* ---- Test result + What-If counterfactual ---- */
function TestResult({ result, method }) {
    const per = result.per_symbol || {};
    const syms = Object.keys(per);
    if (!syms.length) return <div className="panel rounded-xl p-4 font-mono text-[11px] text-atlas-textTertiary">No result rows returned.</div>;
    return (
        <div className="space-y-5" data-testid="wf-result">
            <div>
                <SubHead icon={CheckCircle2} title="Backtest Performance" sub={`${method.name} · 3-month · 1h · BTC/ETH/SOL`} />
                <Grid head={["Symbol", "Return %", "Win %", "PF", "Trades", "MaxDD %"]}
                    rows={syms.map((s) => {
                        const d = per[s] || {};
                        return [s, fmt(d.total_return_pct), fmt(d.win_rate_pct), fmt(d.profit_factor), d.trades ?? "—", fmt(d.max_drawdown_pct)];
                    })} />
            </div>
            <div>
                <SubHead icon={FlaskConical} title="What-If — same entries, different exit" sub="If you'd used another exit on the exact same trades, the result would have been:" />
                {syms.map((s) => {
                    const ec = (per[s] || {}).exit_comparison || {};
                    const rows = ec.rows || {};
                    const keys = Object.keys(rows);
                    if (!keys.length) return null;
                    return (
                        <div key={s} className="mb-3">
                            <div className="font-mono text-[10px] tracking-widest text-atlas-textTertiary mb-1">{s} {ec.winner_key ? `· best: ${rows[ec.winner_key]?.label}` : ""}</div>
                            <Grid head={["Exit config", "PF", "Win %", "Net ret %", "MaxDD %"]}
                                rows={keys.map((k) => {
                                    const r = rows[k];
                                    return [r.label + (k === ec.winner_key ? "  ★" : ""), fmt(r.profit_factor), fmt(r.win_rate_pct), fmt(r.total_return_pct), fmt(r.max_drawdown_pct)];
                                })} highlight={ec.winner_key ? keys.indexOf(ec.winner_key) : -1} />
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

/* ---- small presentational helpers ---- */
const fmt = (x) => (typeof x === "number" ? x.toFixed(2) : x ?? "—");

function StepDots({ step }) {
    const labels = ["Scope", "Method", "Configure", "Test / Deploy"];
    return (
        <div className="flex items-center gap-2">
            {labels.map((l, i) => (
                <div key={l} className="flex items-center gap-2">
                    <div className={`flex items-center gap-1.5 font-mono text-[10px] tracking-widest px-2.5 py-1 rounded-full border ${
                        step === i + 1 ? "border-atlas-cyan text-atlas-cyan bg-atlas-cyan/10"
                            : step > i + 1 ? "border-atlas-positive/40 text-atlas-positive" : "border-atlas-border text-atlas-textTertiary"}`}>
                        {i + 1}. {l}
                    </div>
                    {i < labels.length - 1 && <ChevronRight className="w-3 h-3 text-atlas-border" />}
                </div>
            ))}
        </div>
    );
}
function Block({ title, hint, children }) {
    return (
        <div className="space-y-4">
            <div><div className="font-heading text-lg text-atlas-text">{title}</div>
                <div className="font-mono text-[11px] text-atlas-textSecondary mt-1">{hint}</div></div>
            {children}
        </div>
    );
}
function Card({ testId, icon: Icon, name, desc, active, onClick, tag }) {
    return (
        <button type="button" data-testid={testId} onClick={onClick}
            className={`text-left panel rounded-xl p-4 border transition-all group ${active ? "border-atlas-cyan bg-atlas-cyan/5" : "border-atlas-border hover:border-atlas-textTertiary"}`}>
            <div className="flex items-start gap-3">
                <span className={`w-9 h-9 rounded-lg grid place-items-center border shrink-0 ${active ? "border-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border bg-atlas-cyan/5"}`}>
                    <Icon className="w-4.5 h-4.5 text-atlas-cyan" />
                </span>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 font-heading text-[15px] text-atlas-text">{name}
                        {tag && <span className="font-mono text-[8px] uppercase tracking-widest text-atlas-warning border border-atlas-warning/30 bg-atlas-warning/10 rounded-full px-1.5 py-0.5">{tag}</span>}
                    </div>
                    <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed mt-0.5">{desc}</p>
                </div>
                {active && <CheckCircle2 className="w-4 h-4 text-atlas-cyan shrink-0" />}
            </div>
        </button>
    );
}
function ChipRow({ label, items, value, onPick, prefix }) {
    return (
        <div className="mt-1">
            <div className="font-mono text-[10px] tracking-widest text-atlas-textTertiary mb-1.5">{label.toUpperCase()}</div>
            <div className="flex flex-wrap gap-2">
                {items.map((it) => (
                    <button key={it} data-testid={`${prefix}-${it.replace("/", "-")}`} onClick={() => onPick(it)}
                        className={`font-mono text-[11px] font-bold px-3 py-1.5 rounded-full border transition-all ${value === it ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:border-atlas-textTertiary"}`}>
                        {it}
                    </button>
                ))}
            </div>
        </div>
    );
}
function Num({ label, v, on, step = 1, testId }) {
    return (
        <label className="flex items-center justify-between gap-4">
            <span className="font-mono text-[12px] text-atlas-textSecondary">{label}</span>
            <input data-testid={testId} type="number" step={step} value={v ?? ""} onChange={(e) => on(parseFloat(e.target.value))}
                className="w-28 bg-atlas-bg border border-atlas-border rounded-lg px-3 py-2 font-mono text-sm text-atlas-text text-right focus:border-atlas-cyan outline-none" />
        </label>
    );
}
function Hint({ children }) {
    return <p className="font-mono text-[11px] text-atlas-textTertiary leading-relaxed">{children}</p>;
}
function Primary({ testId, label, onClick, disabled }) {
    return (
        <button type="button" data-testid={testId} onClick={onClick} disabled={disabled}
            className={`w-full rounded-lg bg-atlas-cyan text-atlas-bg font-mono text-xs font-bold tracking-widest py-3.5 mt-2 transition-all ${disabled ? "opacity-40 cursor-not-allowed" : "hover:brightness-110"}`}>
            {label}
        </button>
    );
}
function BackBtn({ onClick }) {
    return (
        <button type="button" data-testid="wf-back" onClick={onClick}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-atlas-border text-atlas-textSecondary hover:text-atlas-text font-mono text-[11px] tracking-widest px-4 py-3 transition-colors">
            <ArrowLeft className="w-3.5 h-3.5" /> Back
        </button>
    );
}
function SubHead({ icon: Icon, title, sub }) {
    return (
        <div className="flex items-center gap-2.5 mb-2">
            <span className="w-8 h-8 rounded-lg grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Icon className="w-4 h-4 text-atlas-cyan" /></span>
            <div><div className="font-heading text-base text-atlas-text leading-none">{title}</div>
                <div className="font-mono text-[10px] text-atlas-textTertiary mt-1">{sub}</div></div>
        </div>
    );
}
function Grid({ head, rows, highlight = -1 }) {
    return (
        <div className="rounded-lg border border-atlas-border overflow-hidden">
            <div className="grid font-mono text-[10px] tracking-widest text-atlas-textTertiary bg-atlas-panelHover px-3 py-2" style={{ gridTemplateColumns: `1.4fr repeat(${head.length - 1}, 1fr)` }}>
                {head.map((h) => <span key={h} className={h === head[0] ? "" : "text-right"}>{h}</span>)}
            </div>
            {rows.map((r, i) => (
                <div key={i} className={`grid font-mono text-[11px] px-3 py-2 border-t border-atlas-border ${i === highlight ? "bg-atlas-positive/5" : ""}`} style={{ gridTemplateColumns: `1.4fr repeat(${head.length - 1}, 1fr)` }}>
                    {r.map((c, j) => <span key={j} className={`${j === 0 ? "text-atlas-text font-bold truncate" : "text-right tabular-nums text-atlas-textSecondary"}`}>{c}</span>)}
                </div>
            ))}
        </div>
    );
}
