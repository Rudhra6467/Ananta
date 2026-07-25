import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Loader2, Sparkles, RotateCcw, ShieldCheck, TrendingUp, TrendingDown, Minimize2, Maximize2, Waves, CircleDot } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const REGIME_META = {
    TREND_UP: { label: "Trend Up", Icon: TrendingUp },
    TREND_DOWN: { label: "Trend Down", Icon: TrendingDown },
    COMPRESSION: { label: "Compression", Icon: Minimize2 },
    RANGE: { label: "Range", Icon: Waves },
    REVERSAL: { label: "Reversal", Icon: Maximize2 },
    NEUTRAL: { label: "Neutral", Icon: CircleDot },
};
const EXIT_LABELS = { atr: "ATR Trailing", fixed: "Fixed TP / SL", native: "Native (engine)" };

/**
 * Strategy Configuration — set the per-strategy identity applied across Live, Paper AND the
 * Research Lab: allowed market regimes + default exit method. Apply Recommended / Reset / Manual.
 */
export function StrategyConfigModal({ open, onClose, strategyKey, strategyName, focus = "regime", isOwner, onSaved }) {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [data, setData] = useState(null);
    const [enabled, setEnabled] = useState(true);
    const [regimes, setRegimes] = useState([]);
    const [exitMethod, setExitMethod] = useState("native");
    const [exitParams, setExitParams] = useState({});

    useEffect(() => {
        if (!open || !strategyKey) return;
        setLoading(true);
        api.strategyProfile(strategyKey)
            .then((d) => { setData(d); hydrate(d.profile); })
            .catch((e) => toast.error("Could not load profile", { description: String(e?.response?.data?.detail || e?.message) }))
            .finally(() => setLoading(false));
    }, [open, strategyKey]);

    const hydrate = (p) => {
        setEnabled(p?.enabled !== false);
        setRegimes(p?.allowed_regimes || []);
        setExitMethod(p?.exit_method || "native");
        setExitParams(p?.exit_params || {});
    };

    const toggleRegime = (r) => setRegimes((cur) => cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]);

    const disabled = enabled === false;
    const statusLabel = disabled ? "Disabled" : (regimes.length === 0 ? "Enabled — all regimes" : "Enabled");

    const applyRecommended = async () => {
        if (!isOwner) return toast.error("Owner login required");
        setSaving(true);
        try {
            const r = await api.strategyProfileApplyRecommended(strategyKey);
            hydrate(r.profile);
            toast.success("Recommended defaults applied", { description: data?.recommended?.note || "" });
        } catch (e) { toast.error("Apply failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setSaving(false); }
    };

    const resetDefaults = async () => {
        if (!isOwner) return toast.error("Owner login required");
        setSaving(true);
        try {
            await api.strategyProfileReset(strategyKey);
            hydrate({ enabled: true, allowed_regimes: [], exit_method: "native", exit_params: {} });
            toast.success("Reset to defaults", { description: "Trades all regimes with the native exit engine." });
            onSaved?.();
        } catch (e) { toast.error("Reset failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setSaving(false); }
    };

    const save = async () => {
        if (!isOwner) return toast.error("Owner login required");
        setSaving(true);
        try {
            const r = await api.strategyProfileSave(strategyKey, {
                enabled, allowed_regimes: regimes, exit_method: exitMethod, exit_params: exitParams,
            });
            toast.success("Strategy configuration saved", { description: r.status?.reason || "" });
            onSaved?.();
            onClose?.();
        } catch (e) { toast.error("Save failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setSaving(false); }
    };

    const rec = data?.recommended;
    const setParam = (k, v) => setExitParams((cur) => ({ ...cur, [k]: v === "" ? undefined : Number(v) }));

    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
            <DialogContent data-testid="strategy-config-modal" className="bg-atlas-panel border-atlas-border text-atlas-text max-w-lg max-h-[88vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-heading text-lg flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-atlas-cyan" /> Strategy Configuration
                    </DialogTitle>
                    <div className="font-mono text-[11px] text-atlas-textSecondary">{strategyName || strategyKey}</div>
                </DialogHeader>

                {loading ? (
                    <div className="py-12 grid place-items-center"><Loader2 className="w-5 h-5 animate-spin text-atlas-cyan" /></div>
                ) : (
                    <div className="space-y-5">
                        {/* status + preset actions */}
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                            <span data-testid="config-status" className={`flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase px-2.5 py-1.5 rounded-lg border ${disabled ? "text-atlas-textTertiary border-atlas-border" : "text-emerald-400 border-emerald-500/40 bg-emerald-500/5"}`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${disabled ? "bg-atlas-textTertiary" : "bg-emerald-400"}`} /> {statusLabel}
                            </span>
                            <div className="flex items-center gap-2">
                                {rec && <button data-testid="config-apply-recommended" onClick={applyRecommended} disabled={saving || !isOwner}
                                    className="flex items-center gap-1.5 rounded-lg border border-atlas-cyan/50 bg-atlas-cyan/10 text-atlas-cyan font-mono text-[10px] font-bold px-2.5 py-1.5 hover:bg-atlas-cyan/20 disabled:opacity-50">
                                    <Sparkles className="w-3 h-3" /> Apply Recommended</button>}
                                <button data-testid="config-reset" onClick={resetDefaults} disabled={saving || !isOwner}
                                    className="flex items-center gap-1.5 rounded-lg border border-atlas-border text-atlas-textSecondary font-mono text-[10px] font-bold px-2.5 py-1.5 hover:text-atlas-text disabled:opacity-50">
                                    <RotateCcw className="w-3 h-3" /> Reset</button>
                            </div>
                        </div>
                        {rec?.note && <div className="font-mono text-[10px] text-atlas-textTertiary -mt-2">Recommended: {rec.allowed_regimes?.join(", ") || "—"} · {EXIT_LABELS[rec.exit_method]} — {rec.note}</div>}

                        {/* enabled toggle */}
                        <label className="flex items-center justify-between gap-3 cursor-pointer">
                            <div>
                                <div className="font-mono text-xs font-bold">Enabled</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary">Off = benched; the engine never evaluates entries.</div>
                            </div>
                            <button data-testid="config-enabled-toggle" onClick={() => setEnabled((v) => !v)}
                                className={`w-11 h-6 rounded-full transition-colors relative ${enabled ? "bg-atlas-cyan" : "bg-atlas-border"}`}>
                                <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${enabled ? "left-[22px]" : "left-0.5"}`} />
                            </button>
                        </label>

                        {/* regime filter */}
                        <div className={`space-y-2 ${!enabled ? "opacity-40 pointer-events-none" : ""}`} data-testid="config-regimes">
                            <div className="label-tag">Regime Filter {focus === "regime" && <span className="text-atlas-cyan">•</span>}</div>
                            <div className="font-mono text-[10px] text-atlas-textTertiary">Select the market conditions this strategy may trade. None selected = all regimes.</div>
                            <div className="grid grid-cols-3 gap-2">
                                {(data?.regimes || []).map((r) => {
                                    const M = REGIME_META[r] || { label: r, Icon: CircleDot };
                                    const on = regimes.includes(r);
                                    return (
                                        <button key={r} data-testid={`config-regime-${r}`} onClick={() => toggleRegime(r)}
                                            className={`flex flex-col items-center gap-1 rounded-xl border py-2.5 font-mono text-[9px] font-bold transition-all ${on ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textTertiary hover:text-atlas-text"}`}>
                                            <M.Icon className="w-4 h-4" /> {M.label}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* exit method */}
                        <div className={`space-y-2 ${!enabled ? "opacity-40 pointer-events-none" : ""}`} data-testid="config-exit">
                            <div className="label-tag">Default Exit {focus === "exit" && <span className="text-atlas-cyan">•</span>}</div>
                            <div className="grid grid-cols-3 gap-2">
                                {Object.keys(data?.exit_methods || EXIT_LABELS).map((m) => (
                                    <button key={m} data-testid={`config-exit-${m}`} onClick={() => setExitMethod(m)}
                                        className={`rounded-xl border py-2.5 font-mono text-[10px] font-bold transition-all ${exitMethod === m ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textTertiary hover:text-atlas-text"}`}>
                                        {EXIT_LABELS[m] || m}
                                    </button>
                                ))}
                            </div>
                            {exitMethod === "atr" && (
                                <ParamRow label="ATR Multiplier" testid="config-atr-mult" value={exitParams.atr_multiplier ?? ""} onChange={(v) => setParam("atr_multiplier", v)} placeholder="2.5" />
                            )}
                            {exitMethod === "fixed" && (
                                <div className="grid grid-cols-2 gap-2">
                                    <ParamRow label="Take Profit %" testid="config-tp" value={exitParams.target_profit ?? ""} onChange={(v) => setParam("target_profit", v)} placeholder="5.0" />
                                    <ParamRow label="Stop Loss %" testid="config-sl" value={exitParams.target_loss ?? ""} onChange={(v) => setParam("target_loss", v)} placeholder="4.0" />
                                </div>
                            )}
                        </div>

                        <button data-testid="config-save" onClick={save} disabled={saving || !isOwner}
                            className="w-full flex items-center justify-center gap-2 rounded-xl bg-atlas-cyan text-atlas-bg font-mono text-xs font-bold tracking-wide py-3.5 hover:brightness-110 active:scale-[0.99] transition-all disabled:opacity-50">
                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />} Save Configuration
                        </button>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

function ParamRow({ label, value, onChange, placeholder, testid }) {
    return (
        <div>
            <div className="font-mono text-[10px] text-atlas-textTertiary mb-1">{label}</div>
            <input data-testid={testid} type="number" step="0.1" value={value} placeholder={placeholder}
                onChange={(e) => onChange(e.target.value)}
                className="w-full bg-atlas-bg border border-atlas-border rounded-lg px-3 py-2 font-mono text-xs text-atlas-text focus:border-atlas-cyan outline-none" />
        </div>
    );
}
