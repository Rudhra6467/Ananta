import { useEffect, useMemo, useState } from "react";
import { FlaskConical, Play, Download, Loader2, Sparkles, SlidersHorizontal, Rocket, Check, X, Trash2, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";

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
const _labCache = { cov: null, presets: null, runs: null, assets: null, period: null, strategies: null, compareTf: false };

export default function StrategyValidationPanel() {
    const [cov, setCov] = useState(_labCache.cov);
    const [assets, setAssets] = useState(_labCache.assets || []);
    const [period, setPeriod] = useState(_labCache.period || "3m");
    const [strategies, setStrategies] = useState(_labCache.strategies || ALL_STRATEGY_IDS);
    const [compareTf, setCompareTf] = useState(_labCache.compareTf || false);
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
    }, []);

    // keep the user's asset/period/strategy selection across tab switches
    const chooseAssets = (next) => { _labCache.assets = next; setAssets(next); };
    const choosePeriod = (next) => { _labCache.period = next; setPeriod(next); };
    const chooseStrategies = (next) => { _labCache.strategies = next; setStrategies(next); };
    const chooseCompareTf = (next) => { _labCache.compareTf = next; setCompareTf(next); };

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
            const common = { symbols: assets, period, strategies, compare_timeframes: compareTf };
            let spec;
            if (track === "current") {
                spec = { kind: "backtest", ...common };
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
                            onPromote={promote} promoting={promoteBusy} onDelete={deleteRun} deleting={deleting === r.id} />)}
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
        </section>
    );
}

function RunRow({ run, onDownload, downloading, onPromote, promoting, onDelete, deleting }) {
    const isDone = run.status === "DONE";
    const isTerminal = isDone || run.status === "FAILED";
    const canPromote = isDone && run.kind !== "backtest";
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
                    {loadingDetail ? <Loader2 className="w-4 h-4 animate-spin text-atlas-cyan" /> : <RunDetails run={detail} />}
                </div>
            )}
        </div>
    );
}

function RunDetails({ run }) {
    if (!run?.result) return <div className="font-mono text-[11px] text-atlas-textSecondary">No detail available.</div>;
    const per = run.result.per_symbol || {};
    const mtf = run.result.multi_timeframe || {};
    return (
        <div className="space-y-4">
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
                    </div>
                );
            })}
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
