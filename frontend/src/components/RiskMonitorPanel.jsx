import { useEffect, useState } from "react";
import { Target, Shield, SlidersHorizontal, Save, Check } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/context/AuthContext";
import { describeActiveExit } from "@/lib/exitConfig";

// Compact Risk Monitor — parity with the mobile Exit Engine "Risk Monitor" view:
//   1. ENTRY SETUP    — rules that decide WHEN Ananta opens a position
//   2. ACTIVE EXIT ENGINE — read-only summary (configured in the Exit Engine flow)
//   3. SAFEGUARDS     — account-level protection + kill switch
export default function RiskMonitorPanel() {
    const { isOwner } = useAuth();
    const [s, setS] = useState(null);
    const [risk, setRisk] = useState(null);
    const [savedFlash, setSavedFlash] = useState(false);

    useEffect(() => {
        api.settings().then(setS).catch(() => {});
        api.riskStatus().then(setRisk).catch(() => {});
        const t = setInterval(() => api.riskStatus().then(setRisk).catch(() => {}), 12000);
        return () => clearInterval(t);
    }, []);

    // Field edits update LOCAL state only — nothing persists until the user clicks
    // "Save Settings" (saveAll). No auto-save.
    const update = (patch) => setS((prev) => ({ ...prev, ...patch }));

    const saveAll = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        const patch = {
            min_confidence: s.min_confidence, htf_trend_enabled: s.htf_trend_enabled,
            level_entry_enabled: s.level_entry_enabled, adaptive_sizing_enabled: s.adaptive_sizing_enabled,
            breakout_min_confidence: s.breakout_min_confidence, max_concurrent_positions: s.max_concurrent_positions,
            allowed_regimes: Array.isArray(s.allowed_regimes) ? s.allowed_regimes : [],
            max_daily_loss_pct: s.max_daily_loss_pct, max_spread_pct: s.max_spread_pct, normal_lot_usd: s.normal_lot_usd,
        };
        try {
            const next = await api.updateSettings(patch);
            setS(next);
            toast.success("Risk settings saved");
            setSavedFlash(true);
            setTimeout(() => setSavedFlash(false), 2000);
        } catch (e) {
            toast.error("Save failed", { description: String(e?.response?.data?.detail || e?.message || e) });
        }
    };

    if (!s) return <div className="py-10 text-center font-mono text-[11px] text-atlas-textTertiary" data-testid="rm-loading">Loading risk configuration…</div>;

    const safe = risk?.status?.overall_safe !== false;
    const active = describeActiveExit(s);

    return (
        <div className="space-y-5" data-testid="risk-monitor-panel">
            {/* ENTRY SETUP */}
            <Card icon={SlidersHorizontal} title="ENTRY SETUP" subtitle="Rules that decide when Ananta opens a new position." testId="rm-entry-setup">
                <NumField label="Min Confidence" k="min_confidence" value={s.min_confidence} isOwner={isOwner} onSave={update} />
                <ToggleField label="HTF Trend Filter" desc="Require price > 4h EMA50 > EMA200" k="htf_trend_enabled" value={s.htf_trend_enabled} isOwner={isOwner} onSave={update} />
                <ToggleField label="Support / Level Entry" desc="Only enter at clean historical support zones" k="level_entry_enabled" value={s.level_entry_enabled} isOwner={isOwner} onSave={update} />
                <ToggleField label="Adaptive Sizing" desc="Size the lot by setup strength" k="adaptive_sizing_enabled" value={s.adaptive_sizing_enabled} isOwner={isOwner} onSave={update} />
                <NumField label="Breakout Min Confidence" k="breakout_min_confidence" value={s.breakout_min_confidence} isOwner={isOwner} onSave={update} />
                <NumField label="Max Open Positions" k="max_concurrent_positions" value={s.max_concurrent_positions} isOwner={isOwner} onSave={update} />
                <RegimeField value={s.allowed_regimes} isOwner={isOwner} onSave={update} />
            </Card>

            {/* ACTIVE EXIT ENGINE (read-only) */}
            <Card icon={Target} title="ACTIVE EXIT ENGINE" subtitle="Configured in the Exit Engine flow." testId="rm-active-exit">
                <div className="flex items-center justify-between py-2 border-b border-atlas-border">
                    <span className="label-tag text-[9px] text-atlas-textTertiary">TYPE</span>
                    <span className="font-mono text-sm font-bold text-atlas-cyan" data-testid="rm-active-name">{active.typeLabel} ●</span>
                </div>
                {active.rows.map((r, i) => (
                    <SummaryRow key={r.label} label={r.label} value={r.value} last={i === active.rows.length - 1} />
                ))}
            </Card>

            {/* SAFEGUARDS */}
            <Card icon={Shield} title="RISK MONITOR · SAFEGUARDS" subtitle="Account-level protection."
                testId="rm-safeguards">
                <div className="flex items-center justify-between py-2 border-b border-atlas-border">
                    <span className="label-tag text-[9px] text-atlas-textTertiary">RISK STATUS</span>
                    <span className={`font-mono text-sm font-bold ${safe ? "text-atlas-cyan" : "text-atlas-negative"}`} data-testid="rm-risk-status">{safe ? "Protected ●" : "Alert ●"}</span>
                </div>
                <NumField label="Daily Loss Cap %" k="max_daily_loss_pct" value={s.max_daily_loss_pct} isOwner={isOwner} onSave={update} />
                <NumField label="Max Spread %" k="max_spread_pct" value={s.max_spread_pct} isOwner={isOwner} onSave={update} />
                <NumField label="Normal Lot (USD)" k="normal_lot_usd" value={s.normal_lot_usd} isOwner={isOwner} onSave={update} last />
            </Card>

            {/* Save — the ONLY thing that persists changes to the backend. */}
            <div className="pt-1">
                <button
                    data-testid="rm-save-settings"
                    onClick={saveAll}
                    disabled={!isOwner}
                    className={`w-full flex items-center justify-center gap-2 py-3 rounded-lg font-mono text-sm font-bold transition-colors disabled:opacity-50 ${savedFlash ? "border border-atlas-positive text-atlas-positive bg-atlas-positive/10" : "border border-atlas-cyan text-atlas-cyan hover:bg-atlas-cyan/10"}`}
                >
                    {savedFlash ? <><Check className="w-4 h-4" /> Saved</> : <><Save className="w-4 h-4" /> Save Settings</>}
                </button>
            </div>
        </div>
    );
}

