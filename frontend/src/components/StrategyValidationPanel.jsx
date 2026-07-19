import { useEffect, useMemo, useState } from "react";
import { FlaskConical, Play, Download, Loader2, Sparkles, SlidersHorizontal, Rocket, Check, X, Trash2, ChevronDown, ChevronRight, Save, Trophy } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";

// The three native strategies the replay engine can run. "Select all" = run every one.
const STRATEGIES = [
    { id: "hunter", label: "Hunter" },
    { id: "squeeze", label: "Volatility Squeeze" },
    { id: "continuation", label: "Continuation" },
];
const ALL_STRATEGY_IDS = STRATEGIES.map((s) => s.id);

// Parameter presets for the "Fresh Values" optimization sandbox. Keys map to the
// backend grid targets ("prof:<strategy>:<field>" or "set:<field>").
const PARAMS = [
    { key: "prof:squeeze:trail_atr_mult", label: "Squeeze — ATR Trail Multiple", def: "2.0, 2.25, 2.5, 2.75" },
    { key: "prof:hunter:trail_atr_mult", label: "Hunter — ATR Trail Multiple", def: "1.6, 1.8, 2.0, 2.2, 2.4" },
    { key: "prof:hunter:profit_arm_pct", label: "Hunter — Profit-Lock Threshold %", def: "4, 5, 6" },
    { key: "prof:squeeze:profit_arm_pct", label: "Squeeze — Profit-Lock Threshold %", def: "3, 4, 5" },
    { key: "set:stop_loss_pct", label: "Global — Stop-Loss %", def: "8, 10, 12" },
];

const STATUS_CLS = {
    QUEUED: "text-atlas-textSecondary", RUNNING: "text-atlas-cyan",
    DONE: "text-atlas-positive", FAILED: "text-atlas-negative",
};

// Module-level cache: coverage/presets are effectively static for a session and runs
// rarely change — caching them means re-opening the Research Lab tab is INSTANT and never
// "loads afresh" or gets stuck when the user hasn't changed anything. Runs still refresh
// silently in the background (and while a job is active).
const ATR_DEFAULTS = { multiplier: 2.5, period: 14, trail_activation_pct: 3, trail_distance: 2 };
const _labCache = {
    cov: null, presets: null, runs: null, assets: null, period: null, strategies: null,
    compareTf: false, exitMethod: "fixed", targetProfit: 5, targetLoss: 4, useLive: true,
    atrParams: { ...ATR_DEFAULTS }, positionSize: 75,
};

