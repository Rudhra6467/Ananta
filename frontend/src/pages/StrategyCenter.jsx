import { useEffect, useRef, useState } from "react";
import {
    Boxes, TrendingUp, Zap, Activity, Plus, ArrowLeft, Copy, Download, Power, Search,
    Loader2, Star, ShieldCheck, BarChart3, Brain, Layers, FileJson, GitBranch, Sparkles,
    CheckCircle2, Circle, Clock, HeartPulse, Pencil, SlidersHorizontal, Heart, X, Upload, ChevronDown, Trash2, Filter,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import LabModal from "@/components/lab/LabModal";
import SavedConfigsPanel from "@/components/lab/SavedConfigsPanel";
import AIAnalystTerminal from "@/components/lab/AIAnalystTerminal";
import StrategyArchitect from "@/pages/StrategyArchitect";
import ImportStrategyModal from "@/components/ImportStrategyModal";
import { useAuth } from "@/context/AuthContext";
import { useResearchStore } from "@/lib/researchStore";
import MetricExplainer from "@/components/MetricExplainer";
import { StrategyConfigModal } from "@/components/StrategyConfigModal";
import HeaderActionPortal from "@/components/HeaderActionPortal";

const ICONS = { hunter: TrendingUp, squeeze: Zap, continuation: Activity };
// A strategy is "live" only when its engine metric is actively running (mirrors mobile isLiveMetric).
const isLiveMetric = (m) => !!m && !!m.enabled && m.status !== "DISABLED" && m.status !== "ERROR";
const STATUS = {
    LIVE: "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10",
    PAPER: "text-atlas-cyan border-atlas-cyan/40 bg-atlas-cyan/10",
    DISABLED: "text-atlas-textTertiary border-atlas-border bg-atlas-panel",
    TESTING: "text-atlas-warning border-atlas-warning/40 bg-atlas-warning/10",
    OPTIMIZING: "text-violet-400 border-violet-500/40 bg-violet-500/10",
    ERROR: "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/10",
};
const GRADE_CLS = {
    A: "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10",
    B: "text-atlas-cyan border-atlas-cyan/40 bg-atlas-cyan/10",
    C: "text-atlas-warning border-atlas-warning/40 bg-atlas-warning/10",
    D: "text-orange-400 border-orange-500/40 bg-orange-500/10",
    E: "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/10",
};

export default function StrategyCenter() {
    const [metrics, setMetrics] = useState(null);
    const [registry, setRegistry] = useState({});
    const [selected, setSelected] = useState(null);       // internal engine key -> StrategyDetail
    const [catalogId, setCatalogId] = useState(null);     // library id -> CatalogDetail
    const [addOpen, setAddOpen] = useState(false);
    const [importOpen, setImportOpen] = useState(false);
    const { isOwner } = useAuth();

    const load = () => {
        api.strategyMetrics().then((d) => setMetrics(d.metrics)).catch(() => setMetrics({}));
        api.strategyRegistry().then((d) => {
            const m = {}; (d.strategies || []).forEach((s) => { m[s.key] = s; }); setRegistry(m);
        }).catch(() => {});
    };
    useEffect(load, []);

    // Tapping the "Strategy Center" header title returns to the library home.
    useEffect(() => {
        const onHome = (e) => { if (e.detail?.id === "strategies") { setSelected(null); setCatalogId(null); } };
        window.addEventListener("ananta:tab-home", onHome);
        return () => window.removeEventListener("ananta:tab-home", onHome);
    }, []);

    if (selected) {
        return <StrategyDetail sKey={selected} schema={registry[selected]} metric={metrics?.[selected]}
            isOwner={isOwner} onBack={() => { setSelected(null); load(); }} onChanged={load} />;
    }
    if (catalogId) {
        return <CatalogDetail id={catalogId} isOwner={isOwner}
            onOpenInternal={(k) => { setCatalogId(null); setSelected(k); }}
            onBack={() => setCatalogId(null)} />;
    }

    return (
        <>
            <StrategyLibrary metrics={metrics} isOwner={isOwner} registry={registry}
                onOpenInternal={setSelected} onOpenCatalog={setCatalogId}
                onImport={() => setImportOpen(true)} onBuild={() => setAddOpen(true)} />
            <StrategyArchitect open={addOpen} onOpenChange={setAddOpen} registry={registry} isOwner={isOwner}
                onCreated={() => { setAddOpen(false); load(); }} />
            <ImportStrategyModal open={importOpen} onOpenChange={setImportOpen}
                onImported={() => { setImportOpen(false); load(); }} />
        </>
    );
}

const FILTER_FIELDS = [
    { key: "market_regime", label: "Market Regime" },
    { key: "market_type", label: "Market Type" },
    { key: "style", label: "Trading Style" },
    { key: "timeframe", label: "Timeframe" },
    { key: "risk", label: "Risk Level" },
    { key: "ai_grade", label: "AI Grade" },
    { key: "source", label: "Strategy Source" },
];

/* ---------------- Library view ---------------- */
function StrategyLibrary({ metrics, isOwner, registry, onOpenInternal, onOpenCatalog, onImport, onBuild }) {
    const [lib, setLib] = useState(null);
    const [facets, setFacets] = useState({});
    const [query, setQuery] = useState("");
    const [filters, setFilters] = useState({});   // {field: [values]}
    const [favOnly, setFavOnly] = useState(false);
    const [showFilter, setShowFilter] = useState(false);
    const [addChooser, setAddChooser] = useState(false);
    const [cloneOpen, setCloneOpen] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);

    const activeCount = Object.values(filters).reduce((n, v) => n + v.length, 0) + (favOnly ? 1 : 0);

    const load = () => {
        const params = {};
        if (query.trim()) params.q = query.trim();
        if (favOnly) params.favorite = true;
        Object.entries(filters).forEach(([k, v]) => { if (v.length) params[k] = v.join(","); });
        api.libraryList(params).then((d) => setLib(d.strategies)).catch(() => setLib([]));
    };
    useEffect(() => { api.libraryFacets().then(setFacets).catch(() => {}); }, []);
    useEffect(load, [filters, favOnly, query]);

    const toggleFilter = (field, val) => setFilters((f) => {
        const cur = f[field] || [];
        return { ...f, [field]: cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val] };
    });
    const clearFilters = () => { setFilters({}); setFavOnly(false); };

    // Route a library card tap: built-in engines AND wireable strategies that have an engine
    // schema open the redesigned StrategyDetail (clean Live/Off + Edit Strategy). Only pure
    // catalog/custom entries without an engine schema fall back to CatalogDetail.
    const routeOpen = (s) => {
        if (s.internal || (s.wireable && s.engine_key && registry?.[s.engine_key])) onOpenInternal(s.engine_key);
        else onOpenCatalog(s.id);
    };

    return (
        <div className="space-y-5" data-testid="strategy-center">
            {/* Search + Add live in the scroll-through top header, next to the title */}
            <HeaderActionPortal>
                <button data-testid="strategy-search-btn" onClick={() => setSearchOpen(true)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-full font-mono text-[10px] tracking-wide border border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-all">
                    <Search className="w-3.5 h-3.5" /> Search
                </button>
                <button data-testid="strategy-add-btn" aria-label="Add Strategy" title="Add Strategy" onClick={() => setAddChooser(true)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-full font-mono text-[10px] tracking-wide border border-atlas-cyan/50 bg-atlas-cyan/10 text-atlas-cyan hover:bg-atlas-cyan/20 transition-all">
                    <Plus className="w-3.5 h-3.5" /> Add
                </button>
            </HeaderActionPortal>

            {!lib ? (
                <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary flex items-center gap-2" data-testid="strategy-center-loading"><Loader2 className="w-4 h-4 animate-spin" /> LOADING LIBRARY</div>
            ) : lib.length === 0 ? (
                <div className="panel p-10 text-center" data-testid="library-empty">
                    <div className="font-mono text-sm text-atlas-textSecondary">No strategies match these filters.</div>
                    <button onClick={clearFilters} className="mt-3 font-mono text-[11px] text-atlas-cyan hover:underline">Clear filters</button>
                </div>
            ) : (
                (() => {
                    const metricOf = (s) => (s.internal || s.wireable) ? metrics?.[s.engine_key] : null;
                    const deployed = lib.filter((s) => isLiveMetric(metricOf(s)));
                    const rest = lib.filter((s) => !isLiveMetric(metricOf(s)));
                    const common = { metricOf, isOwner, onOpen: routeOpen, onDeploy: load };
                    return (
                        <div className="space-y-5" data-testid="strategy-grid">
                            <LibrarySection label="LIVE / PAPER" items={deployed} testid="strategy-section-live" {...common} />
                            <LibrarySection label="TEST & EDIT" items={rest} testid="strategy-section-test" {...common} />
                        </div>
                    );
                })()
            )}

            <AddStrategyChooser open={addChooser} onOpenChange={setAddChooser}
                onImport={() => { setAddChooser(false); onImport(); }}
                onCreate={() => { setAddChooser(false); onBuild(); }}
                onClone={() => { setAddChooser(false); setCloneOpen(true); }} />

            <CloneStrategyPicker open={cloneOpen} onOpenChange={setCloneOpen} lib={lib}
                onCloned={() => { setCloneOpen(false); load(); }} />

            {showFilter && (
                <FilterDrawer facets={facets} filters={filters} favOnly={favOnly} activeCount={activeCount}
                    onToggle={toggleFilter} onFav={() => setFavOnly((v) => !v)} onClear={clearFilters}
                    onClose={() => setShowFilter(false)} />
            )}
            {searchOpen && (
                <SearchScreen lib={lib} query={query} setQuery={setQuery} activeCount={activeCount}
                    onOpenFilters={() => { setSearchOpen(false); setShowFilter(true); }}
                    onOpen={(s) => { setSearchOpen(false); routeOpen(s); }}
                    onClose={() => setSearchOpen(false)} />
            )}
        </div>
    );
}

/* Add-strategy chooser — clean, guided options (AI demoted to a secondary link). */
function AddStrategyChooser({ open, onOpenChange, onImport, onCreate, onClone }) {
    return (
        <LabModal open={open} onOpenChange={onOpenChange} icon={Plus} title="Add a strategy"
            subtitle="Pick how you want to start — you can refine everything afterwards." testid="add-strategy-chooser">
            <div className="space-y-4 p-1 py-2">
                <button data-testid="add-option-create" onClick={onCreate}
                    className="group w-full text-left rounded-xl border border-atlas-cyan/40 bg-atlas-cyan/5 px-4 py-5 flex items-center gap-3.5 hover:bg-atlas-cyan/10 transition-colors">
                    <span className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-cyan/40 bg-atlas-cyan/10 shrink-0"><Boxes className="w-5 h-5 text-atlas-cyan" /></span>
                    <span className="min-w-0">
                        <span className="block font-heading text-sm text-atlas-text">Create New Strategy</span>
                        <span className="block font-mono text-[11px] text-atlas-textTertiary mt-1 leading-relaxed">Build rules step-by-step in the guided builder.</span>
                    </span>
                    <ArrowLeft className="w-4 h-4 text-atlas-textTertiary rotate-180 ml-auto shrink-0 group-hover:text-atlas-cyan transition-colors" />
                </button>
                <button data-testid="add-option-clone" onClick={onClone}
                    className="group w-full text-left rounded-xl border border-atlas-border px-4 py-5 flex items-center gap-3.5 hover:bg-atlas-panelHover transition-colors">
                    <span className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border shrink-0"><Copy className="w-5 h-5 text-atlas-cyan" /></span>
                    <span className="min-w-0">
                        <span className="block font-heading text-sm text-atlas-text">Copy Existing</span>
                        <span className="block font-mono text-[11px] text-atlas-textTertiary mt-1 leading-relaxed">Duplicate a rule-based strategy as a starting point, then tweak it.</span>
                    </span>
                    <ArrowLeft className="w-4 h-4 text-atlas-textTertiary rotate-180 ml-auto shrink-0 group-hover:text-atlas-text transition-colors" />
                </button>
                <button data-testid="add-option-import" onClick={onImport}
                    className="group w-full text-left rounded-xl border border-atlas-border px-4 py-5 flex items-center gap-3.5 hover:bg-atlas-panelHover transition-colors">
                    <span className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border shrink-0"><FileJson className="w-5 h-5 text-atlas-cyan" /></span>
                    <span className="min-w-0">
                        <span className="block font-heading text-sm text-atlas-text">Import JSON</span>
                        <span className="block font-mono text-[11px] text-atlas-textTertiary mt-1 leading-relaxed">Paste a strategy definition (JSON, Pine, Freqtrade…) to convert.</span>
                    </span>
                    <ArrowLeft className="w-4 h-4 text-atlas-textTertiary rotate-180 ml-auto shrink-0 group-hover:text-atlas-text transition-colors" />
                </button>
                <div className="pt-3 mt-1 border-t border-atlas-border/60">
                    <button data-testid="add-option-ai" onClick={onCreate}
                        className="w-full flex items-center justify-center gap-1.5 font-mono text-[10px] text-atlas-textTertiary hover:text-atlas-textSecondary transition-colors py-1">
                        <Sparkles className="w-3 h-3" /> Prefer to describe it in words? Build with AI (advanced)
                    </button>
                </div>
            </div>
        </LabModal>
    );
}

/* Copy-existing picker — lists rule-based strategies that can be duplicated. */
function CloneStrategyPicker({ open, onOpenChange, lib, onCloned }) {
    const [busy, setBusy] = useState(null); // id being cloned
    const cloneable = (lib || []).filter((s) => s.wireable && !s.internal && !s.reference_only);

    const doClone = async (s) => {
        setBusy(s.id);
        try {
            const res = await api.libraryClone(s.id);
            toast.success(`Copied — "${res?.strategy?.name || s.name}" added to your library`);
            onCloned();
        } catch (e) {
            toast.error(String(e?.response?.data?.detail || e?.message || "Couldn't copy that strategy"));
        } finally {
            setBusy(null);
        }
    };

    return (
        <LabModal open={open} onOpenChange={onOpenChange} icon={Copy} title="Copy an existing strategy"
            subtitle="Pick a rule-based strategy to duplicate. You'll get an editable copy you can tune freely." testid="clone-strategy-picker">
            {cloneable.length === 0 ? (
                <div className="py-8 text-center font-mono text-[11px] text-atlas-textTertiary" data-testid="clone-empty">
                    No rule-based strategies available to copy yet. Core engine strategies (Hunter, Squeeze, Continuation) use built-in logic and can&apos;t be copied.
                </div>
            ) : (
                <div className="space-y-2 max-h-[24rem] overflow-y-auto atlas-scroll p-1">
                    {cloneable.map((s) => {
                        const Icon = ICONS[s.engine_key] || Copy;
                        return (
                            <button key={s.id} data-testid={`clone-option-${s.id}`} onClick={() => doClone(s)} disabled={busy}
                                className="group w-full text-left rounded-xl border border-atlas-border px-3.5 py-3 flex items-center gap-3 hover:border-atlas-cyan/40 hover:bg-atlas-panelHover transition-colors disabled:opacity-50">
                                <span className="w-9 h-9 rounded-lg grid place-items-center border border-atlas-border bg-atlas-cyan/5 shrink-0"><Icon className="w-4 h-4 text-atlas-cyan" /></span>
                                <span className="min-w-0 flex-1">
                                    <span className="block font-heading text-sm text-atlas-text truncate">{s.name}</span>
                                    <span className="block font-mono text-[10px] text-atlas-textTertiary truncate">{s.style || s.category || "Rule-based"}</span>
                                </span>
                                {busy === s.id ? <Loader2 className="w-4 h-4 animate-spin text-atlas-cyan shrink-0" /> : <Copy className="w-4 h-4 text-atlas-textTertiary group-hover:text-atlas-cyan shrink-0" />}
                            </button>
                        );
                    })}
                </div>
            )}
        </LabModal>
    );
}

/* Full-screen search — text query + current filters, strategies listed by name (leaderboard-style). */
function SearchScreen({ lib, query, setQuery, activeCount, onOpenFilters, onOpen, onClose }) {
    const rows = lib || [];
    return (
        <div className="fixed inset-0 z-50 bg-atlas-bg flex flex-col" data-testid="strategy-search-screen">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-atlas-border">
                <Search className="w-4 h-4 text-atlas-textTertiary shrink-0" />
                <input autoFocus data-testid="strategy-search-input" value={query} onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search the strategy library…"
                    className="flex-1 bg-transparent outline-none font-mono text-sm text-white placeholder:text-atlas-textTertiary" />
                <button data-testid="strategy-search-filters" onClick={onOpenFilters}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full font-mono text-[10px] border transition-all ${activeCount ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary"}`}>
                    <SlidersHorizontal className="w-3 h-3" /> Filter{activeCount ? ` · ${activeCount}` : ""}
                </button>
                <button data-testid="strategy-search-close" onClick={onClose} className="text-atlas-textTertiary hover:text-atlas-text ml-1"><X className="w-5 h-5" /></button>
            </div>
            <div className="flex-1 overflow-y-auto atlas-scroll p-3 space-y-1">
                {rows.length === 0 ? (
                    <div className="p-8 text-center font-mono text-[12px] text-atlas-textSecondary">No strategies match your search.</div>
                ) : rows.map((s) => (
                    <button key={s.id} data-testid={`search-row-${s.id}`} onClick={() => onOpen(s)}
                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg bg-atlas-panelHover/40 border border-atlas-border hover:border-atlas-cyan/40 transition-colors text-left">
                        <span className="font-heading text-sm text-atlas-text flex-1 truncate">{s.name}</span>
                        <span className="font-mono text-[9px] text-atlas-textTertiary truncate hidden sm:inline">{s.style}</span>
                        <span className={`font-mono text-[8px] font-bold uppercase px-1.5 py-0.5 rounded-full border ${GRADE_CLS[s.ai_grade] || GRADE_CLS.C}`}>{s.ai_grade}</span>
                    </button>
                ))}
            </div>
        </div>
    );
}

function FilterDrawer({ facets, filters, favOnly, activeCount, onToggle, onFav, onClear, onClose }) {
    return (
        <div className="fixed inset-0 z-50 flex justify-end" data-testid="filter-drawer">
            <div className="absolute inset-0 bg-black/60" onClick={onClose} />
            <div className="relative w-full max-w-sm h-full bg-atlas-bg border-l border-atlas-border overflow-y-auto p-5 space-y-5">
                <div className="flex items-center justify-between sticky top-0 bg-atlas-bg pb-2">
                    <div className="font-heading text-lg text-atlas-text">Filters{activeCount ? ` · ${activeCount}` : ""}</div>
                    <button data-testid="filter-close" onClick={onClose} className="text-atlas-textTertiary hover:text-atlas-text"><X className="w-5 h-5" /></button>
                </div>
                <button data-testid="filter-favorites" onClick={onFav}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg border font-mono text-xs transition-all ${favOnly ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary"}`}>
                    <Heart className={`w-4 h-4 ${favOnly ? "fill-atlas-cyan" : ""}`} /> Favorites only
                </button>
                {FILTER_FIELDS.map(({ key, label }) => (
                    <div key={key}>
                        <div className="label-tag mb-2">{label}</div>
                        <div className="flex flex-wrap gap-2">
                            {(facets[key] || []).map((val) => {
                                const active = (filters[key] || []).includes(val);
                                return (
                                    <button key={val} data-testid={`filter-${key}-${val}`} onClick={() => onToggle(key, val)}
                                        className={`px-2.5 py-1 rounded-full font-mono text-[10px] border transition-all ${active ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>
                                        {val}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}
                <div className="flex gap-2 pt-2">
                    <Button data-testid="filter-clear" variant="outline" onClick={onClear} className="flex-1 font-mono text-xs">Clear</Button>
                    <Button data-testid="filter-apply" onClick={onClose} className="flex-1 font-mono text-xs bg-atlas-cyan text-atlas-bg hover:bg-cyan-400">Show results</Button>
                </div>
            </div>
        </div>
    );
}


function timeAgo(ts) {
    if (!ts) return null;
    const d = (Date.now() - new Date(ts).getTime()) / 1000;
    if (isNaN(d)) return null;
    if (d < 3600) return `${Math.max(1, Math.floor(d / 60))}m ago`;
    if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
    return `${Math.floor(d / 86400)}d ago`;
}

function LibrarySection({ label, items, testid, metricOf, isOwner, onOpen, onDeploy }) {
    if (!items.length) return null;
    return (
        <div className="space-y-3" data-testid={testid}>
            <div className="label-tag">{label} · {items.length}</div>
            <div className="grid grid-cols-2 gap-3 md:gap-5">
                {items.map((s) => (
                    <LibraryCard key={s.id} s={s} metric={metricOf(s)} isOwner={isOwner}
                        onOpen={() => onOpen(s)}
                        onDeploy={onDeploy} />
                ))}
            </div>
        </div>
    );
}


function LibraryCard({ s, metric, isOwner, onOpen, onDeploy }) {
    const Icon = ICONS[s.engine_key] || CATEGORY_ICON[s.category] || Boxes;
    const wired = !!(s.internal || (s.wireable && s.engine_key));
    const [localStatus, setLocalStatus] = useState(null);
    const status = localStatus || (wired ? (metric?.status || "PAPER") : "CATALOG");
    const deployed = status === "PAPER" || status === "LIVE";
    const [deploying, setDeploying] = useState(false);

    const deploy = async (e) => {
        e.stopPropagation();
        if (!isOwner) { toast.error("Owner login required to deploy"); return; }
        if (deployed) { onOpen(); return; }  // already live/paper → open detail to manage
        setDeploying(true);
        try {
            const next = await api.strategySetState(s.engine_key, { enabled: true });
            setLocalStatus(next.status || "PAPER");  // optimistic — flip the badge instantly
            toast.success("Deployed to paper engine", { description: `${s.name} → ${next.status || "PAPER"}` });
            onDeploy?.();
        } catch (err) { toast.error("Deploy failed", { description: String(err?.response?.data?.detail || err?.message) }); }
        finally { setDeploying(false); }
    };

    // One consistent activity line for every card.
    const last = metric?.last_trade ? timeAgo(metric.last_trade) : null;
    const activity = wired
        ? (metric?.trades ? `${metric.trades} trade${metric.trades === 1 ? "" : "s"}${last ? ` · last ${last}` : ""}` : "No trades yet")
        : `${s.style || s.category || "Catalog"}`;

    return (
        <div data-testid={`library-card-${s.id}`}
            className="group relative text-left rounded-2xl border border-atlas-border bg-atlas-panel/70 p-5 flex flex-col gap-3.5 transition-all hover:-translate-y-0.5 hover:bg-atlas-panelHover hover:shadow-[0_16px_50px_-20px_rgba(0,0,0,0.95)]">
            <button onClick={onOpen} className="absolute inset-0 z-0" aria-label={`Open ${s.name}`} data-testid={`library-open-${s.id}`} />
            <div className="flex items-start justify-between gap-2 relative z-10 pointer-events-none">
                <div className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5">
                    <Icon className="w-5 h-5 text-atlas-cyan" strokeWidth={2} />
                </div>
                <div className="flex items-center gap-2 pointer-events-auto">
                    {!s.reference_only && (
                        <button data-testid={`card-edit-${s.id}`} onClick={(e) => { e.stopPropagation(); onOpen(); }} title="Edit strategy"
                            className="text-atlas-textTertiary hover:text-atlas-cyan transition-colors">
                            <Pencil className="w-4 h-4" />
                        </button>
                    )}
                    <span data-testid={`card-status-${s.id}`}
                        className={`flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${STATUS[status] || "text-atlas-textTertiary border-atlas-border bg-atlas-panel"}`}>
                        <span className="w-1.5 h-1.5 rounded-full bg-current" /> {status}
                    </span>
                </div>
            </div>
            <div className="relative z-10 pointer-events-none">
                <div className="font-heading font-medium text-base md:text-lg text-atlas-text leading-tight truncate">{s.name}</div>
                <div className="font-body text-xs text-atlas-textSecondary mt-1.5 leading-relaxed line-clamp-2 min-h-[2.25rem]">{s.description || s.ideal_market || "—"}</div>
                <div className="font-mono text-[9px] text-atlas-textTertiary mt-2 truncate">{activity}</div>
            </div>
            {!wired && s.reference_only ? (
                <div data-testid={`card-reference-note-${s.id}`}
                    className="relative z-10 pointer-events-none rounded-lg border border-dashed border-atlas-border bg-atlas-bg/40 py-2 px-3 text-center font-mono text-[9px] uppercase tracking-wider text-atlas-textTertiary">
                    {s.reference_note || "Analysis only"}
                </div>
            ) : (
                <div className="relative z-10 pointer-events-auto flex justify-end mt-auto pt-3.5 border-t border-atlas-border">
                    {wired ? (
                        <button data-testid={`card-deploy-${s.id}`} onClick={deploy} disabled={deploying}
                            className="flex items-center justify-center gap-1.5 rounded-lg border border-atlas-cyan/50 bg-atlas-cyan/10 px-5 py-2 font-mono text-[10px] font-bold tracking-widest text-atlas-cyan hover:bg-atlas-cyan/20 transition-all disabled:opacity-50">
                            {deploying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" strokeWidth={2.5} />}
                            {deployed ? "MANAGE" : "DEPLOY"}
                        </button>
                    ) : (
                        <button data-testid={`card-view-${s.id}`} onClick={(e) => { e.stopPropagation(); onOpen(); }}
                            className="rounded-lg border border-atlas-border px-5 py-2 font-mono text-[10px] font-bold tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-all">
                            VIEW
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

const CATEGORY_ICON = {
    "Trend Following": TrendingUp, "Momentum": Activity, "Mean Reversion": BarChart3,
    "Volatility": Zap, "Statistical / Quantitative": GitBranch, "Academic / Institutional": Brain,
};

function Kv({ label, value, cls = "text-atlas-text" }) {
    return (
        <div className="flex items-center justify-between gap-2">
            <span className="text-atlas-textTertiary">{label}</span>
            <span className={`font-bold tabular-nums ${cls}`}>{value}</span>
        </div>
    );
}

/* ---------------- Detail view ---------------- */
const fmtPf = (x) => (x == null ? "—" : (x >= 999 ? "∞" : Number(x).toFixed(2)));

function StrategyDetail({ sKey, schema, metric, isOwner, onBack, onChanged }) {
    const [status, setStatus] = useState(metric?.status || "PAPER");
    const [showMore, setShowMore] = useState(false);
    const [showParams, setShowParams] = useState(false);
    const [showManage, setShowManage] = useState(false);
    const [deploying, setDeploying] = useState(false);
    const [configOpen, setConfigOpen] = useState(false);
    const [configFocus, setConfigFocus] = useState("regime");
    const paramsRef = useRef(null);
    const Icon = ICONS[sKey] || Boxes;
    const grade = schema?.ai_grade || metric?.grade;
    const stars = metric?.stars ?? Math.round((metric?.health ?? 0) / 20);
    const deployed = status === "PAPER" || status === "LIVE";

    // Live/Off is driven by the Strategy Profile `enabled` flag (regime/exit gating handled in Edit).
    const [profile, setProfile] = useState(null);
    const [live, setLive] = useState(null);
    const [savingLive, setSavingLive] = useState(false);
    useEffect(() => {
        let active = true;
        api.strategyProfile(sKey).then((d) => { if (active) { setProfile(d.profile); setLive(d.profile?.enabled !== false); } }).catch(() => {});
        return () => { active = false; };
    }, [sKey]);
    const toggleLive = async (v) => {
        if (!isOwner || savingLive || live === v) return;
        setLive(v);
        setSavingLive(true);
        try {
            await api.strategyProfileSave(sKey, {
                enabled: v,
                allowed_regimes: profile?.allowed_regimes || [],
                exit_method: profile?.exit_method || "native",
                exit_params: profile?.exit_params || {},
            });
            const d = await api.strategyProfile(sKey);
            setProfile(d.profile);
            onChanged?.();
        } catch (e) {
            setLive(!v);
            toast.error(isOwner ? "Update failed" : "Sign in to change this");
        } finally { setSavingLive(false); }
    };

    const setState = async (patch) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try {
            const r = await api.strategySetState(sKey, patch);
            if (r.status) setStatus(r.status);
            toast.success("Strategy updated", { description: JSON.stringify(patch) });
            onChanged?.();
        } catch (e) { toast.error("Update failed", { description: String(e?.response?.data?.detail || e?.message) }); }
    };

    const deployToPaper = async () => {
        if (!isOwner) { toast.error("Owner login required to deploy"); return; }
        setDeploying(true);
        try {
            const r = await api.strategySetState(sKey, { enabled: true });
            if (r.status) setStatus(r.status);
            toast.success("Deployed to paper engine", { description: `${schema?.name || sKey} → ${r.status || "PAPER"}` });
            onChanged?.();
        } catch (e) { toast.error("Deploy failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setDeploying(false); }
    };

    // "Test in Research Lab" → jump into the Validate wizard with THIS strategy pre-selected.
    const testStrategy = () => {
        useResearchStore.setState({ strat: [sKey], step: 1, phase: "idle", runs: [], progress: 0 });
        localStorage.setItem("ananta_research_sub", "validate");
        window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "research" } }));
    };
    const openParams = () => { setShowParams(true); setTimeout(() => paramsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 90); };

    // "Best used in" — best-effort extraction from the strategy DNA.
    const dna = schema?.dna && typeof schema.dna === "object" ? schema.dna : {};
    const pick = (...keys) => { for (const k of keys) { const v = dna[k]; if (v && typeof v !== "object") return String(v); } return null; };
    const dnaItems = [
        ["Purpose", pick("purpose", "edge", "thesis", "objective")],
        ["Works best", pick("works_best", "ideal_market", "ideal", "best_in", "regime") || schema?.ideal_market],
        ["Avoid", pick("avoid", "avoid_conditions", "weakness", "worst_in")],
    ].filter(([, v]) => v);
    const dnaRows = Object.entries(dna).filter(([, v]) => typeof v !== "object");
    const recent = metric?.recent_form || [];

    return (
        <div className="space-y-4" data-testid={`strategy-detail-${sKey}`}>
            {/* top: identity + status/grade */}
            <div className="panel border-atlas-border rounded-2xl p-5">
                <button data-testid="detail-back-btn" onClick={onBack} className="flex items-center gap-1.5 font-mono text-[10px] text-atlas-textTertiary hover:text-atlas-text mb-3">
                    <ArrowLeft className="w-3.5 h-3.5" /> ALL STRATEGIES
                </button>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3 min-w-0">
                        <div className="w-12 h-12 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5 shrink-0">
                            <Icon className="w-6 h-6 text-atlas-cyan" strokeWidth={2} />
                        </div>
                        <div className="min-w-0">
                            <div className="font-heading font-medium text-xl md:text-2xl text-atlas-text leading-tight truncate">{schema?.name || sKey}</div>
                            <div className="font-body text-xs text-atlas-textSecondary mt-0.5 line-clamp-1">{schema?.ideal_market || (schema?.description || "").split(". ")[0] || `v${schema?.version || "1.0.0"}`}</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        {grade && <span className={`font-mono text-[9px] font-bold uppercase px-2.5 py-1.5 rounded-lg border ${GRADE_CLS[grade] || GRADE_CLS.C}`} data-testid="detail-grade">Grade {grade}</span>}
                        <div className="flex items-center rounded-xl border border-atlas-border bg-atlas-panel p-0.5" data-testid="strategy-live-toggle" style={{ opacity: (!isOwner || savingLive) ? 0.6 : 1 }}>
                            {[{ v: true, label: "Live" }, { v: false, label: "Off" }].map(({ v, label }) => {
                                const active = live === v;
                                return (
                                    <button key={label} data-testid={`toggle-${label.toLowerCase()}`} disabled={!isOwner || savingLive}
                                        onClick={() => toggleLive(v)}
                                        className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-[11px] font-bold uppercase tracking-wide transition-all ${
                                            active && v ? "bg-atlas-positive/15 text-atlas-positive border border-atlas-positive/60"
                                            : active && !v ? "bg-atlas-panel2 text-atlas-textSecondary border border-atlas-border"
                                            : "text-atlas-textTertiary border border-transparent hover:text-atlas-text"}`}>
                                        {active && v ? <span className="w-1.5 h-1.5 rounded-full bg-atlas-positive animate-pulse" /> : null}
                                        {label}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </div>

            {/* 5 key metrics */}
            <div data-testid="detail-metrics-wrap">
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3" data-testid="detail-metrics">
                    <Stat label="Win Rate" value={`${metric?.win_rate ?? 0}%`} />
                    <Stat label="Total P&L" value={`${(metric?.total_pnl ?? 0) >= 0 ? "+" : "-"}$${Math.abs(metric?.total_pnl ?? 0)}`} cls={(metric?.total_pnl ?? 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative/70"} />
                    <Stat label="Max Drawdown" value={`${metric?.max_drawdown_pct ?? 0}%`} cls="text-atlas-negative/70" />
                    <Stat label="Profit Factor" value={fmtPf(metric?.profit_factor)} />
                    <div className="rounded-lg border border-atlas-border bg-atlas-panel px-3 py-2.5" data-testid="detail-recent-form">
                        <div className="font-mono text-[9px] uppercase tracking-wider text-atlas-textTertiary">Recent Form</div>
                        <div className="flex items-center gap-1 mt-1.5">
                            {recent.length ? recent.slice(-6).map((f, i) => (
                                <span key={i} className={`w-4 h-4 rounded grid place-items-center font-mono text-[8px] font-bold ${f === "W" ? "bg-atlas-positive/15 text-atlas-positive" : "bg-atlas-negative/15 text-atlas-negative"}`}>{f}</span>
                            )) : <span className="font-heading font-bold text-lg text-atlas-textTertiary">—</span>}
                        </div>
                    </div>
                </div>
                <div className="font-mono text-[9px] text-atlas-textTertiary mt-2" data-testid="detail-metrics-context">
                    Based on the current backtest window — not a live-trading result.
                </div>
            </div>

            {/* how it works */}
            <div className="panel border-atlas-border rounded-xl p-5" data-testid="detail-how-it-works">
                <div className="label-tag mb-2">HOW IT WORKS</div>
                <p className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed">{schema?.description || "No description available for this strategy."}</p>
            </div>

            {/* best used in */}
            {dnaItems.length > 0 && (
                <div className="panel border-atlas-border rounded-xl p-5" data-testid="detail-best-used-in">
                    <div className="label-tag mb-3">BEST USED IN</div>
                    <div className="space-y-2.5">
                        {dnaItems.map(([k, v]) => (
                            <div key={k} className="flex gap-3 font-mono text-[11px]">
                                <span className="text-atlas-textTertiary w-24 shrink-0 uppercase tracking-wide">{k}</span>
                                <span className="text-atlas-text">{v}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* show more (secondary detail) */}
            <button data-testid="detail-show-more" onClick={() => setShowMore((v) => !v)}
                className="w-full flex items-center justify-center gap-1.5 rounded-xl border border-atlas-border/50 py-2.5 font-mono text-[11px] tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-border transition-colors">
                {showMore ? <ChevronDown className="w-3.5 h-3.5 rotate-180" /> : <ChevronDown className="w-3.5 h-3.5" />}
                {showMore ? "SHOW LESS" : "SHOW MORE — health, live snapshot, AI analysis"}
            </button>
            {showMore && (
                <div className="space-y-4" data-testid="detail-more">
                    <HealthCard metric={metric} />
                    <div className="panel border-atlas-border rounded-xl p-5">
                        <div className="label-tag mb-3">LIVE SNAPSHOT</div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <Stat label="Trades" value={metric?.trades ?? 0} />
                            <Stat label="Confidence" value={`${metric?.confidence ?? 0}%`} />
                            <Stat label="Rating" value={`${stars}★`} />
                            <Stat label="Last Trade" value={metric?.last_trade ? new Date(metric.last_trade).toLocaleDateString() : "—"} />
                        </div>
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
                    <TimelinePanel metric={metric} />
                    <AIAnalystTerminal isOwner={isOwner} strategy={sKey} />
                </div>
            )}

            {/* single primary action */}
            <div className="pt-1">
                <button data-testid="edit-strategy-btn" onClick={() => setConfigOpen(true)}
                    className="w-full flex items-center justify-center gap-2 rounded-xl bg-atlas-cyan text-atlas-bg font-mono text-[13px] font-bold tracking-wide py-4 hover:brightness-110 active:scale-[0.99] transition-all">
                    <SlidersHorizontal className="w-4 h-4" /> EDIT STRATEGY
                </button>
            </div>
            <StrategyConfigModal open={configOpen} onClose={() => setConfigOpen(false)} strategyKey={sKey}
                strategyName={schema?.name || sKey} isOwner={isOwner}
                onSaved={() => { onChanged?.(); api.strategyProfile(sKey).then((d) => { setProfile(d.profile); setLive(d.profile?.enabled !== false); }).catch(() => {}); }} />
        </div>
    );
}


function Stat({ label, value, cls = "text-atlas-text" }) {
    return (
        <div className="rounded-lg border border-atlas-border bg-atlas-panel px-3 py-2.5">
            <div className="font-mono text-[9px] uppercase tracking-wider text-atlas-textTertiary">{label}</div>
            <div className={`font-heading font-bold text-lg md:text-xl tabular-nums mt-0.5 ${cls}`}>{value}</div>
        </div>
    );
}

/* ---------------- Health Score (transparent breakdown) ---------------- */
function healthColor(v) {
    return v >= 60 ? "text-atlas-positive" : v >= 35 ? "text-atlas-warning" : "text-atlas-negative";
}
function healthBar(v) {
    return v >= 60 ? "bg-atlas-positive" : v >= 35 ? "bg-atlas-warning" : "bg-atlas-negative";
}

function HealthCard({ metric }) {
    const score = metric?.health ?? 0;
    const comps = metric?.health_breakdown || [];
    const stars = Math.round(score / 20);
    // gauge geometry
    const R = 42, C = 2 * Math.PI * R, pct = Math.max(0, Math.min(100, score));
    return (
        <div className="panel border-atlas-border rounded-xl p-5" data-testid="strategy-health-card">
            <div className="flex items-center gap-2 mb-4">
                <HeartPulse className="w-4 h-4 text-atlas-cyan" />
                <span className="label-tag">STRATEGY HEALTH</span>
                <MetricExplainer metric="health" value={score} side="bottom" />
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-6">
                {/* radial gauge */}
                <div className="relative shrink-0" style={{ width: 108, height: 108 }}>
                    <svg width="108" height="108" className="-rotate-90">
                        <circle cx="54" cy="54" r={R} fill="none" stroke="currentColor" strokeWidth="9" className="text-atlas-border" />
                        <circle cx="54" cy="54" r={R} fill="none" strokeWidth="9" strokeLinecap="round"
                            className={healthColor(score)} stroke="currentColor"
                            strokeDasharray={C} strokeDashoffset={C - (pct / 100) * C}
                            style={{ transition: "stroke-dashoffset 0.8s ease" }} />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className={`font-heading font-bold text-3xl tabular-nums ${healthColor(score)}`} data-testid="health-score-value">{score}</span>
                        <span className="font-mono text-[8px] text-atlas-textTertiary uppercase tracking-wider">/ 100</span>
                    </div>
                </div>
                {/* stars + component bars */}
                <div className="flex-1 w-full space-y-2.5">
                    <div className="flex items-center gap-1 mb-1">
                        {[1, 2, 3, 4, 5].map((n) => <Star key={n} className={`w-4 h-4 ${n <= stars ? "text-atlas-warning fill-atlas-warning" : "text-atlas-textTertiary"}`} />)}
                        <span className="font-mono text-[10px] text-atlas-textTertiary ml-1.5">{score >= 60 ? "Healthy" : score >= 35 ? "Needs work" : "At risk"}</span>
                    </div>
                    {comps.map((c) => (
                        <div key={c.key} className="group" title={c.detail} data-testid={`health-comp-${c.key}`}>
                            <div className="flex items-center justify-between font-mono text-[10px] mb-0.5">
                                <span className="text-atlas-textSecondary flex items-center gap-1">{c.label}{(c.key === "win_rate" || c.key === "risk") && <MetricExplainer metric={c.key === "risk" ? "roi" : "win_rate"} value={c.score} />}</span>
                                <span className={`tabular-nums font-bold ${healthColor(c.score)}`}>{c.score}</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-atlas-panel overflow-hidden">
                                <div className={`h-full rounded-full ${healthBar(c.score)}`} style={{ width: `${Math.max(2, c.score)}%`, transition: "width 0.6s ease" }} />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ---------------- Lifecycle Timeline ---------------- */
function fmtTs(ts) {
    if (!ts) return null;
    try { return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); }
    catch { return null; }
}

function TimelinePanel({ metric }) {
    const events = metric?.timeline || [];
    if (!events.length) {
        return <div className="panel border-atlas-border rounded-xl p-5 font-mono text-[11px] text-atlas-textTertiary">No lifecycle data yet.</div>;
    }
    return (
        <div className="panel border-atlas-border rounded-xl p-5" data-testid="strategy-timeline">
            <div className="flex items-center gap-2 mb-5"><GitBranch className="w-4 h-4 text-atlas-cyan" /><span className="label-tag">LIFECYCLE TIMELINE</span></div>
            <div className="relative pl-6">
                <div className="absolute left-[9px] top-1 bottom-1 w-px bg-atlas-border" />
                {events.map((e, i) => {
                    const done = !!e.done;
                    const Icon = done ? CheckCircle2 : Circle;
                    return (
                        <div key={e.key} className="relative pb-5 last:pb-0" data-testid={`timeline-${e.key}`}>
                            <span className={`absolute -left-[23px] top-0.5 grid place-items-center w-[19px] h-[19px] rounded-full bg-atlas-bg ${done ? "text-atlas-cyan" : "text-atlas-textTertiary"}`}>
                                <Icon className="w-[15px] h-[15px]" strokeWidth={done ? 2.4 : 1.8} fill={done ? "currentColor" : "none"} fillOpacity={done ? 0.15 : 0} />
                            </span>
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                                <span className={`font-heading text-sm ${done ? "text-atlas-text" : "text-atlas-textTertiary"}`}>{e.label}</span>
                                {fmtTs(e.ts) && (
                                    <span className="flex items-center gap-1 font-mono text-[9px] text-atlas-textTertiary"><Clock className="w-3 h-3" />{fmtTs(e.ts)}</span>
                                )}
                            </div>
                            <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">{e.detail}</div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}


/* ---------------- Catalog detail (non-engine library strategies) ---------------- */
function CatalogDetail({ id, isOwner, onOpenInternal, onBack }) {
    const [s, setS] = useState(null);
    const [grading, setGrading] = useState(false);
    const [backtesting, setBacktesting] = useState(false);
    const [deploying, setDeploying] = useState(false);
    const [engineState, setEngineState] = useState(null);
    const [renaming, setRenaming] = useState(false);
    const [nameInput, setNameInput] = useState("");
    const [savingName, setSavingName] = useState(false);
    const [deletingLib, setDeletingLib] = useState(false);

    const load = () => api.libraryGet(id).then((d) => {
        if (d.internal && d.engine_key) { onOpenInternal(d.engine_key); return; }
        setS(d);
    }).catch(() => toast.error("Failed to load strategy"));
    useEffect(() => { load(); }, [id]);
    useEffect(() => {
        if (s?.wireable && s?.engine_key) {
            api.strategyMetrics().then((m) => setEngineState(m?.metrics?.[s.engine_key] || null)).catch(() => {});
        }
    }, [s?.engine_key, s?.wireable]);

    const regrade = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setGrading(true);
        try {
            const g = await api.libraryAiGrade(id);
            toast.success(`Re-graded: ${g.ai_grade} · ${g.ai_health_score}/100`);
            await load();
        } catch (e) { toast.error("AI grade failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setGrading(false); }
    };

    const runBacktest = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setBacktesting(true);
        try {
            const r = await api.libraryBacktest(id);
            toast.success("Backtest complete", { description: `${r.historical_results.trade_count} trades · ROI ${r.historical_results.roi}% over ${r.days}d` });
            await load();
        } catch (e) { toast.error("Backtest failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setBacktesting(false); }
    };

    const toggleDeploy = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        const on = !!engineState?.enabled;
        setDeploying(true);
        try {
            const next = await api.strategySetState(s.engine_key, on ? { status: "DISABLED" } : { enabled: true });
            setEngineState((prev) => ({ ...(prev || {}), status: next.status, enabled: next.enabled }));
            toast.success(on ? "Disabled" : "Deployed to paper engine", { description: `${s.name} → ${next.status}` });
        } catch (e) { toast.error("Toggle failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setDeploying(false); }
    };

    // "Test in Research Lab" → jump into the Validate wizard with THIS wired strategy pre-selected.
    const testInLab = () => {
        useResearchStore.setState({ strat: [s.engine_key], step: 1, phase: "idle", runs: [], progress: 0 });
        localStorage.setItem("ananta_research_sub", "validate");
        window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "research" } }));
    };

    if (!s) return <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> LOADING</div>;
    const r = s.historical_results || {};
    const Icon = CATEGORY_ICON[s.category] || Boxes;
    const userAdded = !!(s.imported || s.origin === "clone");
    const deployed = !!engineState?.enabled;

    const startRename = () => { setNameInput(s.name || ""); setRenaming(true); };
    const saveRename = async () => {
        const name = nameInput.trim();
        if (!name || name === s.name) { setRenaming(false); return; }
        setSavingName(true);
        try {
            await api.libraryRename(id, name);
            toast.success("Renamed", { description: name });
            setRenaming(false);
            await load();
        } catch (e) { toast.error("Rename failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setSavingName(false); }
    };
    const deleteStrategy = async () => {
        if (deployed) { toast.error("Disable this strategy before deleting it"); return; }
        if (!window.confirm(`Delete "${s.name}" permanently? This removes the strategy and its saved parameters. This cannot be undone.`)) return;
        setDeletingLib(true);
        try {
            await api.libraryDelete(id);
            toast.success("Strategy deleted", { description: s.name });
            onBack();
        } catch (e) { toast.error("Delete failed", { description: String(e?.response?.data?.detail || e?.message) }); setDeletingLib(false); }
    };


    return (
        <div className="space-y-5" data-testid="catalog-detail">
            <button data-testid="catalog-back" onClick={onBack} className="flex items-center gap-2 font-mono text-[11px] text-atlas-textSecondary hover:text-atlas-text">
                <ArrowLeft className="w-4 h-4" /> Back to Library
            </button>

            <div className="panel p-5">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="w-12 h-12 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5 shrink-0"><Icon className="w-6 h-6 text-atlas-cyan" /></div>
                        <div className="min-w-0 flex-1">
                            {renaming ? (
                                <div className="flex items-center gap-2">
                                    <input data-testid="catalog-rename-input" autoFocus value={nameInput} maxLength={80}
                                        onChange={(e) => setNameInput(e.target.value)}
                                        onKeyDown={(e) => { if (e.key === "Enter") saveRename(); if (e.key === "Escape") setRenaming(false); }}
                                        className="flex-1 min-w-0 bg-atlas-panel border border-atlas-cyan/50 rounded-lg px-2.5 py-1.5 font-heading text-lg text-atlas-text outline-none" />
                                    <button data-testid="catalog-rename-save" onClick={saveRename} disabled={savingName}
                                        className="p-1.5 rounded-lg border border-atlas-cyan/50 bg-atlas-cyan/10 text-atlas-cyan disabled:opacity-50">
                                        {savingName ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                                    </button>
                                    <button data-testid="catalog-rename-cancel" onClick={() => setRenaming(false)} className="p-1.5 rounded-lg border border-atlas-border text-atlas-textTertiary hover:text-atlas-text"><X className="w-4 h-4" /></button>
                                </div>
                            ) : (
                                <div className="flex items-center gap-2 min-w-0">
                                    <div className="font-heading text-xl text-atlas-text truncate">{s.name}</div>
                                    {userAdded && isOwner && (
                                        <button data-testid="catalog-rename-btn" onClick={startRename} title="Rename"
                                            className="text-atlas-textTertiary hover:text-atlas-cyan shrink-0"><Pencil className="w-3.5 h-3.5" /></button>
                                    )}
                                </div>
                            )}
                            <div className="font-mono text-[10px] text-atlas-textTertiary">{s.style} · {s.category} · {s.source}</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className={`font-mono text-[9px] font-bold uppercase px-2.5 py-1 rounded-full border ${GRADE_CLS[s.ai_grade] || GRADE_CLS.C}`}>Grade {s.ai_grade}</span>
                        {s.imported && s.origin !== "clone" && <span data-testid="imported-badge" className="font-mono text-[9px] font-bold uppercase px-2.5 py-1 rounded-full border border-atlas-cyan/40 bg-atlas-cyan/10 text-atlas-cyan flex items-center gap-1"><Upload className="w-3 h-3" /> Imported</span>}
                        {s.origin === "clone" && <span data-testid="clone-badge" className="font-mono text-[9px] font-bold uppercase px-2.5 py-1 rounded-full border border-atlas-cyan/40 bg-atlas-cyan/10 text-atlas-cyan flex items-center gap-1"><Copy className="w-3 h-3" /> Copy</span>}
                        <button data-testid="catalog-favorite" onClick={() => api.libraryFavorite(id).then(load)} className="text-atlas-textTertiary hover:text-atlas-cyan" title="Favorite">
                            <Heart className={`w-5 h-5 ${s.favorite ? "fill-atlas-cyan text-atlas-cyan" : ""}`} />
                        </button>
                        {userAdded && isOwner && (
                            <button data-testid="catalog-delete-btn" onClick={deleteStrategy} disabled={deletingLib} title={deployed ? "Disable before deleting" : "Delete strategy"}
                                className="text-atlas-textTertiary hover:text-atlas-negative disabled:opacity-40">
                                {deletingLib ? <Loader2 className="w-5 h-5 animate-spin" /> : <Trash2 className="w-5 h-5" />}
                            </button>
                        )}
                    </div>
                </div>
                <p className="font-mono text-xs text-atlas-textSecondary mt-3 leading-relaxed">{s.description}</p>
                {s.wireable && s.engine_key && (
                    <div className="mt-3 rounded-lg border border-atlas-cyan/30 bg-atlas-cyan/5 px-3 py-2.5 space-y-2.5">
                        <div className="flex items-center gap-2">
                            <Power className="w-4 h-4 text-atlas-cyan" />
                            <span className="font-mono text-[11px] text-atlas-text">Live-executable — runs in the paper engine via the declarative executor.</span>
                            {engineState && (
                                <span className={`ml-auto font-mono text-[9px] font-bold uppercase px-2 py-0.5 rounded-full border ${engineState.enabled ? "border-atlas-positive/40 bg-atlas-positive/10 text-atlas-positive" : "border-atlas-border text-atlas-textTertiary"}`}>
                                    {engineState.enabled ? (engineState.status || "PAPER") : "OFF"}
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                            <button data-testid="catalog-deploy-toggle" onClick={toggleDeploy} disabled={!isOwner || deploying}
                                className={`flex items-center gap-1.5 font-mono text-[10px] font-bold rounded px-3 py-1.5 border disabled:opacity-40 ${engineState?.enabled ? "border-atlas-border text-atlas-textSecondary hover:text-atlas-text" : "border-atlas-cyan/50 bg-atlas-cyan/10 text-atlas-cyan hover:bg-atlas-cyan/20"}`}>
                                {deploying ? <Loader2 className="w-3 h-3 animate-spin" /> : <Power className="w-3 h-3" />}
                                {engineState?.enabled ? "Disable" : "Deploy (Paper)"}
                            </button>
                            <button data-testid="catalog-backtest" onClick={runBacktest} disabled={!isOwner || backtesting}
                                className="flex items-center gap-1.5 font-mono text-[10px] font-bold rounded px-3 py-1.5 border border-atlas-border text-atlas-textSecondary hover:text-atlas-text disabled:opacity-40">
                                {backtesting ? <Loader2 className="w-3 h-3 animate-spin" /> : <BarChart3 className="w-3 h-3" />}
                                {backtesting ? "Backtesting…" : "Run Backtest"}
                            </button>
                            <button data-testid="catalog-test-lab" onClick={testInLab}
                                className="flex items-center gap-1.5 font-mono text-[10px] font-bold rounded px-3 py-1.5 border border-atlas-border text-atlas-textSecondary hover:text-atlas-text">
                                <ShieldCheck className="w-3 h-3" /> Test in Research Lab
                            </button>
                            <button data-testid="catalog-manage-engine" onClick={() => onOpenInternal(s.engine_key)}
                                className="ml-auto font-mono text-[10px] font-bold text-atlas-cyan hover:text-cyan-300 border border-atlas-cyan/40 rounded px-3 py-1.5 whitespace-nowrap">
                                Manage in Engine →
                            </button>
                        </div>
                        {s.backtested && s.backtest_meta && (
                            <div className="font-mono text-[9px] text-atlas-textTertiary">Backtested on {s.backtest_meta.symbol} · {s.backtest_meta.days}d · {s.backtest_meta.bars} bars</div>
                        )}
                    </div>
                )}
                <div className="flex flex-wrap gap-1.5 mt-3">
                    {(s.market_regimes || []).map((m) => <span key={m} className="font-mono text-[9px] px-2 py-0.5 rounded-full border border-atlas-border text-atlas-textSecondary">{m}</span>)}
                    <span className="font-mono text-[9px] px-2 py-0.5 rounded-full border border-atlas-border text-atlas-textSecondary">{s.risk}</span>
                    {(s.timeframes || []).map((t) => <span key={t} className="font-mono text-[9px] px-2 py-0.5 rounded-full border border-atlas-border text-atlas-textSecondary">{t}</span>)}
                </div>
            </div>

            {/* AI summary */}
            <div className="panel p-5" data-testid="catalog-ai">
                <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-atlas-cyan" /><span className="label-tag">AI ASSESSMENT</span></div>
                    <button data-testid="catalog-regrade" onClick={regrade} disabled={grading || !isOwner}
                        className="flex items-center gap-1.5 font-mono text-[10px] text-atlas-cyan hover:text-cyan-300 disabled:opacity-40">
                        {grading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Brain className="w-3 h-3" />} Re-grade with AI
                    </button>
                </div>
                <p className="font-mono text-xs text-atlas-text leading-relaxed">{s.ai_summary}</p>
                <div className="flex items-center gap-4 mt-3 font-mono text-[10px] text-atlas-textTertiary">
                    <span>Health <b className="text-atlas-text">{s.ai_health_score}/100</b></span>
                    <span>Confidence <b className="text-atlas-text">{s.ai_confidence}%</b></span>
                    <span>Recommended <b className="text-atlas-text">{s.recommended_market}</b></span>
                </div>
            </div>

            {/* performance */}
            <div className="panel p-5">
                <div className="label-tag mb-3">BACKTEST PERFORMANCE <span className="text-atlas-textTertiary normal-case">(seeded — run a real backtest to validate)</span></div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
                    {[["ROI", `${r.roi}%`], ["Win Rate", `${r.win_rate}%`], ["Profit Factor", r.profit_factor], ["Sharpe", r.sharpe],
                      ["Sortino", r.sortino], ["Max Drawdown", `${r.max_drawdown}%`], ["Avg Trade", `${r.avg_trade}%`], ["Trades", r.trade_count]].map(([k, v]) => (
                        <div key={k} className="rounded-lg border border-atlas-border bg-atlas-panel/50 p-2.5">
                            <div className="text-atlas-textTertiary text-[9px] uppercase tracking-wide">{k}</div>
                            <div className="text-atlas-text font-bold text-sm mt-0.5 tabular-nums">{v}</div>
                        </div>
                    ))}
                </div>
            </div>

            {/* rules */}
            <div className="grid md:grid-cols-2 gap-4">
                <RuleList title="Entry Rules" items={s.entry_rules} tone="positive" />
                <RuleList title="Exit Rules" items={s.exit_rules} tone="cyan" />
                <RuleList title="Ideal Conditions" items={s.ideal_conditions} tone="positive" />
                <RuleList title="Avoid Conditions" items={s.avoid_conditions} tone="negative" />
            </div>

            {/* imported strategy extras */}
            {s.imported && (
                <div className="space-y-4" data-testid="catalog-import-meta">
                    {s.conversion_report && (
                        <div className="panel p-5">
                            <div className="label-tag mb-2 flex items-center gap-2"><Upload className="w-3.5 h-3.5 text-atlas-cyan" /> Import &amp; Conversion Report
                                <span className="ml-auto font-mono text-[10px] text-atlas-textTertiary">{s.source_label} · {s.conversion_confidence}% confidence</span>
                            </div>
                            <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">{s.conversion_report}</p>
                        </div>
                    )}
                    {(s.indicators?.length > 0) && (
                        <div className="panel p-5">
                            <div className="label-tag mb-2">Indicators</div>
                            <div className="flex flex-wrap gap-1.5">
                                {s.indicators.map((ind, i) => (
                                    <span key={i} className="font-mono text-[10px] px-2 py-1 rounded-lg border border-atlas-border bg-atlas-panel/50 text-atlas-textSecondary">
                                        {ind.name}{ind.params && Object.keys(ind.params).length ? ` (${Object.entries(ind.params).map(([k, v]) => `${k}=${v}`).join(", ")})` : ""}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                    {(s.strengths?.length > 0 || s.weaknesses?.length > 0) && (
                        <div className="grid md:grid-cols-2 gap-4">
                            <RuleList title="Strengths" items={s.strengths} tone="positive" />
                            <RuleList title="Weaknesses" items={s.weaknesses} tone="negative" />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function RuleList({ title, items, tone }) {
    const dot = tone === "positive" ? "bg-atlas-positive" : tone === "negative" ? "bg-atlas-negative" : "bg-atlas-cyan";
    return (
        <div className="panel p-4">
            <div className="label-tag mb-2">{title}</div>
            <ul className="space-y-1.5">
                {(items || []).map((it, i) => (
                    <li key={i} className="flex items-start gap-2 font-mono text-[11px] text-atlas-textSecondary">
                        <span className={`mt-1.5 w-1.5 h-1.5 rounded-full ${dot} shrink-0`} />{it}
                    </li>
                ))}
            </ul>
        </div>
    );
}