function Card({ icon: Icon, title, subtitle, action, testId, children }) {
    return (
        <div className="panel border-atlas-border rounded-xl p-5" data-testid={testId}>
            <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2.5">
                    <span className="w-8 h-8 rounded-lg grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Icon className="w-4 h-4 text-atlas-cyan" /></span>
                    <div>
                        <div className="font-mono text-[11px] tracking-[0.2em] uppercase font-bold text-atlas-text">{title}</div>
                        {subtitle && <div className="label-tag mt-0.5 text-[9px] text-atlas-textTertiary normal-case tracking-normal">{subtitle}</div>}
                    </div>
                </div>
                {action}
            </div>
            <div className="divide-y divide-atlas-border">{children}</div>
        </div>
    );
}

function NumField({ label, k, value, isOwner, onSave, last }) {
    const [v, setV] = useState(String(value ?? ""));
    useEffect(() => setV(String(value ?? "")), [value]);
    const commit = () => { const n = parseFloat(v); if (!Number.isNaN(n) && n !== value) onSave({ [k]: n }); };
    return (
        <div className={`flex items-center justify-between py-2.5 ${last ? "" : ""}`}>
            <span className="font-mono text-[12px] text-atlas-textSecondary">{label}</span>
            <input data-testid={`rm-set-${k}`} value={v} disabled={!isOwner}
                onChange={(e) => setV(e.target.value)} onBlur={commit}
                onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                inputMode="decimal"
                className="w-24 rounded-md border border-atlas-border bg-atlas-bg px-2.5 py-1.5 text-right font-mono text-[12px] font-bold text-atlas-text focus:border-atlas-cyan focus:outline-none disabled:opacity-50" />
        </div>
    );
}

const REGIMES = ["COMPRESSION", "REVERSAL", "TREND_UP", "TREND_DOWN", "RANGE", "NEUTRAL"];

function RegimeField({ value, isOwner, onSave }) {
    const active = Array.isArray(value) ? value : [];
    const toggle = (r) => onSave({ allowed_regimes: active.includes(r) ? active.filter((x) => x !== r) : [...active, r] });
    return (
        <div className="py-2.5">
            <div className="flex items-center justify-between">
                <span className="font-mono text-[12px] text-atlas-textSecondary">Allowed Regimes</span>
                <span data-testid="rm-regimes-count" className="font-mono text-[10px] text-atlas-textTertiary">{active.length ? `${active.length} selected` : "All regimes"}</span>
            </div>
            <div className="label-tag mt-0.5 text-[9px] text-atlas-textTertiary normal-case tracking-normal">Only open entries in these regimes. None selected = trade all.</div>
            <div className="flex flex-wrap gap-1.5 mt-2">
                {REGIMES.map((r) => {
                    const on = active.includes(r);
                    return (
                        <button key={r} type="button" data-testid={`rm-regime-${r}`} disabled={!isOwner} onClick={() => toggle(r)}
                            className={`px-2.5 py-1 rounded-full font-mono text-[10px] border transition-colors disabled:opacity-50 ${on ? "border-atlas-cyan bg-atlas-cyan/15 text-atlas-cyan" : "border-atlas-border text-atlas-textTertiary hover:text-atlas-textSecondary"}`}>
                            {r}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

function ToggleField({ label, desc, k, value, isOwner, onSave }) {
    return (
        <div className="flex items-center justify-between py-2.5 gap-3">
            <div className="min-w-0">
                <div className="font-mono text-[12px] text-atlas-textSecondary">{label}</div>
                {desc && <div className="label-tag mt-0.5 text-[9px] text-atlas-textTertiary normal-case tracking-normal">{desc}</div>}
            </div>
            <Switch data-testid={`rm-toggle-${k}`} checked={!!value} disabled={!isOwner}
                onCheckedChange={(next) => onSave({ [k]: next })} />
        </div>
    );
}

function SummaryRow({ label, value, last }) {
    return (
        <div className={`flex items-center justify-between py-2.5 ${last ? "" : ""}`}>
            <span className="font-mono text-[12px] text-atlas-textSecondary">{label}</span>
            <span className="font-mono text-[13px] font-bold text-atlas-text tabular-nums">{value}</span>
        </div>
    );
}