export default function StrategyValidationPanel() {
    const [cov, setCov] = useState(_labCache.cov);
    const [assets, setAssets] = useState(_labCache.assets || []);
    const [period, setPeriod] = useState(_labCache.period || "3m");
    const [strategies, setStrategies] = useState(_labCache.strategies || ALL_STRATEGY_IDS);
    const [compareTf, setCompareTf] = useState(_labCache.compareTf || false);
    const [exitMethod, setExitMethod] = useState(_labCache.exitMethod || "fixed");
    const [targetProfit, setTargetProfit] = useState(_labCache.targetProfit ?? 5);
    const [targetLoss, setTargetLoss] = useState(_labCache.targetLoss ?? 4);
    const [useLive, setUseLive] = useState(_labCache.useLive ?? true);
    const [atrParams, setAtrParams] = useState(_labCache.atrParams || { ...ATR_DEFAULTS });
    const [positionSize, setPositionSize] = useState(_labCache.positionSize || 75);
    const [showFixedAdv, setShowFixedAdv] = useState(false); // collapsed by default
    const [showAtrAdv, setShowAtrAdv] = useState(false); // collapsed by default
    const [runs, setRuns] = useState(_labCache.runs || []);
    const [open, setOpen] = useState(false);
    const [track, setTrack] = useState("current");
    const [param, setParam] = useState(PARAMS[0].key);
    const [values, setValues] = useState(PARAMS[0].def);
    const [folds, setFolds] = useState(4);
    const [busy, setBusy] = useState(false);
    const [dl, setDl] = useState(null);
    const [proposal, setProposal] = useState(null);
    const [promoteBusy, setPromoteBusy] = useState(false);
    const [deleting, setDeleting] = useState(null);
    const [presets, setPresets] = useState(_labCache.presets || []);
    const [presetId, setPresetId] = useState(_labCache.presets?.[0]?.id || "");
    // Save-winning-config flow (bridge into the Strategy Config engine)
    const [saveTarget, setSaveTarget] = useState(null); // { run, symbol, timeframe, winnerKey, winnerLabel }
    const [saveStrategy, setSaveStrategy] = useState("hunter");
    const [saveName, setSaveName] = useState("");
    const [saveBusy, setSaveBusy] = useState(false);

    const openSave = (target) => {
        setSaveTarget(target);
        // default the config's strategy to the run's sole strategy (else Hunter)
        const strats = target?.run?.strategies || [];
        setSaveStrategy(strats.length === 1 ? strats[0] : "hunter");
        setSaveName("");
    };

    const submitSave = async () => {
        if (!saveTarget) return;
        setSaveBusy(true);
        try {
            const res = await api.strategyConfigFromLabRun({
                run_id: saveTarget.run.id,
                strategy_key: saveStrategy,
                symbol: saveTarget.symbol,
                timeframe: saveTarget.timeframe,
                name: saveName.trim() || undefined,
            });
            toast.success("CONFIG SAVED", {
                description: `${res.config.name} → strategy_configs (${res.config.rating?.stars ?? "?"}★)`,
            });
            setSaveTarget(null);
        } catch (e) {
            toast.error("SAVE FAILED", { description: String(e?.response?.data?.detail || e?.message || e) });
        } finally {
            setSaveBusy(false);
        }
    };

    const loadRuns = () => api.labRuns(12).then((d) => {
        _labCache.runs = d.runs || [];
        setRuns(_labCache.runs);
    }).catch(() => {});

    const deleteRun = async (id) => {
        setDeleting(id);
        try {
            await api.deleteLabRun(id);
            _labCache.runs = (_labCache.runs || []).filter((r) => r.id !== id);
            setRuns((prev) => prev.filter((r) => r.id !== id));
            toast.success("RECORD DELETED", { description: `Run ${id.slice(0, 8)} removed` });
        } catch (_) {
            toast.error("DELETE FAILED", { description: "Could not remove the record" });
        } finally {
            setDeleting(null);
        }
    };

    useEffect(() => {
        // coverage — fetch only once per session; reuse cache on subsequent tab visits
        if (!_labCache.cov) {
            api.labCoverage().then((c) => {
                _labCache.cov = c;
                setCov(c);
                if (!_labCache.assets) {
                    const avail = (c.symbols || []).filter((s) => s.bars_1h > 0).map((s) => s.symbol).slice(0, 3);
                    _labCache.assets = avail;
                    setAssets(avail);
                }
            }).catch(() => {});
        }
        // presets — static, fetch once
        if (!_labCache.presets) {
            api.labPresets().then((d) => {
                _labCache.presets = d.presets || [];
                setPresets(_labCache.presets);
                if (_labCache.presets.length) setPresetId(_labCache.presets[0].id);
            }).catch(() => {});
        }
        // runs — silent background refresh (no spinner, cached list shows instantly)
        loadRuns();
        // position size (lot) — for the live risk/reward % calculator on fixed-$ targets
        api.settings().then((st) => {
            const lot = Number(st?.normal_lot_usd);
            if (lot > 0) { _labCache.positionSize = lot; setPositionSize(lot); }
        }).catch(() => {});
    }, []);

    // keep the user's asset/period/strategy selection across tab switches
    const chooseAssets = (next) => { _labCache.assets = next; setAssets(next); };
    const choosePeriod = (next) => { _labCache.period = next; setPeriod(next); };
    const chooseStrategies = (next) => { _labCache.strategies = next; setStrategies(next); };
    const chooseCompareTf = (next) => { _labCache.compareTf = next; setCompareTf(next); };
    const chooseExitMethod = (next) => { _labCache.exitMethod = next; setExitMethod(next); };
    const chooseUseLive = (v) => { _labCache.useLive = v; setUseLive(v); };
    const chooseTargetProfit = (next) => { _labCache.targetProfit = next; setTargetProfit(next); };
    const chooseTargetLoss = (next) => { _labCache.targetLoss = next; setTargetLoss(next); };
    const chooseAtrParam = (key, val) => {
        const next = { ...atrParams, [key]: val };
        _labCache.atrParams = next; setAtrParams(next);
    };

    // poll while any run is active
    useEffect(() => {
        const active = runs.some((r) => r.status === "QUEUED" || r.status === "RUNNING");
        if (!active) return;
        const t = setInterval(loadRuns, 2500);
        return () => clearInterval(t);
    }, [runs]);

    const symbols = useMemo(() => (cov?.symbols || []).filter((s) => s.bars_1h > 0), [cov]);
    const periods = cov?.periods || ["1m", "2m", "3m", "quarter", "6m", "1y", "2y", "custom"];

    const toggleAsset = (sym) =>
        chooseAssets(assets.includes(sym) ? assets.filter((x) => x !== sym) : [...assets, sym]);

    const onPickParam = (k) => {
        setParam(k);
        setValues(PARAMS.find((p) => p.key === k)?.def || "");
    };

    const submit = async () => {
        if (!assets.length) { toast.error("Select at least one asset"); return; }
        if (!strategies.length) { toast.error("Select at least one strategy"); return; }
        setBusy(true);
        try {
            const common = {
                symbols: assets, period, strategies, compare_timeframes: compareTf,
                exit_method: exitMethod,
                target_profit: Number(targetProfit) || 5,
                target_loss: Number(targetLoss) || 4,
                atr_params: exitMethod === "atr" ? {
                    multiplier: Number(atrParams.multiplier) || ATR_DEFAULTS.multiplier,
                    period: Number(atrParams.period) || ATR_DEFAULTS.period,
                    trail_activation_pct: Number(atrParams.trail_activation_pct) || ATR_DEFAULTS.trail_activation_pct,
                    trail_distance: Number(atrParams.trail_distance) || ATR_DEFAULTS.trail_distance,
                } : null,
            };
            let spec;
            if (track === "current") {
                spec = useLive
                    ? { kind: "backtest", symbols: assets, period, strategies, compare_timeframes: compareTf, use_live_exit_settings: true }
                    : { kind: "backtest", ...common };
            } else if (track === "presets") {
                if (!presetId) { toast.error("Pick a preset"); setBusy(false); return; }
                spec = { kind: "backtest", ...common, preset: presetId };
            } else {
                const vals = values.split(",").map((v) => parseFloat(v.trim())).filter((v) => !Number.isNaN(v));
                if (vals.length < 2) { toast.error("Enter at least 2 comma-separated values"); setBusy(false); return; }
                spec = {
                    kind: "walk_forward", ...common,
                    grid: { [param]: vals }, folds: Number(folds) || 4,
                    metric: "total_return_pct", min_trades: 3,
                    label: `Fresh: ${PARAMS.find((p) => p.key === param)?.label}`,
                };
            }
            const res = await api.labCreateRun(spec);
            toast.success("VALIDATION QUEUED", { description: `${res.kind} · run ${res.id.slice(0, 8)}` });
            setOpen(false);
            loadRuns();
        } catch (e) {
            toast.error("QUEUE FAILED", { description: String(e?.response?.data?.detail || e?.message || e) });
        } finally {
            setBusy(false);
        }
    };

    const downloadPdf = async (id) => {
        setDl(id);
        try {
            const blob = await api.labRunPdf(id);
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `ananta_lab_${id.slice(0, 8)}.pdf`;
            document.body.appendChild(a); a.click(); a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            toast.error("PDF UNAVAILABLE", { description: String(e?.response?.data?.detail || e) });
        } finally {
            setDl(null);
        }
    };

    const promote = async (runId) => {
        setPromoteBusy(true);
        try {
            const p = await api.labPropose(runId);
            setProposal(p);
        } catch (e) {
            toast.error("PROMOTE FAILED", { description: String(e?.response?.data?.detail || e) });
        } finally {
            setPromoteBusy(false);
        }
    };

    const applyProposal = async () => {
        if (!proposal) return;
        setPromoteBusy(true);
        try {
            const res = await api.labApplyProposal(proposal.id);
            toast.success("APPLIED TO PRODUCTION", {
                description: `${(res.applied || []).map((c) => `${c.target} → ${c.value}`).join(", ")} · redeploy to go live`,
            });
            setProposal(null);
        } catch (e) {
            toast.error("APPLY FAILED", { description: String(e?.response?.data?.detail || e) });
        } finally {
            setPromoteBusy(false);
        }
    };

    const rejectProposal = async () => {
        if (!proposal) return;
        try { await api.labRejectProposal(proposal.id); } catch (_) { /* noop */ }
        setProposal(null);
    };

    return (
        <section className="panel p-6 md:p-8" data-testid="strategy-validation-panel">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                    <FlaskConical className="w-5 h-5 text-atlas-cyan" strokeWidth={2} />
                    <div>
                        <div className="font-heading font-medium text-lg text-atlas-text">STRATEGY VALIDATION</div>
                        <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-0.5">
                            Offline simulation · $1,200 baseline · parity with the live engine · credit-free
                        </div>
                    </div>
                </div>
                <Dialog open={open} onOpenChange={setOpen}>
                    <DialogTrigger asChild>
                        <Button data-testid="run-validation-btn" className="gap-2" disabled={!assets.length}>
                            <Play className="w-4 h-4" /> RUN VALIDATION
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="bg-atlas-panel border-atlas-border max-w-lg" data-testid="validation-dialog">
                        <DialogHeader>
                            <DialogTitle className="font-heading tracking-wide">CHOOSE VALIDATION TRACK</DialogTitle>
                        </DialogHeader>
                        <div className="grid grid-cols-3 gap-3 mt-2">
                            <button data-testid="track-current"
                                onClick={() => setTrack("current")}
                                className={`text-left p-4 rounded-lg border-2 transition-all ${track === "current" ? "border-atlas-cyan bg-atlas-panelHover" : "border-atlas-border hover:bg-atlas-panelHover"}`}>
                                <Sparkles className="w-4 h-4 text-atlas-cyan mb-2" />
                                <div className="font-mono text-sm font-bold text-atlas-text">A · Current Prod</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary mt-1">Live production parameters vs past regimes.</div>
                            </button>
                            <button data-testid="track-fresh"
                                onClick={() => setTrack("fresh")}
                                className={`text-left p-4 rounded-lg border-2 transition-all ${track === "fresh" ? "border-atlas-cyan bg-atlas-panelHover" : "border-atlas-border hover:bg-atlas-panelHover"}`}>
                                <SlidersHorizontal className="w-4 h-4 text-atlas-cyan mb-2" />
                                <div className="font-mono text-sm font-bold text-atlas-text">B · Param Opt</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary mt-1">Sweep a param · rolling In-Sample→Out-of-Sample.</div>
                            </button>
                            <button data-testid="track-presets"
                                onClick={() => setTrack("presets")}
                                className={`text-left p-4 rounded-lg border-2 transition-all ${track === "presets" ? "border-atlas-cyan bg-atlas-panelHover" : "border-atlas-border hover:bg-atlas-panelHover"}`}>
                                <FlaskConical className="w-4 h-4 text-atlas-cyan mb-2" />
                                <div className="font-mono text-sm font-bold text-atlas-text">C · Presets</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary mt-1">Test a canned strategy personality in one click.</div>
                            </button>
                        </div>

                        {track === "presets" && (
                            <div className="space-y-3 mt-2 pt-3 border-t border-atlas-border" data-testid="presets-config">
                                <div>
                                    <Label className="label-tag text-[10px]">PRESET</Label>
                                    <select data-testid="preset-select" value={presetId} onChange={(e) => setPresetId(e.target.value)}
                                        className="w-full mt-1 bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-sm text-atlas-text">
                                        {presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                                    </select>
                                </div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary leading-relaxed" data-testid="preset-desc">
                                    {presets.find((p) => p.id === presetId)?.description || ""}
                                </div>
                            </div>
                        )}

                        {track === "fresh" && (
                            <div className="space-y-3 mt-2 pt-3 border-t border-atlas-border" data-testid="fresh-values-config">
                                <div>
                                    <Label className="label-tag text-[10px]">PARAMETER</Label>
                                    <select data-testid="param-select" value={param} onChange={(e) => onPickParam(e.target.value)}
                                        className="w-full mt-1 bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-sm text-atlas-text">
                                        {PARAMS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                                    </select>
                                </div>
                                <div className="grid grid-cols-3 gap-3">
                                    <div className="col-span-2">
                                        <Label className="label-tag text-[10px]">CANDIDATE VALUES</Label>
                                        <Input data-testid="values-input" value={values} onChange={(e) => setValues(e.target.value)}
                                            className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" placeholder="2.0, 2.5, 3.0" />
                                    </div>
                                    <div>
                                        <Label className="label-tag text-[10px]">FOLDS</Label>
                                        <Input data-testid="folds-input" type="number" min={2} max={8} value={folds}
                                            onChange={(e) => setFolds(e.target.value)}
                                            className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" />
                                    </div>
                                </div>
                            </div>
                        )}

                        {track !== "fresh" && (
                            <div className="mt-4 pt-3 border-t border-atlas-border" data-testid="exit-logic-config">
                                {track === "current" && (
                                    <label data-testid="use-live-exit-toggle" className="flex items-start gap-3 p-3 mb-3 rounded-lg border border-atlas-cyan/40 bg-atlas-cyan/5 cursor-pointer">
                                        <Switch data-testid="use-live-exit-switch" checked={useLive} onCheckedChange={chooseUseLive} className="mt-0.5" />
                                        <span className="flex-1">
                                            <span className="font-mono text-xs font-bold text-atlas-text">Use my live Exit Engine settings</span>
                                            <span className="block font-mono text-[10px] text-atlas-textTertiary mt-0.5">
                                                {useLive
                                                    ? "Backtest replays through your DEPLOYED exit config (method + per-strategy & per-coin overrides) — results match paper/live."
                                                    : "Manual override — choose an exit below to A/B test different rules."}
                                            </span>
                                        </span>
                                    </label>
                                )}
                                {!(track === "current" && useLive) && (<>
                                <Label className="label-tag text-[10px]">EXIT STRATEGY</Label>
                                <div className="grid grid-cols-3 gap-2 mt-1.5">
                                    {[
                                        { id: "native", title: "Native Strategy", sub: "Each strategy's own exit" },
                                        { id: "atr", title: "ATR Exit", sub: "ATR trailing stop" },
                                        { id: "fixed", title: "Fixed $ Target", sub: "Fixed profit / loss" },
                                    ].map((o) => (
                                        <button key={o.id} type="button" data-testid={`exit-method-${o.id}`} onClick={() => chooseExitMethod(o.id)}
                                            className={`text-left p-2.5 rounded-lg border-2 transition-all ${exitMethod === o.id ? "border-atlas-cyan bg-atlas-panelHover" : "border-atlas-border hover:bg-atlas-panelHover"}`}>
                                            <div className="font-mono text-[11px] font-bold text-atlas-text">{o.title}</div>
                                            <div className="font-mono text-[9px] text-atlas-textTertiary mt-0.5 leading-tight">{o.sub}</div>
                                        </button>
                                    ))}
                                </div>

                                {/* ATR advanced settings — collapsed by default, only for ATR */}
                                {exitMethod === "atr" && (
                                    <div className="mt-2">
                                        <button type="button" data-testid="atr-adv-toggle" onClick={() => setShowAtrAdv((v) => !v)}
                                            className="w-full flex items-center gap-1.5 font-mono text-[11px] text-atlas-textTertiary hover:text-atlas-cyan transition-colors">
                                            {showAtrAdv ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                                            Advanced settings
                                            {!showAtrAdv && <span className="text-atlas-textTertiary/70">&nbsp;(×{atrParams.multiplier}, {atrParams.period}p, arm {atrParams.trail_activation_pct}%, trail ×{atrParams.trail_distance})</span>}
                                        </button>
                                        {showAtrAdv && (
                                            <div className="grid grid-cols-2 gap-3 mt-2" data-testid="atr-adv-panel">
                                                <div>
                                                    <Label className="label-tag text-[10px]">ATR MULTIPLIER</Label>
                                                    <Input data-testid="atr-multiplier-input" type="number" min={0.5} step="0.1" value={atrParams.multiplier}
                                                        onChange={(e) => chooseAtrParam("multiplier", e.target.value)}
                                                        className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" />
                                                </div>
                                                <div>
                                                    <Label className="label-tag text-[10px]">ATR PERIOD</Label>
                                                    <Input data-testid="atr-period-input" type="number" min={2} step="1" value={atrParams.period}
                                                        onChange={(e) => chooseAtrParam("period", e.target.value)}
                                                        className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" />
                                                </div>
                                                <div>
                                                    <Label className="label-tag text-[10px]">TRAIL ACTIVATION (%)</Label>
                                                    <Input data-testid="atr-trail-activation-input" type="number" min={0} step="0.5" value={atrParams.trail_activation_pct}
                                                        onChange={(e) => chooseAtrParam("trail_activation_pct", e.target.value)}
                                                        className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" />
                                                </div>
                                                <div>
                                                    <Label className="label-tag text-[10px]">TRAIL DISTANCE (ATR)</Label>
                                                    <Input data-testid="atr-trail-distance-input" type="number" min={0.5} step="0.1" value={atrParams.trail_distance}
                                                        onChange={(e) => chooseAtrParam("trail_distance", e.target.value)}
                                                        className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" />
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Fixed $ advanced settings — collapsed by default, only for Fixed */}
                                {exitMethod === "fixed" && (
                                    <div className="mt-2">
                                        <button type="button" data-testid="fixed-adv-toggle" onClick={() => setShowFixedAdv((v) => !v)}
                                            className="w-full flex items-center gap-1.5 font-mono text-[11px] text-atlas-textTertiary hover:text-atlas-cyan transition-colors">
                                            {showFixedAdv ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                                            Advanced settings
                                            {!showFixedAdv && <span className="text-atlas-textTertiary/70">&nbsp;(TP ${targetProfit || 5} / SL ${targetLoss || 4})</span>}
                                        </button>
                                        {showFixedAdv && (
                                            <div className="grid grid-cols-2 gap-3 mt-2" data-testid="fixed-adv-panel">
                                                <div>
                                                    <Label className="label-tag text-[10px]">PROFIT TARGET ($)</Label>
                                                    <Input data-testid="target-profit-input" type="number" min={0} step="0.5" value={targetProfit}
                                                        onChange={(e) => chooseTargetProfit(e.target.value)}
                                                        className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" />
                                                    <div className="font-mono text-[10px] text-atlas-cyan mt-1" data-testid="profit-pct-hint">
                                                        &asymp; {positionSize > 0 ? ((Number(targetProfit) || 0) / positionSize * 100).toFixed(2) : "0.00"}% of trade value
                                                    </div>
                                                </div>
                                                <div>
                                                    <Label className="label-tag text-[10px]">STOP LOSS ($)</Label>
                                                    <Input data-testid="target-loss-input" type="number" min={0} step="0.5" value={targetLoss}
                                                        onChange={(e) => chooseTargetLoss(e.target.value)}
                                                        className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" />
                                                    <div className="font-mono text-[10px] text-atlas-cyan mt-1" data-testid="loss-pct-hint">
                                                        &asymp; {positionSize > 0 ? ((Number(targetLoss) || 0) / positionSize * 100).toFixed(2) : "0.00"}% of trade value
                                                    </div>
                                                </div>
                                                <div className="col-span-2 font-mono text-[9px] text-atlas-textTertiary">
                                                    Position size ${positionSize} · percentages update live as you edit.
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                                </>)}
                            </div>
                        )}

                        <label data-testid="compare-tf-toggle" className="flex items-start gap-2.5 mt-4 p-3 rounded-lg border border-atlas-border cursor-pointer hover:bg-atlas-panelHover transition-colors">
                            <input type="checkbox" checked={compareTf} onChange={(e) => chooseCompareTf(e.target.checked)}
                                className="mt-0.5 h-4 w-4 accent-atlas-cyan" data-testid="compare-tf-checkbox" />
                            <span>
                                <span className="font-mono text-xs font-bold text-atlas-text">Compare 30m &amp; 15m timeframes</span>
                                <span className="block font-mono text-[10px] text-atlas-textTertiary mt-0.5">
                                    Off = 1h only (live-parity, fastest). On = also replays 30m/15m for the multi-timeframe report — ~3× slower.
                                </span>
                            </span>
                        </label>

                        <Button data-testid="submit-validation-btn" onClick={submit} disabled={busy || !assets.length || !strategies.length} className="w-full mt-3 gap-2">
                            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                            {track === "current" ? "RUN CURRENT-PROD BACKTEST"
                                : track === "presets" ? "RUN PRESET BACKTEST"
                                    : "RUN WALK-FORWARD VALIDATION"}
                        </Button>
                    </DialogContent>
                </Dialog>
            </div>

            {/* config: strategy · assets · period — three compact dropdowns */}
            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="validation-config">
                <div>
                    <Label className="label-tag text-[10px]">STRATEGY · {strategies.length === ALL_STRATEGY_IDS.length ? "all" : `${strategies.length} selected`}</Label>
                    <MultiSelect
                        testid="strategy-select"
                        summary={strategies.length === ALL_STRATEGY_IDS.length ? "All strategies"
                            : strategies.length === 0 ? "None"
                                : strategies.length === 1 ? STRATEGIES.find((s) => s.id === strategies[0])?.label
                                    : `${strategies.length} selected`}
                        allOn={strategies.length === ALL_STRATEGY_IDS.length}
                        onToggleAll={() => chooseStrategies(strategies.length === ALL_STRATEGY_IDS.length ? [] : ALL_STRATEGY_IDS)}
                        options={STRATEGIES.map((s) => ({
                            key: s.id, label: s.label, on: strategies.includes(s.id),
                            onToggle: () => chooseStrategies(strategies.includes(s.id) ? strategies.filter((x) => x !== s.id) : [...strategies, s.id]),
                        }))}
                    />
                </div>
                <div>
                    <Label className="label-tag text-[10px]">ASSETS · {assets.length} selected</Label>
                    <MultiSelect
                        testid="asset-select"
                        disabled={symbols.length === 0}
                        summary={symbols.length === 0 ? "No history seeded"
                            : assets.length === 0 ? "Select assets"
                                : assets.length === symbols.length ? "All assets"
                                    : assets.length === 1 ? assets[0].split("/")[0]
                                        : `${assets.length} selected`}
                        allOn={symbols.length > 0 && assets.length === symbols.length}
                        onToggleAll={() => chooseAssets(assets.length === symbols.length ? [] : symbols.map((s) => s.symbol))}
                        options={symbols.map((s) => ({
                            key: s.symbol, label: s.symbol.split("/")[0], meta: `${s.bars_1h}`,
                            on: assets.includes(s.symbol), onToggle: () => toggleAsset(s.symbol),
                        }))}
                    />
                </div>
                <div>
                    <Label className="label-tag text-[10px]">HISTORICAL PERIOD</Label>
                    <select data-testid="period-select" value={period} onChange={(e) => choosePeriod(e.target.value)}
                        className="w-full mt-2 bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-sm text-atlas-text h-[38px]">
                        {periods.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                </div>
            </div>

            {/* runs */}
            <div className="mt-8">
                <div className="label-tag mb-3">VALIDATION RUNS</div>
                {runs.length === 0 ? (
                    <div className="p-6 text-center font-mono text-xs text-atlas-textSecondary border border-atlas-border rounded-lg" data-testid="runs-empty">
                        No runs yet. Configure assets and hit RUN VALIDATION.
                    </div>
                ) : (
                    <div className="space-y-2" data-testid="runs-list">
                        {runs.map((r) => <RunRow key={r.id} run={r} onDownload={downloadPdf} downloading={dl === r.id}
                            onPromote={promote} promoting={promoteBusy} onDelete={deleteRun} deleting={deleting === r.id}
                            onSaveConfig={openSave} />)}
                    </div>
                )}
            </div>

            {/* Promote-to-Production approval gate */}
            <Dialog open={!!proposal} onOpenChange={(o) => { if (!o) setProposal(null); }}>
                <DialogContent className="bg-atlas-panel border-atlas-border max-w-lg" data-testid="promote-dialog">
                    <DialogHeader>
                        <DialogTitle className="font-heading tracking-wide flex items-center gap-2">
                            <Rocket className="w-4 h-4 text-atlas-cyan" /> PROMOTE TO PRODUCTION
                        </DialogTitle>
                    </DialogHeader>
                    <div className="font-mono text-[11px] text-atlas-textTertiary">
                        Review the change below. Nothing is applied until you confirm — and it only goes live
                        after you redeploy the backend.
                    </div>
                    <div className="mt-3 space-y-2" data-testid="promote-diff">
                        {(proposal?.diff || []).map((d) => (
                            <div key={d.key} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border border-atlas-border">
                                <span className="font-mono text-xs text-atlas-text">{d.target}</span>
                                <span className="font-mono text-xs">
                                    <span className="text-atlas-textSecondary">{String(d.current)}</span>
                                    <span className="text-atlas-textTertiary mx-2">→</span>
                                    <span className="text-atlas-positive font-bold">{String(d.proposed)}</span>
                                </span>
                            </div>
                        ))}
                    </div>
                    <div className="flex gap-3 mt-4">
                        <Button data-testid="apply-proposal-btn" onClick={applyProposal} disabled={promoteBusy} className="flex-1 gap-2">
                            {promoteBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} APPLY TO PRODUCTION
                        </Button>
                        <Button data-testid="reject-proposal-btn" variant="outline" onClick={rejectProposal} disabled={promoteBusy} className="gap-2">
                            <X className="w-4 h-4" /> REJECT
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Save-winning-config bridge → Strategy Config engine */}
            <Dialog open={!!saveTarget} onOpenChange={(o) => { if (!o) setSaveTarget(null); }}>
                <DialogContent className="bg-atlas-panel border-atlas-border max-w-md" data-testid="save-config-dialog">
                    <DialogHeader>
                        <DialogTitle className="font-heading tracking-wide flex items-center gap-2">
                            <Trophy className="w-4 h-4 text-atlas-cyan" /> SAVE WINNING CONFIG
                        </DialogTitle>
                    </DialogHeader>
                    <div className="font-mono text-[11px] text-atlas-textTertiary">
                        Promote the winning exit configuration from this run into a reusable, rateable
                        Strategy Config (origin&nbsp;=&nbsp;optimizer). It becomes selectable across the platform.
                    </div>
                    {saveTarget && (
                        <div className="mt-3 space-y-3">
                            <div className="px-3 py-2 rounded-lg border border-atlas-cyan/30 bg-atlas-cyan/5 font-mono text-[11px]" data-testid="save-config-winner">
                                <div className="text-atlas-textTertiary">Winner · {saveTarget.symbol} · {saveTarget.timeframe}</div>
                                <div className="text-atlas-cyan font-bold mt-0.5">{saveTarget.winnerLabel}</div>
                            </div>
                            <div>
                                <Label className="label-tag text-[10px]">ATTACH TO STRATEGY</Label>
                                <select data-testid="save-config-strategy" value={saveStrategy} onChange={(e) => setSaveStrategy(e.target.value)}
                                    className="w-full mt-1 bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-sm text-atlas-text">
                                    {STRATEGIES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                                </select>
                            </div>
                            <div>
                                <Label className="label-tag text-[10px]">CONFIG NAME (optional)</Label>
                                <Input data-testid="save-config-name" value={saveName} onChange={(e) => setSaveName(e.target.value)}
                                    className="font-mono text-sm bg-atlas-panel border-atlas-border mt-1" placeholder="Auto-generated if blank" />
                            </div>
                        </div>
                    )}
                    <Button data-testid="save-config-submit-btn" onClick={submitSave} disabled={saveBusy} className="w-full mt-4 gap-2">
                        {saveBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} SAVE CONFIGURATION
                    </Button>
                </DialogContent>
            </Dialog>
        </section>
    );
}

function RunRow({ run, onDownload, downloading, onPromote, promoting, onDelete, deleting, onSaveConfig }) {
    const isDone = run.status === "DONE";
    const isTerminal = isDone || run.status === "FAILED";
    const canPromote = isDone && run.kind !== "backtest";
    const winner = isDone && run.kind === "backtest" && run.exit_winner
        ? { symbol: run.exit_winner.symbol, timeframe: run.exit_winner.timeframe,
            winnerKey: run.exit_winner.winner_key, winnerLabel: run.exit_winner.winner_label }
        : null;
    const summary = runSummary(run);
    const [expanded, setExpanded] = useState(false);
    const [detail, setDetail] = useState(null);
    const [loadingDetail, setLoadingDetail] = useState(false);

    const toggle = async () => {
        const next = !expanded;
        setExpanded(next);
        if (next && !detail) {
            setLoadingDetail(true);
            try { setDetail(await api.labRun(run.id)); } catch (_) { /* noop */ }
            finally { setLoadingDetail(false); }
        }
    };

    return (
        <div className="border border-atlas-border rounded-lg p-4 bg-atlas-panel" data-testid={`run-row-${run.id.slice(0, 8)}`}>
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-3 min-w-0">
                    {isDone && run.kind === "backtest" && (
                        <button data-testid={`expand-run-${run.id.slice(0, 8)}`} onClick={toggle}
                            className="text-atlas-textTertiary hover:text-atlas-cyan">
                            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        </button>
                    )}
                    <span className="font-mono text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border border-atlas-border text-atlas-textSecondary">{run.kind}</span>
                    {run.exit_method && (
                        <span data-testid={`run-exit-${run.id.slice(0, 8)}`}
                            className="font-mono text-[10px] px-2 py-0.5 rounded border border-atlas-cyan/40 text-atlas-cyan whitespace-nowrap">
                            {run.exit_method === "fixed" ? `Fixed $${run.target_profit ?? 5}/$${run.target_loss ?? 4}`
                                : run.exit_method === "atr" ? "ATR exit"
                                    : "Native exit"}
                        </span>
                    )}
                    <span className="font-mono text-xs text-atlas-textSecondary truncate">{run.label || (run.symbols || []).join(", ")}</span>
                </div>
                <div className="flex items-center gap-3">
                    <span className={`font-mono text-[11px] font-bold ${STATUS_CLS[run.status] || "text-atlas-textSecondary"}`} data-testid={`run-status-${run.id.slice(0, 8)}`}>
                        {run.status}{run.status === "RUNNING" ? ` ${Math.round(run.progress_pct || 0)}%` : ""}
                    </span>
                    {isDone && (
                        <Button size="sm" variant="outline" data-testid={`download-pdf-${run.id.slice(0, 8)}`}
                            onClick={() => onDownload(run.id)} disabled={downloading} className="gap-1.5 h-7">
                            {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} PDF
                        </Button>
                    )}
                    {canPromote && (
                        <Button size="sm" data-testid={`promote-${run.id.slice(0, 8)}`}
                            onClick={() => onPromote(run.id)} disabled={promoting} className="gap-1.5 h-7">
                            <Rocket className="w-3.5 h-3.5" /> PROMOTE
                        </Button>
                    )}
                    {winner && (
                        <Button size="sm" data-testid={`save-config-${run.id.slice(0, 8)}`}
                            onClick={() => onSaveConfig({ run, ...winner })} className="gap-1.5 h-7">
                            <Trophy className="w-3.5 h-3.5" /> SAVE CONFIG
                        </Button>
                    )}
                    {isTerminal && (
                        <Button size="sm" variant="ghost" data-testid={`delete-run-${run.id.slice(0, 8)}`}
                            onClick={() => onDelete(run.id)} disabled={deleting} title="Delete this record (free up space)"
                            className="h-7 w-7 p-0 text-atlas-textTertiary hover:text-atlas-negative hover:bg-atlas-negative/10">
                            {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                        </Button>
                    )}
                </div>
            </div>
            {run.status === "RUNNING" && (
                <div className="mt-3 h-1.5 bg-atlas-border rounded-full overflow-hidden">
                    <div className="h-full bg-atlas-cyan transition-all" style={{ width: `${run.progress_pct || 0}%` }} />
                </div>
            )}
            {summary && <div className="mt-2 font-mono text-[11px] text-atlas-textSecondary" data-testid={`run-summary-${run.id.slice(0, 8)}`}>{summary}</div>}
            {run.status === "FAILED" && <div className="mt-2 font-mono text-[11px] text-atlas-negative">{run.error}</div>}
            {expanded && (
                <div className="mt-3 pt-3 border-t border-atlas-border" data-testid={`run-detail-${run.id.slice(0, 8)}`}>
                    {loadingDetail ? <Loader2 className="w-4 h-4 animate-spin text-atlas-cyan" /> : <RunDetails run={detail} onSaveConfig={onSaveConfig} />}
                </div>
            )}
        </div>
    );
}

function RunDetails({ run, onSaveConfig }) {
    if (!run?.result) return <div className="font-mono text-[11px] text-atlas-textSecondary">No detail available.</div>;
    const per = run.result.per_symbol || {};
    const mtf = run.result.multi_timeframe || {};
    const exitCmp = run.result.exit_comparison || {};
    const exitLabel = run.result.exit_method_label
        || (run.exit_method === "fixed" ? `Fixed $ Target (TP $${run.target_profit ?? 5} / SL $${run.target_loss ?? 4})` : "Universal Exit Engine (ATR-based)");
    return (
        <div className="space-y-4">
            {/* explicitly state which exit method was used — for cross-strategy comparison */}
            <div className="px-3 py-2 rounded-lg border border-atlas-cyan/30 bg-atlas-cyan/5" data-testid="detail-exit-method">
                <div className="flex items-center gap-2">
                    <SlidersHorizontal className="w-3.5 h-3.5 text-atlas-cyan shrink-0" />
                    <span className="font-mono text-[11px] text-atlas-text">Exit method used: <b className="text-atlas-cyan">{exitLabel}</b></span>
                </div>
                <div className="font-mono text-[10px] text-atlas-textTertiary mt-1 pl-5" data-testid="detail-exit-params">
                    Position size ${run.result.position_size_usd ?? run.position_size_usd ?? 75}
                    {run.exit_method === "fixed" && (() => {
                        const ps = run.result.position_size_usd || 75;
                        const tp = run.target_profit ?? 5, tl = run.target_loss ?? 4;
                        return ` · Profit $${tp} (≈${(tp / ps * 100).toFixed(2)}%) · Stop $${tl} (≈${(tl / ps * 100).toFixed(2)}%)`;
                    })()}
                    {run.exit_method === "atr" && run.result.atr_params && (
                        ` · ATR ×${run.result.atr_params.multiplier} · ${run.result.atr_params.period}p · arm ${run.result.atr_params.trail_activation_pct}% · trail ×${run.result.atr_params.trail_distance}`
                    )}
                </div>
            </div>
            {Object.keys(exitCmp).length > 0 && (
                <ExitComparison run={run} exitCmp={exitCmp} onSaveConfig={onSaveConfig} />
            )}
            {Object.entries(per).map(([sym, m]) => {
                if (m.error) return <div key={sym} className="font-mono text-[11px] text-atlas-negative">{sym}: {m.error}</div>;
                const verdict = mtf[sym]?.verdict;
                const byTf = mtf[sym]?.by_tf || {};
                return (
                    <div key={sym} data-testid={`detail-sym-${sym.split("/")[0]}`}>
                        <div className="font-mono text-xs font-bold text-atlas-text mb-1.5">{sym.split("/")[0]}</div>
                        <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                            <Metric label="Return" value={fmtPct(m.total_return_pct)} good={m.total_return_pct > 0} />
                            <Metric label="Win%" value={fmtPct(m.win_rate_pct)} />
                            <Metric label="Sharpe" value={m.sharpe ?? "—"} good={m.sharpe > 0} />
                            <Metric label="Prof.Factor" value={m.profit_factor ?? "—"} good={m.profit_factor >= 1} />
                            <Metric label="Max DD" value={fmtPct(m.max_drawdown_pct)} />
                            <Metric label="Trades" value={m.trades ?? 0} />
                        </div>
                        {/* trade-replay analytics: captured vs left-on-table (entry-vs-exit diagnosis) */}
                        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mt-2" data-testid={`detail-replay-${sym.split("/")[0]}`}>
                            <Metric label="Net $" value={`${m.net_pnl >= 0 ? "+" : ""}${(m.net_pnl ?? 0).toFixed(2)}`} good={m.net_pnl > 0} />
                            <Metric label="Avg MFE $" value={m.avg_mfe_usd != null ? `+${m.avg_mfe_usd}` : "—"} />
                            <Metric label="Avg MAE $" value={m.avg_mae_usd != null ? `${m.avg_mae_usd}` : "—"} />
                            <Metric label="Avg Left $" value={m.avg_profit_left_usd != null ? `${m.avg_profit_left_usd}` : "—"} />
                            <Metric label="Total Left $" value={m.total_profit_left_usd != null ? `${m.total_profit_left_usd}` : "—"} />
                            <Metric label="Avg MFE%" value={m.avg_mfe_pct != null ? fmtPct(m.avg_mfe_pct) : "—"} />
                        </div>
                        {m.strategy_breakdown && Object.keys(m.strategy_breakdown).length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-2" data-testid={`detail-strats-${sym.split("/")[0]}`}>
                                {Object.entries(m.strategy_breakdown).map(([st, v]) => (
                                    <span key={st} className="font-mono text-[10px] px-2 py-0.5 rounded border border-atlas-border text-atlas-textSecondary">
                                        {st}: {v.n}t · {v.win_pct}% · {v.net_pnl >= 0 ? "+" : ""}{v.net_pnl}
                                    </span>
                                ))}
                            </div>
                        )}
                        {Object.keys(byTf).length > 0 && (
                            <div className="mt-2 overflow-x-auto">
                                <table className="w-full font-mono text-[10px]" data-testid={`detail-mtf-${sym.split("/")[0]}`}>
                                    <thead><tr className="text-atlas-textTertiary text-left">
                                        <th className="pr-3 py-0.5">TF</th><th className="pr-3">Trades</th><th className="pr-3">Return</th><th className="pr-3">Win%</th><th className="pr-3">Max DD</th>
                                    </tr></thead>
                                    <tbody>
                                        {["15m", "30m", "1h"].map((tf) => {
                                            const t = byTf[tf]; if (!t) return null;
                                            if (t.error) return <tr key={tf}><td className="pr-3 py-0.5">{tf}</td><td colSpan={4} className="text-atlas-textTertiary">{t.error}</td></tr>;
                                            return (
                                                <tr key={tf} className="text-atlas-textSecondary">
                                                    <td className="pr-3 py-0.5">{tf}</td><td className="pr-3">{t.trades}</td>
                                                    <td className={`pr-3 ${t.total_return_pct > 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{fmtPct(t.total_return_pct)}</td>
                                                    <td className="pr-3">{fmtPct(t.win_rate_pct)}</td><td className="pr-3">{fmtPct(t.max_drawdown_pct)}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                        {verdict?.reason && (
                            <div className="mt-1.5 font-mono text-[10px] text-atlas-cyan" data-testid={`detail-verdict-${sym.split("/")[0]}`}>
                                Best TF: <b>{verdict.best_tf || "—"}</b> — {verdict.reason}
                            </div>
                        )}
                        {m.recommendation && (
                            <div className="mt-1.5 font-mono text-[10px] text-atlas-textSecondary italic" data-testid={`detail-reco-${sym.split("/")[0]}`}>
                                {m.recommendation}
                            </div>
                        )}
                        <TradeLog trades={m.trade_log || []} base={sym.split("/")[0]} />
                    </div>
                );
            })}
        </div>
    );
}

function TradeLog({ trades, base }) {
    const [open, setOpen] = useState(false);
    if (!trades.length) return null;
    const fmtTs = (iso) => (iso ? String(iso).replace("T", " ").slice(0, 16) : "—");
    const fmtPx = (v) => (v >= 1000 ? v.toFixed(2) : v >= 1 ? v.toFixed(4) : Number(v).toPrecision(4));
    const dur = (h) => (h == null ? "—" : h >= 24 ? `${(h / 24).toFixed(1)}d` : `${h.toFixed(1)}h`);
    return (
        <div className="mt-2">
            <button data-testid={`tradelog-toggle-${base}`} onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-1.5 font-mono text-[10px] text-atlas-textTertiary hover:text-atlas-cyan transition-colors">
                {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                {open ? "Hide" : "Show"} full trade log ({trades.length})
            </button>
            {open && (
                <div className="mt-1.5 overflow-x-auto max-h-80 overflow-y-auto border border-atlas-border rounded">
                    <table className="w-full font-mono text-[10px] whitespace-nowrap" data-testid={`tradelog-table-${base}`}>
                        <thead className="sticky top-0 bg-atlas-panel">
                            <tr className="text-atlas-textTertiary text-left border-b border-atlas-border">
                                <th className="px-2 py-1">#</th>
                                <th className="px-2">Strategy</th>
                                <th className="px-2">Entry time</th>
                                <th className="px-2">Exit time</th>
                                <th className="px-2 text-right">Entry</th>
                                <th className="px-2 text-right">Exit</th>
                                <th className="px-2 text-right">Size $</th>
                                <th className="px-2 text-right">Dur</th>
                                <th className="px-2">Exit reason</th>
                                <th className="px-2 text-right">P&amp;L $</th>
                                <th className="px-2 text-right">P&amp;L %</th>
                                <th className="px-2 text-right">MFE $</th>
                                <th className="px-2 text-right">MAE $</th>
                                <th className="px-2 text-right">Capt.</th>
                                <th className="px-2 text-right">Left $</th>
                                <th className="px-2">Regime</th>
                                <th className="px-2 text-right">Conf.</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trades.map((t, i) => (
                                <tr key={i} className="text-atlas-textSecondary border-b border-atlas-border/40">
                                    <td className="px-2 py-1 text-atlas-textTertiary">{i + 1}</td>
                                    <td className="px-2">{t.strategy || "—"}</td>
                                    <td className="px-2">{fmtTs(t.entry_ts)}</td>
                                    <td className="px-2">{fmtTs(t.exit_ts)}</td>
                                    <td className="px-2 text-right tabular-nums">{fmtPx(t.entry_price)}</td>
                                    <td className="px-2 text-right tabular-nums">{fmtPx(t.exit_price)}</td>
                                    <td className="px-2 text-right tabular-nums">{t.position_size_usd ?? "—"}</td>
                                    <td className="px-2 text-right tabular-nums">{dur(t.hold_hours)}</td>
                                    <td className="px-2 text-atlas-textTertiary">{t.exit_reason || t.exit_module}</td>
                                    <td className={`px-2 text-right tabular-nums font-bold ${t.pnl >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>
                                        {t.pnl >= 0 ? "+" : ""}{Number(t.pnl).toFixed(2)}
                                    </td>
                                    <td className={`px-2 text-right tabular-nums ${t.return_pct >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>
                                        {t.return_pct >= 0 ? "+" : ""}{Number(t.return_pct).toFixed(2)}%
                                    </td>
                                    <td className="px-2 text-right tabular-nums text-atlas-positive">{t.mfe_usd != null ? `+${t.mfe_usd}` : "—"}</td>
                                    <td className="px-2 text-right tabular-nums text-atlas-negative">{t.mae_usd != null ? t.mae_usd : "—"}</td>
                                    <td className="px-2 text-right tabular-nums">{t.captured_pnl != null ? t.captured_pnl : "—"}</td>
                                    <td className="px-2 text-right tabular-nums text-atlas-warning">{t.profit_left_usd != null ? t.profit_left_usd : "—"}</td>
                                    <td className="px-2 text-atlas-textTertiary">{t.regime_at_entry || "—"}</td>
                                    <td className="px-2 text-right tabular-nums">{t.confidence != null ? t.confidence : "—"}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

function Metric({ label, value, good }) {
    return (
        <div className="px-2 py-1.5 rounded border border-atlas-border">
            <div className="font-mono text-[9px] uppercase tracking-wider text-atlas-textTertiary">{label}</div>
            <div className={`font-mono text-xs font-bold ${good === undefined ? "text-atlas-text" : good ? "text-atlas-positive" : "text-atlas-negative"}`}>{value}</div>
        </div>
    );
}

function fmtPct(v) {
    return v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v}%`;
}

// Compact multi-select dropdown (trigger + popover checklist with a "Select all" row).
// Keeps the dark terminal aesthetic; used for both Strategy and Asset pickers so a long
// asset list no longer floods the panel with chips.
function MultiSelect({ testid, summary, options, allOn, onToggleAll, disabled }) {
    return (
        <Popover>
            <PopoverTrigger asChild>
                <button data-testid={testid} disabled={disabled}
                    className="w-full mt-2 h-[38px] flex items-center justify-between gap-2 bg-atlas-panel border border-atlas-border rounded px-3 font-mono text-sm text-atlas-text hover:border-atlas-cyan/60 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                    <span className="truncate">{summary}</span>
                    <ChevronDown className="w-3.5 h-3.5 text-atlas-textTertiary shrink-0" />
                </button>
            </PopoverTrigger>
            <PopoverContent align="start" data-testid={`${testid}-menu`}
                className="w-[var(--radix-popover-trigger-width)] min-w-56 max-h-72 overflow-auto p-1.5 bg-atlas-panel border-atlas-border">
                <button data-testid={`${testid}-all`} onClick={onToggleAll}
                    className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded font-mono text-xs text-atlas-text hover:bg-atlas-panelHover transition-colors">
                    <Check className={`w-3.5 h-3.5 text-atlas-cyan ${allOn ? "opacity-100" : "opacity-0"}`} />
                    <span className="font-bold">Select all</span>
                </button>
                <div className="h-px bg-atlas-border my-1" />
                {options.map((o) => (
                    <button key={o.key} data-testid={`${testid}-opt-${String(o.key).split("/")[0]}`} onClick={o.onToggle}
                        className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded font-mono text-xs text-atlas-textSecondary hover:bg-atlas-panelHover hover:text-atlas-text transition-colors">
                        <Check className={`w-3.5 h-3.5 text-atlas-cyan shrink-0 ${o.on ? "opacity-100" : "opacity-0"}`} />
                        <span className="flex-1 text-left truncate">{o.label}</span>
                        {o.meta && <span className="text-[9px] text-atlas-textTertiary tabular-nums">{o.meta}</span>}
                    </button>
                ))}
            </PopoverContent>
        </Popover>
    );
}

function runSummary(run) {
    if (run.status !== "DONE" || !run.result) return run.git_hash ? `commit ${run.git_hash}` : null;
    const r = run.result;
    if (run.kind === "walk_forward") return `WFA efficiency ${r.wfa_efficiency ?? "—"} · OOS+ ${r.oos_positive_folds ?? "—"} · ${r.verdict || ""}`;
    if (run.kind === "backtest") {
        const syms = r.per_symbol || {};
        const parts = Object.entries(syms).map(([k, v]) => `${k.split("/")[0]} ${v.total_return_pct ?? "?"}% (${v.trades ?? 0}t)`);
        return parts.join("  ·  ");
    }
    if (run.kind === "sensitivity") return `${r.target} · ${r.verdict || ""}`;
    return `commit ${run.git_hash}`;
}


// Pick the timeframe block to show for a symbol (prefer 1h, else first available).
function pickBlock(byTf) {
    return byTf?.["1h"] ? { tf: "1h", block: byTf["1h"] } : (() => {
        const tf = Object.keys(byTf || {})[0];
        return tf ? { tf, block: byTf[tf] } : null;
    })();
}

// A/B/C exit-config comparison table (winner highlighted) with a Save action per symbol.
function ExitComparison({ run, exitCmp, onSaveConfig }) {
    const CMP_COLS = [
        { k: "total_return_pct", label: "Return", pct: true, good: (v) => v > 0 },
        { k: "win_rate_pct", label: "Win%", pct: true },
        { k: "profit_factor", label: "PF", good: (v) => v >= 1 },
        { k: "expectancy_usd", label: "Exp $" },
        { k: "max_drawdown_pct", label: "Max DD", pct: true },
        { k: "trades", label: "Trades" },
    ];
    return (
        <div className="space-y-4" data-testid="exit-comparison">
            <div className="flex items-center gap-2">
                <Trophy className="w-3.5 h-3.5 text-atlas-cyan" />
                <span className="font-mono text-[11px] font-bold text-atlas-text uppercase tracking-wide">Exit-Config Comparison (A/B/C)</span>
            </div>
            {Object.entries(exitCmp).map(([sym, byTf]) => {
                const picked = pickBlock(byTf);
                const block = picked?.block;
                if (!block || block.error) {
                    return <div key={sym} className="font-mono text-[10px] text-atlas-textTertiary">{sym.split("/")[0]}: {block?.error || "no comparison"}</div>;
                }
                const wk = block.winner_key;
                const configs = block.configs || [];
                const rows = block.rows || {};
                return (
                    <div key={sym} data-testid={`exit-cmp-${sym.split("/")[0]}`} className="border border-atlas-border rounded-lg p-3">
                        <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
                            <span className="font-mono text-xs font-bold text-atlas-text">{sym.split("/")[0]} · {picked.tf}</span>
                            {wk ? (
                                <Button size="sm" data-testid={`save-winner-${sym.split("/")[0]}`}
                                    onClick={() => onSaveConfig({ run, symbol: sym, timeframe: picked.tf, winnerKey: wk, winnerLabel: rows[wk]?.label || wk })}
                                    className="gap-1.5 h-7">
                                    <Save className="w-3.5 h-3.5" /> SAVE WINNING
                                </Button>
                            ) : (
                                <span className="font-mono text-[10px] text-atlas-textTertiary">no clear winner</span>
                            )}
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full font-mono text-[10px] whitespace-nowrap" data-testid={`exit-cmp-table-${sym.split("/")[0]}`}>
                                <thead>
                                    <tr className="text-atlas-textTertiary text-left border-b border-atlas-border">
                                        <th className="px-2 py-1">Exit Config</th>
                                        {CMP_COLS.map((c) => <th key={c.k} className="px-2 text-right">{c.label}</th>)}
                                    </tr>
                                </thead>
                                <tbody>
                                    {configs.map((c) => {
                                        const m = rows[c.key] || {};
                                        const isWinner = c.key === wk;
                                        if (m.error) {
                                            return <tr key={c.key} className="text-atlas-textTertiary border-b border-atlas-border/40">
                                                <td className="px-2 py-1">{c.label}</td>
                                                <td className="px-2" colSpan={CMP_COLS.length}>{m.error}</td>
                                            </tr>;
                                        }
                                        return (
                                            <tr key={c.key} data-testid={`exit-cmp-row-${sym.split("/")[0]}-${c.key}`}
                                                className={`border-b border-atlas-border/40 ${isWinner ? "bg-atlas-cyan/10 text-atlas-text" : "text-atlas-textSecondary"}`}>
                                                <td className="px-2 py-1">
                                                    {isWinner && <Trophy className="w-3 h-3 text-atlas-cyan inline mr-1 -mt-0.5" />}
                                                    <span className={isWinner ? "font-bold text-atlas-cyan" : ""}>{c.label}</span>
                                                </td>
                                                {CMP_COLS.map((col) => {
                                                    const v = m[col.k];
                                                    const disp = v == null ? "—" : col.pct ? fmtPct(v) : v;
                                                    const good = col.good ? col.good(v) : undefined;
                                                    return <td key={col.k} className={`px-2 text-right tabular-nums ${good === undefined ? "" : good ? "text-atlas-positive" : "text-atlas-negative"}`}>{disp}</td>;
                                                })}
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
