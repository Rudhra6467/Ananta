import { useEffect, useState, useMemo } from "react";
import {
    Boxes, TrendingUp, Zap, Activity, Plus, ArrowLeft, Copy, Download, Power, Search,
    Loader2, Star, ShieldCheck, BarChart3, Brain, Layers, FileJson, GitBranch, Store, Code, Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import LabModal from "@/components/lab/LabModal";
import SavedConfigsPanel from "@/components/lab/SavedConfigsPanel";
import MonteCarloPanel from "@/components/lab/MonteCarloPanel";
import AIAnalystTerminal from "@/components/lab/AIAnalystTerminal";
import StrategyValidationPanel from "@/components/StrategyValidationPanel";
import HelpHint from "@/components/lab/HelpHint";
import { useAuth } from "@/context/AuthContext";

const ICONS = { hunter: TrendingUp, squeeze: Zap, continuation: Activity };
const STATUS = {
    LIVE: "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10",
    PAPER: "text-atlas-cyan border-atlas-cyan/40 bg-atlas-cyan/10",
    DISABLED: "text-atlas-textTertiary border-atlas-border bg-atlas-panel",
    TESTING: "text-atlas-warning border-atlas-warning/40 bg-atlas-warning/10",
    OPTIMIZING: "text-violet-400 border-violet-500/40 bg-violet-500/10",
    ERROR: "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/10",
};
const SORTS = [
    { id: "profit", label: "Most Profitable", fn: (a, b) => b.roi - a.roi },
    { id: "winrate", label: "Highest Win Rate", fn: (a, b) => b.win_rate - a.win_rate },
    { id: "health", label: "Healthiest", fn: (a, b) => b.health - a.health },
    { id: "rating", label: "Top Rated", fn: (a, b) => b.stars - a.stars },
];

export default function StrategyCenter() {
    const [metrics, setMetrics] = useState(null);
    const [registry, setRegistry] = useState({});
    const [selected, setSelected] = useState(null);
    const [addOpen, setAddOpen] = useState(false);
    const { isOwner } = useAuth();

    const load = () => {
        api.strategyMetrics().then((d) => setMetrics(d.metrics)).catch(() => setMetrics({}));
        api.strategyRegistry().then((d) => {
            const m = {}; (d.strategies || []).forEach((s) => { m[s.key] = s; }); setRegistry(m);
        }).catch(() => {});
    };
    useEffect(load, []);

    if (selected) {
        return <StrategyDetail sKey={selected} schema={registry[selected]} metric={metrics?.[selected]}
            isOwner={isOwner} onBack={() => { setSelected(null); load(); }} onChanged={load} />;
    }

    return (
        <>
            <StrategyList metrics={metrics} onOpen={setSelected} onAdd={() => setAddOpen(true)} />
            <AddStrategyWizard open={addOpen} onOpenChange={setAddOpen} registry={registry} isOwner={isOwner}
                onCreated={() => { setAddOpen(false); load(); }} />
        </>
    );
}

/* ---------------- List view ---------------- */
function StrategyList({ metrics, onOpen, onAdd }) {
    const [query, setQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState(null);
    const [sort, setSort] = useState("health");

    const rows = useMemo(() => {
        let arr = Object.values(metrics || {});
        if (query.trim()) arr = arr.filter((s) => s.name.toLowerCase().includes(query.toLowerCase()));
        if (statusFilter) arr = arr.filter((s) => s.status === statusFilter);
        const s = SORTS.find((x) => x.id === sort);
        return [...arr].sort(s ? s.fn : (a, b) => 0);
    }, [metrics, query, statusFilter, sort]);

    if (!metrics) {
        return <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary flex items-center gap-2" data-testid="strategy-center-loading"><Loader2 className="w-4 h-4 animate-spin" /> LOADING STRATEGIES</div>;
    }

    return (
        <div className="space-y-5" data-testid="strategy-center">
            {/* search + filters */}
            <div className="space-y-3">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-atlas-textTertiary" />
                    <Input data-testid="strategy-search" value={query} onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search strategies…" className="atlas-input rounded-lg pl-9 font-mono text-sm" />
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    {["LIVE", "PAPER", "DISABLED"].map((st) => (
                        <Chip key={st} testid={`filter-${st}`} active={statusFilter === st} onClick={() => setStatusFilter(statusFilter === st ? null : st)}>{st}</Chip>
                    ))}
                    <span className="w-px h-5 bg-atlas-border mx-1" />
                    {SORTS.map((s) => (
                        <Chip key={s.id} testid={`sort-${s.id}`} active={sort === s.id} onClick={() => setSort(s.id)}>{s.label}</Chip>
                    ))}
                </div>
            </div>

            {/* cards — always 2 per row */}
            <div className="grid grid-cols-2 gap-3 md:gap-5" data-testid="strategy-grid">
                {rows.map((s) => <StrategyCard key={s.key} s={s} onOpen={() => onOpen(s.key)} />)}
                <button data-testid="add-strategy-card" onClick={onAdd}
                    className="group rounded-2xl border-2 border-dashed border-atlas-border hover:border-atlas-cyan/60 bg-atlas-panel/30 min-h-[180px] flex flex-col items-center justify-center gap-2 transition-all hover:bg-atlas-panelHover">
                    <div className="w-11 h-11 rounded-xl grid place-items-center border border-atlas-border group-hover:border-atlas-cyan/50 group-hover:bg-atlas-cyan/10 transition-colors">
                        <Plus className="w-5 h-5 text-atlas-textTertiary group-hover:text-atlas-cyan" />
                    </div>
                    <span className="font-mono text-xs text-atlas-textSecondary group-hover:text-atlas-text">Add Strategy</span>
                </button>
            </div>
        </div>
    );
}

function Chip({ children, active, onClick, testid }) {
    return (
        <button data-testid={testid} onClick={onClick}
            className={`px-3 py-1.5 rounded-full font-mono text-[10px] tracking-wide border transition-all ${
                active ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary"
            }`}>{children}</button>
    );
}

function StrategyCard({ s, onOpen }) {
    const Icon = ICONS[s.key] || Boxes;
    const roiCls = s.roi > 0 ? "text-atlas-positive" : s.roi < 0 ? "text-atlas-negative" : "text-atlas-text";
    return (
        <button data-testid={`strategy-card-${s.key}`} onClick={onOpen}
            className="group text-left rounded-2xl border border-atlas-border bg-atlas-panel/70 p-4 md:p-5 flex flex-col gap-3 transition-all hover:-translate-y-0.5 hover:bg-atlas-panelHover hover:shadow-[0_16px_50px_-20px_rgba(0,0,0,0.95)]">
            <div className="flex items-start justify-between gap-2">
                <div className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5">
                    <Icon className="w-5 h-5 text-atlas-cyan" strokeWidth={2} />
                </div>
                <span className={`font-mono text-[8px] font-bold uppercase tracking-wider px-2 py-1 rounded-full border ${STATUS[s.status] || STATUS.PAPER}`} data-testid={`card-status-${s.key}`}>{s.status}</span>
            </div>
            <div>
                <div className="font-heading font-medium text-base md:text-lg text-atlas-text leading-tight truncate">{s.name}</div>
                <div className="flex items-center gap-1 mt-0.5">
                    {[1, 2, 3, 4, 5].map((n) => <Star key={n} className={`w-3 h-3 ${n <= s.stars ? "text-atlas-warning fill-atlas-warning" : "text-atlas-textTertiary"}`} />)}
                </div>
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 font-mono text-[11px]">
                <Kv label="ROI" value={`${s.roi > 0 ? "+" : ""}${s.roi}%`} cls={roiCls} />
                <Kv label="Win Rate" value={`${s.win_rate}%`} />
                <Kv label="Health" value={`${s.health}`} cls={s.health >= 60 ? "text-atlas-positive" : s.health >= 35 ? "text-atlas-warning" : "text-atlas-negative"} />
                <Kv label="Trades" value={s.trades} />
            </div>
        </button>
    );
}

function Kv({ label, value, cls = "text-atlas-text" }) {
    return (
        <div className="flex items-center justify-between gap-2">
            <span className="text-atlas-textTertiary">{label}</span>
            <span className={`font-bold tabular-nums ${cls}`}>{value}</span>
        </div>
    );
}

/* ---------------- Detail view ---------------- */
const TABS = ["Overview", "Parameters", "Validation", "AI", "Research", "History"];

function StrategyDetail({ sKey, schema, metric, isOwner, onBack, onChanged }) {
    const [tab, setTab] = useState("Overview");
    const [status, setStatus] = useState(metric?.status || "PAPER");
    const Icon = ICONS[sKey] || Boxes;

    const setState = async (patch) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try {
            const r = await api.strategySetState(sKey, patch);
            if (r.status) setStatus(r.status);
            toast.success("Strategy updated", { description: JSON.stringify(patch) });
            onChanged?.();
        } catch (e) { toast.error("Update failed", { description: String(e?.response?.data?.detail || e?.message) }); }
    };

    return (
        <div className="space-y-5" data-testid={`strategy-detail-${sKey}`}>
            {/* header */}
            <div className="panel border-atlas-border rounded-2xl p-5">
                <button data-testid="detail-back-btn" onClick={onBack} className="flex items-center gap-1.5 font-mono text-[10px] text-atlas-textTertiary hover:text-atlas-text mb-3">
                    <ArrowLeft className="w-3.5 h-3.5" /> ALL STRATEGIES
                </button>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5">
                            <Icon className="w-6 h-6 text-atlas-cyan" strokeWidth={2} />
                        </div>
                        <div>
                            <div className="font-heading font-medium text-xl md:text-2xl text-atlas-text leading-tight">{schema?.name || sKey}</div>
                            <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">v{schema?.version || "1.0.0"} · {metric?.trades ?? 0} trades · {metric?.config_count ?? 0} configs</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className={`font-mono text-[9px] font-bold uppercase px-2.5 py-1.5 rounded-lg border ${STATUS[status]}`} data-testid="detail-status">{status}</span>
                        <select data-testid="detail-status-select" value={status} onChange={(e) => setState({ status: e.target.value })} disabled={!isOwner}
                            className="bg-atlas-panel border border-atlas-border rounded-lg px-2.5 py-1.5 font-mono text-[10px] text-atlas-text disabled:opacity-50">
                            {Object.keys(STATUS).map((st) => <option key={st} value={st}>{st}</option>)}
                        </select>
                    </div>
                </div>
                {/* headline metrics */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                    <Stat label="ROI" value={`${(metric?.roi ?? 0) > 0 ? "+" : ""}${metric?.roi ?? 0}%`} cls={(metric?.roi ?? 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative"} />
                    <Stat label="Win Rate" value={`${metric?.win_rate ?? 0}%`} />
                    <Stat label="Health" value={metric?.health ?? "—"} />
                    <Stat label="Confidence" value={`${metric?.confidence ?? 0}%`} />
                </div>
            </div>

            {/* tabs */}
            <div className="flex items-center gap-1 overflow-x-auto atlas-scroll border-b border-atlas-border" data-testid="detail-tabs">
                {TABS.map((t) => (
                    <button key={t} data-testid={`tab-${t.toLowerCase()}`} onClick={() => setTab(t)}
                        className={`px-3.5 py-2.5 font-mono text-[11px] tracking-wide whitespace-nowrap border-b-2 -mb-px transition-colors ${
                            tab === t ? "border-atlas-cyan text-atlas-cyan" : "border-transparent text-atlas-textTertiary hover:text-atlas-text"
                        }`}>{t}</button>
                ))}
            </div>

            {/* tab body */}
            <div data-testid={`tab-body-${tab.toLowerCase()}`}>
                {tab === "Overview" && <Overview schema={schema} metric={metric} />}
                {tab === "Parameters" && <SavedConfigsPanel isOwner={isOwner} only={sKey} />}
                {tab === "Validation" && <div className="space-y-4"><MonteCarloPanel /><StrategyValidationPanel /></div>}
                {tab === "AI" && <AIAnalystTerminal isOwner={isOwner} strategy={sKey} />}
                {tab === "Research" && (
                    <div className="panel border-atlas-border rounded-xl p-5 space-y-3">
                        <div className="flex items-center gap-2"><FlaskIcon /> <span className="font-heading font-medium text-atlas-text">Research & Backtesting</span></div>
                        <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">Run backtests, walk-forward and optimization sweeps for <b className="text-atlas-text">{schema?.name || sKey}</b>. Every completed run is attached to the strategy in History.</p>
                        <StrategyValidationPanel />
                    </div>
                )}
                {tab === "History" && <History metric={metric} />}
            </div>
        </div>
    );
}

function FlaskIcon() { return <Layers className="w-4 h-4 text-atlas-cyan" />; }

function Stat({ label, value, cls = "text-atlas-text" }) {
    return (
        <div className="rounded-lg border border-atlas-border bg-atlas-panel px-3 py-2.5">
            <div className="font-mono text-[9px] uppercase tracking-wider text-atlas-textTertiary">{label}</div>
            <div className={`font-heading font-bold text-lg md:text-xl tabular-nums mt-0.5 ${cls}`}>{value}</div>
        </div>
    );
}

function Overview({ schema, metric }) {
    const dna = schema?.dna && typeof schema.dna === "object" ? schema.dna : {};
    const dnaRows = Object.entries(dna).filter(([, v]) => typeof v !== "object");
    return (
        <div className="space-y-4">
            <div className="panel border-atlas-border rounded-xl p-5">
                <div className="label-tag mb-2">HOW IT WORKS</div>
                <p className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed">{schema?.description || "No description available for this strategy."}</p>
            </div>
            {dnaRows.length > 0 && (
                <div className="panel border-atlas-border rounded-xl p-5">
                    <div className="label-tag mb-3">STRATEGY DNA</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                        {dnaRows.map(([k, v]) => (
                            <div key={k} className="flex items-center justify-between gap-3 font-mono text-[11px] border-b border-atlas-border/40 py-1">
                                <span className="text-atlas-textTertiary capitalize">{k.replace(/_/g, " ")}</span>
                                <span className="text-atlas-text font-bold text-right">{String(v)}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            <div className="panel border-atlas-border rounded-xl p-5">
                <div className="label-tag mb-3">LIVE SNAPSHOT</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <Stat label="Total P&L" value={`$${metric?.total_pnl ?? 0}`} cls={(metric?.total_pnl ?? 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative"} />
                    <Stat label="Trades" value={metric?.trades ?? 0} />
                    <Stat label="Rating" value={`${metric?.stars ?? 0}★`} />
                    <Stat label="Last Trade" value={metric?.last_trade ? new Date(metric.last_trade).toLocaleDateString() : "—"} />
                </div>
            </div>
        </div>
    );
}

function History({ metric }) {
    return (
        <div className="panel border-atlas-border rounded-xl p-5">
            <div className="label-tag mb-3">HISTORICAL RUNS</div>
            <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">
                Backtests, walk-forward and optimization runs launched from the Validation / Research tabs
                are recorded in the Research Lab timeline. This strategy has {metric?.trades ?? 0} closed live trades so far.
            </p>
            <div className="mt-3 flex items-center gap-2 font-mono text-[10px] text-atlas-textTertiary">
                <HelpHint text="Per-strategy run history with version tagging & compare is on the roadmap. Runs currently live in the Research Lab." title="Run History" side="bottom" />
                Version-tagged run history coming with the optimization engine.
            </div>
        </div>
    );
}

/* ---------------- Add Strategy wizard ---------------- */
const SOURCES = [
    { id: "duplicate", label: "Copy Existing Strategy", icon: Copy, ready: true, desc: "Clone a built-in as a new tunable config variant." },
    { id: "json", label: "Import JSON Configuration", icon: FileJson, ready: true, desc: "Paste a validated config JSON." },
    { id: "builtin", label: "Built-in Strategies", icon: Boxes, ready: false, desc: "All built-ins are already active." },
    { id: "marketplace", label: "Community Marketplace", icon: Store, ready: false, desc: "Coming soon." },
    { id: "git", label: "Git Repository", icon: GitBranch, ready: false, desc: "Coming soon." },
    { id: "python", label: "Upload Python Strategy", icon: Code, ready: false, desc: "Sandboxed execution — coming soon." },
];

function AddStrategyWizard({ open, onOpenChange, registry, isOwner, onCreated }) {
    const [source, setSource] = useState(null);
    const [strat, setStrat] = useState("hunter");
    const [name, setName] = useState("");
    const [json, setJson] = useState("");
    const [busy, setBusy] = useState(false);
    const keys = Object.keys(registry);

    const reset = () => { setSource(null); setName(""); setJson(""); };

    const submit = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setBusy(true);
        try {
            let payload;
            if (source === "duplicate") {
                payload = { strategy_key: strat, params: {}, origin: "user", name: name.trim() || `${registry[strat]?.name || strat} · variant` };
            } else {
                let parsed;
                try { parsed = JSON.parse(json); }
                catch { toast.error("Invalid JSON", { description: "Check the syntax and try again." }); setBusy(false); return; }
                if (!parsed.strategy_key) { toast.error("Missing strategy_key", { description: 'JSON must include a "strategy_key".' }); setBusy(false); return; }
                payload = { strategy_key: parsed.strategy_key, params: parsed.params || {}, origin: "user", name: (parsed.name || name.trim() || "Imported config") };
            }
            const res = await api.strategyConfigCreate(payload);
            toast.success("STRATEGY VARIANT ADDED", { description: res.config.name });
            reset(); onCreated();
        } catch (e) {
            toast.error("ADD FAILED", { description: String(e?.response?.data?.detail?.errors?.join?.(", ") || e?.response?.data?.detail || e?.message) });
        } finally { setBusy(false); }
    };

    return (
        <LabModal open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }} testid="add-strategy-wizard"
            icon={Sparkles} accent="cyan" title="Add Strategy" subtitle="Choose a source">
            {!source ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="wizard-sources">
                    {SOURCES.map((src) => {
                        const SIcon = src.icon;
                        return (
                            <button key={src.id} data-testid={`source-${src.id}`} disabled={!src.ready} onClick={() => src.ready && setSource(src.id)}
                                className={`text-left p-4 rounded-xl border transition-all ${src.ready ? "border-atlas-border hover:border-atlas-cyan/50 hover:bg-atlas-panelHover" : "border-atlas-border/50 opacity-50 cursor-not-allowed"}`}>
                                <SIcon className={`w-5 h-5 mb-2 ${src.ready ? "text-atlas-cyan" : "text-atlas-textTertiary"}`} />
                                <div className="font-mono text-sm font-bold text-atlas-text flex items-center gap-2">{src.label}{!src.ready && <span className="text-[8px] text-atlas-textTertiary border border-atlas-border rounded px-1 py-0.5">SOON</span>}</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary mt-1">{src.desc}</div>
                            </button>
                        );
                    })}
                </div>
            ) : (
                <div className="space-y-4" data-testid={`wizard-form-${source}`}>
                    <button onClick={() => setSource(null)} className="flex items-center gap-1.5 font-mono text-[10px] text-atlas-textTertiary hover:text-atlas-text">
                        <ArrowLeft className="w-3.5 h-3.5" /> CHANGE SOURCE
                    </button>
                    {source === "duplicate" && (
                        <div>
                            <div className="label-tag mb-2">BASE STRATEGY</div>
                            <select data-testid="wizard-strat" value={strat} onChange={(e) => setStrat(e.target.value)}
                                className="w-full bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-sm text-atlas-text">
                                {keys.map((k) => <option key={k} value={k}>{registry[k]?.name || k}</option>)}
                            </select>
                        </div>
                    )}
                    {source === "json" && (
                        <div>
                            <div className="label-tag mb-2">CONFIG JSON</div>
                            <textarea data-testid="wizard-json" value={json} onChange={(e) => setJson(e.target.value)} rows={7}
                                placeholder='{"strategy_key":"hunter","name":"My variant","params":{"rsi_reset_min":28}}'
                                className="w-full atlas-input rounded-lg font-mono text-[11px] p-3" />
                        </div>
                    )}
                    <div>
                        <div className="label-tag mb-2">NAME (optional)</div>
                        <Input data-testid="wizard-name" value={name} onChange={(e) => setName(e.target.value)} className="atlas-input rounded-lg font-mono text-sm" placeholder="Auto-generated if blank" />
                    </div>
                    <Button data-testid="wizard-submit" onClick={submit} disabled={busy || !isOwner} className="w-full gap-2">
                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} ADD STRATEGY
                    </Button>
                </div>
            )}
        </LabModal>
    );
}
