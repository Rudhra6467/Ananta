import { useEffect, useState } from "react";
import {
    Save, ShieldOff, Key, AlertTriangle, Zap, Info, TrendingUp, ShieldCheck, Shield,
    BarChart3, Layers, Gauge, Percent, Target, CheckCircle2, Loader2, Power,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import KillSwitchPanel from "@/components/KillSwitchPanel";
import AnalyticsPanel from "@/components/AnalyticsPanel";
import StrategyValidationPanel from "@/components/StrategyValidationPanel";
import QuadrantCard from "@/components/lab/QuadrantCard";
import LabModal from "@/components/lab/LabModal";
import ExitEngineModal from "@/components/lab/ExitEngineModal";
import { useAuth } from "@/context/AuthContext";

// Cache the settings payload so re-opening the Research Lab renders instantly from cache.
let _settingsCache = null;

export default function SettingsPage() {
    const [s, setS] = useState(_settingsCache);
    const [saving, setSaving] = useState(false);
    const [risk, setRisk] = useState(null);
    const [running, setRunning] = useState(false);
    const [lastRun, setLastRun] = useState(null);
    const [analytics, setAnalytics] = useState(null);
    const [excludeSynthetic, setExcludeSynthetic] = useState(false);
    const [validation, setValidation] = useState(null); // derived lab-readiness face data
    const [openModal, setOpenModal] = useState(null); // 'exit' | 'validation' | 'risk' | 'analytics'
    const { isOwner } = useAuth();

    const applyS = (v) => { _settingsCache = v; setS(v); };

    useEffect(() => {
        api.settings().then(applyS).catch(() => { if (!_settingsCache) setS(null); });
        api.riskStatus().then(setRisk).catch(() => {});
        const t = setInterval(() => { api.riskStatus().then(setRisk).catch(() => {}); }, 12000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        api.analyticsPerformance(excludeSynthetic).then(setAnalytics).catch(() => {});
        const t = setInterval(() => { api.analyticsPerformance(excludeSynthetic).then(setAnalytics).catch(() => {}); }, 15000);
        return () => clearInterval(t);
    }, [excludeSynthetic]);

    // Derive the Strategy-Validation face from the latest completed lab runs (real data).
    useEffect(() => { deriveValidation().then(setValidation).catch(() => setValidation({ empty: true })); }, []);

    const upd = (patch) => setS((cur) => ({ ...cur, ...patch }));

    const runCycleNow = async () => {
        setRunning(true);
        try {
            const out = await api.runCycle();
            setLastRun(out.ran_at);
            toast.success("CYCLE COMPLETED", { description: `${(out.results || []).length} symbols evaluated` });
            api.riskStatus().then(setRisk).catch(() => {});
        } catch (e) {
            toast.error("CYCLE FAILED", { description: String(e?.message || e) });
        } finally { setRunning(false); }
    };

    // Persist a partial patch merged into the current settings (used by the exit-engine modal).
    const persistPatch = async (patch) => {
        const merged = { ...s, ...patch };
        const payload = { ...merged };
        ["coinbase_api_secret", "kraken_api_secret"].forEach((k) => {
            if (payload[k] && /^•+$/.test(payload[k])) delete payload[k];
        });
        const next = await api.updateSettings(payload);
        applyS(next);
        return next;
    };

    const save = async () => {
        if (!s) return;
        setSaving(true);
        try {
            await persistPatch({});
            toast.success("SETTINGS SAVED", { description: "Risk engine and exchange config updated." });
        } catch (e) {
            toast.error("SAVE FAILED", { description: String(e?.message || e) });
        } finally { setSaving(false); }
    };

    const toggleKill = async (val) => {
        try {
            const next = await api.updateSettings({ manual_kill_switch: val });
            applyS(next);
            toast[val ? "error" : "success"](val ? "MANUAL KILL ENGAGED" : "MANUAL KILL RELEASED", {
                description: val ? "All new trades blocked until released." : "Trading resumes on next cycle.",
            });
        } catch (e) {
            toast.error("UPDATE FAILED", { description: String(e?.message || e) });
        }
    };

    if (!s) {
        return (
            <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary" data-testid="settings-loading">
                <span className="blink-cursor">LOADING RESEARCH LAB</span>
            </div>
        );
    }

    // ---- face metrics (localized state store) ----
    const engineName = s.dynamic_trail_enabled === false ? "Fixed-% Stop" : "ATR Trailing Stop";
    const hunterMult = s.profile_overrides?.hunter?.trail_atr_mult ?? 2.0;
    const killed = !!s.manual_kill_switch;
    const safe = risk?.status?.overall_safe !== false;
    const win = analytics?.rolling_24h || {};
    const closed = win.closed_trades || 0;
    const expectancy = win.expectancy_usd;
    const health = closed === 0 ? { t: "Warming up", dot: "muted" }
        : expectancy > 0 ? { t: "Good", dot: "good" }
            : { t: "Caution", dot: "warn" };
    const diversification = diversify(analytics?.sector_exposure?.counts);

    return (
        <TooltipProvider delayDuration={120}>
            <div className="space-y-5 pb-24" data-testid="settings-page">
                {/* Emergency override — top-right under the header */}
                <div className="flex items-center justify-end">
                    <button
                        data-testid="emergency-kill-btn"
                        onClick={() => isOwner ? toggleKill(!killed) : toast.error("Owner login required")}
                        title={isOwner ? "Emergency stop — blocks all new trades" : "Owner login required"}
                        className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 font-mono text-[11px] font-bold tracking-widest transition-all ${
                            killed
                                ? "border-atlas-negative bg-atlas-negative/15 text-atlas-negative animate-pulse"
                                : "border-atlas-negative/40 text-atlas-negative hover:bg-atlas-negative/10"
                        } disabled:opacity-50`}
                    >
                        <Power className="w-4 h-4" strokeWidth={2.5} />
                        {killed ? "KILL ENGAGED · RELEASE" : "EMERGENCY STOP"}
                    </button>
                </div>

                {/* 2×2 cockpit grid */}
                <div className="grid grid-cols-2 gap-3 md:gap-5" data-testid="lab-grid">
                    {/* Q1 — Entry & Exit Engine */}
                    <QuadrantCard
                        testid="quad-exit-engine" icon={TrendingUp} accent="cyan"
                        title="Entry & Exit Engine" subtitle="Position Modifiers"
                        stats={[{ testid: "face-active-engine", label: "Active Exit Engine", value: engineName, valueCls: "text-atlas-cyan", dot: "good" }]}
                        rows={[
                            { testid: "face-trail-mult", icon: TrendingUp, label: "Trail Multiplier", value: `${hunterMult}x` },
                            { testid: "face-arm", icon: Target, label: "Breakeven Arm", value: `${s.trail_arm_pct}%` },
                            { testid: "face-stop", icon: Shield, label: "Hard Stop-Loss", value: `${s.stop_loss_pct}%` },
                        ]}
                        cta="Open Engine" onOpen={() => setOpenModal("exit")}
                    />

                    {/* Q2 — Strategy Validation */}
                    <QuadrantCard
                        testid="quad-validation" icon={ShieldCheck} accent="violet"
                        title="Strategy Validation" subtitle="Stress Tester"
                        stats={[
                            { testid: "face-readiness", label: "Model Readiness", value: validation?.readiness != null ? `${validation.readiness}%` : "—", valueCls: "text-violet-400" },
                            { testid: "face-overfit", label: "Overfitting Risk", value: validation?.overfit?.t || "—", valueCls: "text-atlas-text", dot: validation?.overfit?.dot },
                        ]}
                        rows={[
                            { testid: "face-wfa", icon: CheckCircle2, label: "Walk-Forward", value: validation?.wfa || "—", valueCls: validation?.wfa === "Passed" ? "text-atlas-positive" : "text-atlas-textTertiary" },
                            { testid: "face-mc", icon: Layers, label: "Monte Carlo", value: "Soon", valueCls: "text-atlas-textTertiary" },
                            { testid: "face-sens", icon: Gauge, label: "Sensitivity", value: validation?.sensitivity || "—", valueCls: validation?.sensitivity === "Stable" ? "text-atlas-positive" : "text-atlas-textTertiary" },
                        ]}
                        cta="Open Validation" onOpen={() => setOpenModal("validation")}
                    />

                    {/* Q3 — Risk Monitor */}
                    <QuadrantCard
                        testid="quad-risk" icon={Shield} accent="amber"
                        title="Risk Monitor" subtitle="Safeguards"
                        stats={[{ testid: "face-risk-status", label: "Risk Status", value: safe ? "Protected" : "Alert", valueCls: safe ? "text-atlas-positive" : "text-atlas-negative", dot: safe ? "good" : "bad" }]}
                        rows={[
                            { testid: "face-max-pos", icon: Layers, label: "Max Open Positions", value: s.max_concurrent_positions },
                            { testid: "face-daily-loss", icon: Percent, label: "Daily Loss Cap", value: `${s.max_daily_loss_pct}%` },
                            { testid: "face-min-conf", icon: Target, label: "Min Confidence", value: Number(s.min_confidence).toFixed(2) },
                            { testid: "face-max-spread", icon: Gauge, label: "Max Spread", value: `${s.max_spread_pct}%` },
                        ]}
                        cta="Open Risk Monitor" onOpen={() => setOpenModal("risk")}
                    />

                    {/* Q4 — Analytics Engine */}
                    <QuadrantCard
                        testid="quad-analytics" icon={BarChart3} accent="green"
                        title="Analytics Engine" subtitle="AI Reasoning Portal"
                        stats={[
                            { testid: "face-health", label: "Portfolio Health", value: health.t, valueCls: "text-atlas-text", dot: health.dot },
                            { testid: "face-diversification", label: "Diversification", value: diversification != null ? `${diversification}%` : "—", valueCls: "text-atlas-positive" },
                        ]}
                        rows={[
                            { testid: "face-winrate", icon: Percent, label: "Win Rate", value: closed ? `${win.win_rate_pct ?? 0}%` : "—" },
                            { testid: "face-pf", icon: Gauge, label: "Profit Factor", value: closed ? (win.profit_factor ?? "—") : "—" },
                            { testid: "face-expectancy", icon: Target, label: "Expectancy", value: closed ? `${(expectancy ?? 0) >= 0 ? "+" : ""}$${Number(expectancy ?? 0).toFixed(2)}` : "—", valueCls: (expectancy ?? 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative" },
                            { testid: "face-open-pos", icon: Layers, label: "Open Positions", value: Array.isArray(analytics?.open_positions) ? analytics.open_positions.length : (analytics?.open_positions ?? "—") },
                        ]}
                        cta="Open Analytics" onOpen={() => setOpenModal("analytics")}
                    />
                </div>

                {/* ---- Q1 modal ---- */}
                <ExitEngineModal
                    open={openModal === "exit"} onOpenChange={(o) => setOpenModal(o ? "exit" : null)}
                    settings={s} onPersist={persistPatch} isOwner={isOwner}
                />

                {/* ---- Q2 modal ---- */}
                <LabModal open={openModal === "validation"} onOpenChange={(o) => setOpenModal(o ? "validation" : null)}
                    testid="validation-modal" icon={ShieldCheck} accent="violet"
                    title="Strategy Validation" subtitle="Walk-Forward · Sensitivity · Stress Tester">
                    <StrategyValidationPanel />
                </LabModal>

                {/* ---- Q3 modal ---- */}
                <LabModal open={openModal === "risk"} onOpenChange={(o) => setOpenModal(o ? "risk" : null)}
                    testid="risk-modal" icon={Shield} accent="amber"
                    title="Risk Monitor & Safeguards" subtitle="Guardrails · Sizing · Credentials"
                    footer={
                        <div className="flex items-center justify-between gap-3">
                            <span className="font-mono text-[10px] text-atlas-textTertiary">Updated {s.updated_at ? new Date(s.updated_at).toLocaleString() : "—"}</span>
                            <Button data-testid="risk-save-btn" onClick={save} disabled={saving || !isOwner} className="gap-2">
                                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{isOwner ? "SAVE" : "READ-ONLY"}
                            </Button>
                        </div>
                    }>
                    <RiskThresholds s={s} upd={upd} />
                    <AdaptiveSizing s={s} upd={upd} />
                    <div className="panel border-atlas-border rounded-xl p-4">
                        <div className="label-tag mb-3">EXECUTION CONTROLS</div>
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                            <div className="lg:col-span-2"><KillSwitchPanel risk={risk} /></div>
                            <div className="panel border-atlas-border rounded-lg flex flex-col">
                                <div className="px-4 pt-3 pb-2 border-b border-atlas-border"><div className="label-tag">MANUAL CYCLE</div></div>
                                <div className="p-4 flex-1 flex flex-col justify-between gap-3">
                                    <div className="text-[10px] font-mono text-atlas-textSecondary">Loop runs every 90s. Trigger an immediate cycle:</div>
                                    {lastRun && <div className="text-[10px] font-mono text-atlas-textTertiary">LAST: {new Date(lastRun).toLocaleTimeString()}</div>}
                                    <Button data-testid="settings-run-cycle-btn" onClick={runCycleNow} disabled={running || !isOwner}
                                        className="rounded-md bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-xs tracking-widest font-bold disabled:opacity-50">
                                        {running ? <span className="blink-cursor">RUNNING</span> : <><Zap className="w-3.5 h-3.5 mr-2" strokeWidth={2.5} />RUN CYCLE NOW</>}
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                    <ApiKeys s={s} upd={upd} />
                </LabModal>

                {/* ---- Q4 modal ---- */}
                <LabModal open={openModal === "analytics"} onOpenChange={(o) => setOpenModal(o ? "analytics" : null)}
                    testid="analytics-modal" icon={BarChart3} accent="green"
                    title="Analytics Engine" subtitle="Performance Diagnostics · AI Reasoning">
                    <AnalyticsPanel analytics={analytics} excludeSynthetic={excludeSynthetic} onToggleSynthetic={setExcludeSynthetic} />
                </LabModal>
            </div>
        </TooltipProvider>
    );
}

// Diversification index (0–100) via Herfindahl on sector counts. 1 position => 0%.
function diversify(counts) {
    if (!counts || typeof counts !== "object") return null;
    const vals = Object.values(counts).map(Number).filter((n) => n > 0);
    const total = vals.reduce((a, b) => a + b, 0);
    if (total <= 1) return total === 1 ? 0 : null;
    const hhi = vals.reduce((a, n) => a + (n / total) ** 2, 0);
    return Math.round((1 - hhi) * 100);
}

// Derive validation face data from the latest completed lab runs (real, defensive).
async function deriveValidation() {
    const { runs = [] } = await api.labRuns(20);
    const done = runs.filter((r) => r.status === "DONE");
    if (!done.length) return { empty: true };
    const out = {};
    // walk-forward verdict (needs detail)
    const wf = done.find((r) => r.kind === "walk_forward");
    if (wf) {
        try {
            const d = await api.labRun(wf.id);
            const v = d?.result?.verdict || "";
            out.wfa = /ROBUST/i.test(v) ? "Passed" : /OVERFIT|NO-IN-SAMPLE|WEAK/i.test(v) ? "Weak" : "Mixed";
            const eff = Number(d?.result?.wfa_efficiency);
            out.overfit = Number.isFinite(eff)
                ? (eff >= 0.7 ? { t: "Low", dot: "good" } : eff >= 0.4 ? { t: "Medium", dot: "warn" } : { t: "High", dot: "bad" })
                : { t: "—", dot: "muted" };
        } catch { /* noop */ }
    }
    const sens = done.find((r) => r.kind === "sensitivity");
    if (sens) {
        try {
            const d = await api.labRun(sens.id);
            out.sensitivity = /ROBUST/i.test(d?.result?.verdict || "") ? "Stable" : "Fragile";
        } catch { /* noop */ }
    }
    // readiness from the latest backtest metrics
    const bt = done.find((r) => r.kind === "backtest");
    if (bt) {
        try {
            const d = await api.labRun(bt.id);
            const per = Object.values(d?.result?.per_symbol || {}).filter((m) => !m.error);
            if (per.length) {
                const avg = (k) => per.reduce((a, m) => a + (Number(m[k]) || 0), 0) / per.length;
                const pf = avg("profit_factor"), ret = avg("total_return_pct"), dd = Math.abs(avg("max_drawdown_pct"));
                let score = 40;
                score += pf >= 1.5 ? 30 : pf >= 1.1 ? 18 : pf >= 1 ? 8 : 0;
                score += ret > 0 ? 15 : 0;
                score += dd <= 5 ? 15 : dd <= 12 ? 8 : 0;
                out.readiness = Math.max(1, Math.min(99, Math.round(score)));
            }
        } catch { /* noop */ }
    }
    return out;
}

/* ---------------- Q3 modal sub-sections ---------------- */
function RiskThresholds({ s, upd }) {
    return (
        <div className="panel border-atlas-border rounded-xl p-5 space-y-6">
            <div className="label-tag">RISK THRESHOLDS</div>
            <SliderField id="spread" label="MAX SPREAD" description="Hard kill: trades blocked if bid/ask spread widens past this."
                value={s.max_spread_pct} min={0.05} max={2} step={0.05} unit="%" onChange={(v) => upd({ max_spread_pct: v })} />
            <SliderField id="daily-loss" label="MAX DAILY LOSS" description="Hard kill: trades blocked if equity drops by this % from day start."
                value={s.max_daily_loss_pct} min={0.5} max={10} step={0.1} unit="%" onChange={(v) => upd({ max_daily_loss_pct: v })} />
            <SliderField id="min-confidence" label="MIN LLM CONFIDENCE" description="Soft block: don't open new positions below this LLM conviction."
                value={s.min_confidence} min={0} max={1} step={0.05} unit="" onChange={(v) => upd({ min_confidence: v })} />
            <div className="grid grid-cols-2 gap-4">
                <SliderField id="size-min" label="MIN POSITION SIZE" tooltip="Legacy %-of-equity sizing floor. Only used when Adaptive Lot Sizing is OFF."
                    value={s.position_size_pct_min} min={0.1} max={5} step={0.1} unit="%" onChange={(v) => upd({ position_size_pct_min: v })} />
                <SliderField id="size-max" label="MAX POSITION SIZE" tooltip="Legacy %-of-equity sizing ceiling. Only used when Adaptive Lot Sizing is OFF."
                    value={s.position_size_pct_max} min={0.5} max={10} step={0.1} unit="%" onChange={(v) => upd({ position_size_pct_max: v })} />
            </div>
        </div>
    );
}

function AdaptiveSizing({ s, upd }) {
    return (
        <div className="panel border-atlas-border rounded-xl p-5 space-y-5">
            <div className="flex items-center justify-between">
                <div>
                    <div className="label-tag">ADAPTIVE LOT SIZING</div>
                    <div className="mt-1 text-[11px] font-mono text-atlas-textSecondary">STRONG setups (trend + volatility + conviction) get the bigger USD lot.</div>
                </div>
                <Switch data-testid="adaptive-sizing-switch" checked={!!s.adaptive_sizing_enabled} onCheckedChange={(v) => upd({ adaptive_sizing_enabled: v })}
                    className="data-[state=checked]:bg-atlas-cyan data-[state=unchecked]:bg-atlas-border" />
            </div>
            <div className="grid grid-cols-2 gap-4">
                <NumberField id="normal-lot-usd" label="NORMAL LOT (USD)" value={s.normal_lot_usd} min={1} max={1000} step={0.5} onChange={(v) => upd({ normal_lot_usd: v })} />
                <NumberField id="strong-lot-usd" label="STRONG LOT (USD)" value={s.strong_lot_usd} min={1} max={1000} step={0.5} onChange={(v) => upd({ strong_lot_usd: v })} />
            </div>
            <NumberField id="max-concurrent" label="MAX CONCURRENT POSITIONS" value={s.max_concurrent_positions} min={1} max={20} step={1}
                onChange={(v) => upd({ max_concurrent_positions: Math.round(v) })} description="Beyond this, fresh BUY signals are queued for the next cycle." />
        </div>
    );
}

function ApiKeys({ s, upd }) {
    return (
        <div className="panel border-atlas-border rounded-xl p-5">
            <div className="label-tag mb-3">EXCHANGE CREDENTIALS · OPTIONAL</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                    <div className="label-tag mb-2 flex items-center gap-2"><Key className="w-3 h-3" />KRAKEN</div>
                    <div className="space-y-3">
                        <Field id="kraken-key" label="API Key" value={s.kraken_api_key} onChange={(v) => upd({ kraken_api_key: v })} />
                        <Field id="kraken-secret" label="API Secret" value={s.kraken_api_secret} onChange={(v) => upd({ kraken_api_secret: v })} type="password" />
                    </div>
                </div>
                <div>
                    <div className="label-tag mb-2 flex items-center gap-2"><Key className="w-3 h-3" />COINBASE</div>
                    <div className="space-y-3">
                        <Field id="coinbase-key" label="API Key" value={s.coinbase_api_key} onChange={(v) => upd({ coinbase_api_key: v })} />
                        <Field id="coinbase-secret" label="API Secret" value={s.coinbase_api_secret} onChange={(v) => upd({ coinbase_api_secret: v })} type="password" />
                    </div>
                </div>
            </div>
            <div className="mt-3 text-[10px] font-mono text-atlas-textTertiary">Keys are only used in LIVE mode. PAPER reads public market data; no auth required.</div>
        </div>
    );
}

function TitleLabel({ children, tooltip, htmlFor }) {
    if (!tooltip) return <Label htmlFor={htmlFor} className="label-tag">{children}</Label>;
    return (
        <Tooltip delayDuration={120}>
            <TooltipTrigger asChild>
                <Label htmlFor={htmlFor} data-testid={htmlFor ? `tooltip-label-${htmlFor}` : undefined} className="label-tag inline-flex items-center gap-1 cursor-help">
                    {children}<Info className="w-3 h-3 text-atlas-textTertiary shrink-0" />
                </Label>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-[260px] bg-atlas-panel border border-atlas-border text-white font-mono text-[11px] leading-relaxed rounded-none">
                {tooltip}
            </TooltipContent>
        </Tooltip>
    );
}

function SliderField({ id, label, description, tooltip, value, min, max, step, unit, onChange }) {
    return (
        <div data-testid={`slider-${id}`}>
            <div className="flex items-center justify-between mb-2">
                <TitleLabel tooltip={tooltip || description} htmlFor={`input-${id}`}>{label}</TitleLabel>
                <div className="font-mono text-base font-bold tabular-nums">
                    {Number(value).toFixed(2)}<span className="text-atlas-textSecondary ml-1">{unit}</span>
                </div>
            </div>
            <Slider data-testid={`slider-input-${id}`} value={[Number(value)]} min={min} max={max} step={step}
                onValueChange={(v) => onChange(v[0])}
                className="[&_[role=slider]]:rounded-none [&_[role=slider]]:bg-atlas-cyan [&_[role=slider]]:border-atlas-cyan" />
            {description && <div className="mt-2 text-[10px] font-mono text-atlas-textTertiary">{description}</div>}
        </div>
    );
}

function Field({ id, label, value, onChange, type = "text", tooltip }) {
    return (
        <div>
            <TitleLabel tooltip={tooltip} htmlFor={id}>{label}</TitleLabel>
            <Input id={id} data-testid={`input-${id}`} type={type} value={value || ""} onChange={(e) => onChange(e.target.value)}
                placeholder="••••••••" className="atlas-input rounded-none mt-1" />
        </div>
    );
}

function NumberField({ id, label, value, min, max, step, onChange, description, tooltip }) {
    return (
        <div data-testid={`number-${id}`}>
            <TitleLabel tooltip={tooltip || description} htmlFor={id}>{label}</TitleLabel>
            <Input id={id} data-testid={`input-${id}`} type="number" value={value ?? ""} min={min} max={max} step={step}
                onChange={(e) => { const raw = e.target.value; const n = raw === "" ? 0 : Number(raw); if (!Number.isNaN(n)) onChange(n); }}
                className="atlas-input rounded-none font-mono mt-1" />
            {description && <div className="mt-2 text-[10px] font-mono text-atlas-textTertiary">{description}</div>}
        </div>
    );
}
