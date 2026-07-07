import { useState } from "react";
import { Check, Save, Loader2, TrendingUp, DollarSign } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import LabModal from "@/components/lab/LabModal";

const STRATEGIES = [
    { id: "hunter", label: "Hunter" },
    { id: "squeeze", label: "Volatility Squeeze" },
    { id: "continuation", label: "Continuation" },
];

// Q1 — Entry & Exit Engine. Step 1: pick which live strategies to modify (or all).
// Step 2: ATR trailing stop vs fixed-% stop. Save writes straight to the LIVE engine
// settings (profile_overrides per strategy + global stop/trail) so it reflects in trading.
export default function ExitEngineModal({ open, onOpenChange, settings, onPersist, isOwner }) {
    const s = settings || {};
    const [selected, setSelected] = useState(STRATEGIES.map((x) => x.id));
    const [mode, setMode] = useState(s.dynamic_trail_enabled === false ? "fixed" : "atr");
    // ATR mode
    const [trailMult, setTrailMult] = useState(2.0);
    const [armPct, setArmPct] = useState(s.trail_arm_pct ?? 5);
    const [atrStop, setAtrStop] = useState(s.stop_loss_pct ?? 10);
    // Fixed mode
    const [fixedStop, setFixedStop] = useState(s.stop_loss_pct ?? 10);
    const [fixedArm, setFixedArm] = useState(s.trail_arm_pct ?? 5);
    const [fixedTrail, setFixedTrail] = useState(s.trail_distance_pct ?? 3);
    const [busy, setBusy] = useState(false);

    const toggle = (id) => setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
    const allOn = selected.length === STRATEGIES.length;
    const num = (v, d) => { const n = Number(v); return Number.isNaN(n) ? d : n; };

    const save = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        if (!selected.length) { toast.error("Select at least one strategy"); return; }
        setBusy(true);
        try {
            const overrides = { ...(s.profile_overrides || {}) };
            const patch = {};
            if (mode === "atr") {
                patch.dynamic_trail_enabled = true;
                patch.stop_loss_pct = num(atrStop, 10);
                selected.forEach((st) => {
                    overrides[st] = { ...(overrides[st] || {}), trail_atr_mult: num(trailMult, 2.0), profit_arm_pct: num(armPct, 5) };
                });
            } else {
                patch.dynamic_trail_enabled = false;
                patch.stop_loss_pct = num(fixedStop, 10);
                patch.trail_arm_pct = num(fixedArm, 5);
                patch.trail_distance_pct = num(fixedTrail, 3);
                selected.forEach((st) => {
                    overrides[st] = { ...(overrides[st] || {}), profit_arm_pct: num(fixedArm, 5) };
                });
            }
            patch.profile_overrides = overrides;
            await onPersist(patch);
            toast.success("EXIT ENGINE UPDATED", {
                description: `${mode === "atr" ? "ATR trailing stop" : "Fixed-% stop"} · ${allOn ? "all strategies" : selected.join(", ")}`,
            });
            onOpenChange(false);
        } catch (e) {
            toast.error("SAVE FAILED", { description: String(e?.message || e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <LabModal
            open={open} onOpenChange={onOpenChange} testid="exit-engine-modal"
            icon={TrendingUp} accent="cyan" title="Entry & Exit Engine" subtitle="Position Modifiers"
            footer={
                <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-[10px] text-atlas-textTertiary">Writes to the live engine · redeploy to reach production.</span>
                    <Button data-testid="exit-engine-save-btn" onClick={save} disabled={busy || !isOwner} className="gap-2">
                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        {isOwner ? "SAVE" : "READ-ONLY"}
                    </Button>
                </div>
            }
        >
            {/* Step 1 — strategy targeting */}
            <div>
                <div className="label-tag mb-2">STEP 1 · APPLY TO STRATEGIES</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <button type="button" data-testid="exit-strat-all" onClick={() => setSelected(allOn ? [] : STRATEGIES.map((x) => x.id))}
                        className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border-2 font-mono text-xs transition-all ${allOn ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:bg-atlas-panelHover"}`}>
                        <Check className={`w-3.5 h-3.5 ${allOn ? "opacity-100" : "opacity-30"}`} /> Global (all)
                    </button>
                    {STRATEGIES.map((x) => {
                        const on = selected.includes(x.id);
                        return (
                            <button key={x.id} type="button" data-testid={`exit-strat-${x.id}`} onClick={() => toggle(x.id)}
                                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border-2 font-mono text-xs transition-all ${on ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:bg-atlas-panelHover"}`}>
                                <Check className={`w-3.5 h-3.5 ${on ? "opacity-100" : "opacity-30"}`} /> {x.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Step 2 — exit method */}
            <div className="pt-2">
                <div className="label-tag mb-2">STEP 2 · EXIT METHOD</div>
                <div className="grid grid-cols-2 gap-3">
                    {[
                        { id: "atr", icon: TrendingUp, title: "ATR Trailing Stop", sub: "Volatility-adaptive trail" },
                        { id: "fixed", icon: DollarSign, title: "Fixed-% Stop", sub: "Static stop / trail" },
                    ].map((o) => {
                        const OIcon = o.icon;
                        return (
                            <button key={o.id} type="button" data-testid={`exit-mode-${o.id}`} onClick={() => setMode(o.id)}
                                className={`text-left p-3.5 rounded-xl border-2 transition-all ${mode === o.id ? "border-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border hover:bg-atlas-panelHover"}`}>
                                <OIcon className={`w-4 h-4 mb-1.5 ${mode === o.id ? "text-atlas-cyan" : "text-atlas-textTertiary"}`} />
                                <div className="font-mono text-sm font-bold text-atlas-text">{o.title}</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">{o.sub}</div>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Step 2 fields */}
            {mode === "atr" ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="exit-atr-fields">
                    <NumField id="atr-trail-mult" label="ATR TRAIL MULTIPLIER" value={trailMult} onChange={setTrailMult} step="0.1" min={0.5} hint="Wider = more room" />
                    <NumField id="atr-arm" label="BREAKEVEN ARM (%)" value={armPct} onChange={setArmPct} step="0.5" min={0} hint="MFE% that locks profit" />
                    <NumField id="atr-stop" label="HARD STOP-LOSS (%)" value={atrStop} onChange={setAtrStop} step="0.5" min={0.5} hint="Catastrophe floor" />
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="exit-fixed-fields">
                    <NumField id="fixed-stop" label="STOP-LOSS (%)" value={fixedStop} onChange={setFixedStop} step="0.5" min={0.5} hint="Fixed drawdown exit" />
                    <NumField id="fixed-arm" label="TRAIL ARM (%)" value={fixedArm} onChange={setFixedArm} step="0.5" min={0} hint="Gain that arms the trail" />
                    <NumField id="fixed-trail" label="TRAIL DISTANCE (%)" value={fixedTrail} onChange={setFixedTrail} step="0.5" min={0.1} hint="Pullback-from-peak exit" />
                </div>
            )}
        </LabModal>
    );
}

function NumField({ id, label, value, onChange, step, min, hint }) {
    return (
        <div>
            <Label className="label-tag text-[10px]" htmlFor={`input-${id}`}>{label}</Label>
            <Input id={`input-${id}`} data-testid={`input-${id}`} type="number" step={step} min={min} value={value}
                onChange={(e) => onChange(e.target.value)}
                className="atlas-input rounded-md font-mono mt-1" />
            {hint && <div className="mt-1 font-mono text-[9px] text-atlas-textTertiary">{hint}</div>}
        </div>
    );
}
