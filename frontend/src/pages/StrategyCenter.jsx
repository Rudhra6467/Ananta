import { useEffect, useState } from "react";
import {
    Boxes, TrendingUp, Zap, Activity, Plus, ArrowLeft, Copy, Download, Power, Search,
    Loader2, Star, ShieldCheck, BarChart3, Brain, Layers, FileJson, GitBranch, Store, Code, Sparkles,
    CheckCircle2, Circle, Clock, HeartPulse, Pencil, Flame, SlidersHorizontal, Heart, X, Upload,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import LabModal from "@/components/lab/LabModal";
import SavedConfigsPanel from "@/components/lab/SavedConfigsPanel";
import AIAnalystTerminal from "@/components/lab/AIAnalystTerminal";
import StrategyValidationPanel from "@/components/StrategyValidationPanel";
import HelpHint from "@/components/lab/HelpHint";
import StrategyArchitect from "@/pages/StrategyArchitect";
import ImportStrategyModal from "@/components/ImportStrategyModal";
import { useAuth } from "@/context/AuthContext";
import MetricExplainer from "@/components/MetricExplainer";
import HeaderActionPortal from "@/components/HeaderActionPortal";

const ICONS = { hunter: TrendingUp, squeeze: Zap, continuation: Activity };
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
            <StrategyLibrary metrics={metrics} isOwner={isOwner}
                onOpenInternal={setSelected} onOpenCatalog={setCatalogId}
                onImport={() => setImportOpen(true)} onBuild={() => setAddOpen(true)} />
            <StrategyArchitect open={addOpen} onOpenChange={setAddOpen} registry={registry} isOwner={isOwner}
                onCreated={() => { setAddOpen(false); load(); }} />
            <ImportStrategyModal open={importOpen} onOpenChange={setImportOpen}
                onImported={() => { setImportOpen(false); load(); }} />
        </>
    );
}

const CHIPS = [
    { id: "top_rated", label: "Top Rated", Icon: Star },
    { id: "top_internal", label: "Top Internal", Icon: Brain },
    { id: "healthiest", label: "Healthiest", Icon: HeartPulse },
    { id: "trending", label: "Trending", Icon: Flame },
];
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
function StrategyLibrary({ metrics, isOwner, onOpenInternal, onOpenCatalog, onImport, onBuild }) {
    const [lib, setLib] = useState(null);
    const [facets, setFacets] = useState({});
    const [query, setQuery] = useState("");
    const [chip, setChip] = useState(null);
    const [filters, setFilters] = useState({});   // {field: [values]}
    const [favOnly, setFavOnly] = useState(false);
    const [showFilter, setShowFilter] = useState(false);
    const [addMenu, setAddMenu] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);

    const activeCount = Object.values(filters).reduce((n, v) => n + v.length, 0) + (favOnly ? 1 : 0);

    const load = () => {
        const params = {};
        if (chip) params.chip = chip;
        if (query.trim()) params.q = query.trim();
        if (favOnly) params.favorite = true;
        Object.entries(filters).forEach(([k, v]) => { if (v.length) params[k] = v.join(","); });
        api.libraryList(params).then((d) => setLib(d.strategies)).catch(() => setLib([]));
    };
    useEffect(() => { api.libraryFacets().then(setFacets).catch(() => {}); }, []);
    useEffect(load, [chip, filters, favOnly, query]);

    const toggleFilter = (field, val) => setFilters((f) => {
        const cur = f[field] || [];
        return { ...f, [field]: cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val] };
    });
    const clearFilters = () => { setFilters({}); setFavOnly(false); };

    return (
        <div className="space-y-5" data-testid="strategy-center">
            {/* Search + Add live in the scroll-through top header, next to the title */}
            <HeaderActionPortal>
                <button data-testid="strategy-search-btn" onClick={() => setSearchOpen(true)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-full font-mono text-[10px] tracking-wide border border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-all">
                    <Search className="w-3.5 h-3.5" /> Search
                </button>
                <div className="relative">
                    <button data-testid="strategy-add-btn" aria-label="Add Strategy" title="Add Strategy" onClick={() => setAddMenu((v) => !v)}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-full font-mono text-[10px] tracking-wide border border-atlas-cyan/50 bg-atlas-cyan/10 text-atlas-cyan hover:bg-atlas-cyan/20 transition-all">
                        <Plus className={`w-3.5 h-3.5 transition-transform ${addMenu ? "rotate-45" : ""}`} /> Add
                    </button>
                    {addMenu && (
                        <div className="absolute right-0 mt-2 w-56 panel border-atlas-border rounded-xl p-1 z-50" data-testid="add-menu">
                            <button data-testid="add-menu-import" onClick={() => { setAddMenu(false); onImport(); }} className="w-full flex items-center gap-2 rounded-lg px-3 py-2.5 text-left hover:bg-atlas-panelHover">
                                <Upload className="w-4 h-4 text-atlas-cyan" /><span className="font-mono text-[12px] text-atlas-text">Import Strategy</span>
                            </button>
                            <button data-testid="add-menu-manual" onClick={() => { setAddMenu(false); onBuild(); }} className="w-full flex items-center gap-2 rounded-lg px-3 py-2.5 text-left hover:bg-atlas-panelHover">
                                <Boxes className="w-4 h-4 text-atlas-cyan" /><span className="font-mono text-[12px] text-atlas-text">Write Strategy</span>
                            </button>
                            <button data-testid="add-menu-ai" onClick={() => { setAddMenu(false); onBuild(); }} className="w-full flex items-center gap-2 rounded-lg px-3 py-2.5 text-left hover:bg-atlas-panelHover">
                                <Sparkles className="w-4 h-4 text-atlas-cyan" /><span className="font-mono text-[12px] text-atlas-text">Describe &amp; Build (AI)</span>
                            </button>
                        </div>
                    )}
                </div>
            </HeaderActionPortal>

            <div className="flex items-center gap-2 flex-wrap">
                {CHIPS.map(({ id, label, Icon }) => (
                    <button key={id} data-testid={`chip-${id}`} onClick={() => setChip(chip === id ? null : id)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full font-mono text-[10px] tracking-wide border transition-all ${
                            chip === id ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary"}`}>
                        <Icon className="w-3 h-3" /> {label}
                    </button>
                ))}
                <span className="w-px h-5 bg-atlas-border mx-1" />
                <button data-testid="filter-button" onClick={() => setShowFilter(true)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full font-mono text-[10px] tracking-wide border transition-all ${
                        activeCount ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>
                    <SlidersHorizontal className="w-3 h-3" /> Filter{activeCount ? ` · ${activeCount}` : ""}
                </button>
            </div>

            <StrategyLeaderboard onOpen={(r) => (r.internal ? onOpenInternal(r.key) : onOpenCatalog(r.key))} />

            {!lib ? (
                <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary flex items-center gap-2" data-testid="strategy-center-loading"><Loader2 className="w-4 h-4 animate-spin" /> LOADING LIBRARY</div>
            ) : lib.length === 0 ? (
                <div className="panel p-10 text-center" data-testid="library-empty">
                    <div className="font-mono text-sm text-atlas-textSecondary">No strategies match these filters.</div>
                    <button onClick={clearFilters} className="mt-3 font-mono text-[11px] text-atlas-cyan hover:underline">Clear filters</button>
                </div>
            ) : (
                <div className="grid grid-cols-2 gap-3 md:gap-5" data-testid="strategy-grid">
                    {lib.map((s) => (
                        <LibraryCard key={s.id} s={s} metric={(s.internal || s.wireable) ? metrics?.[s.engine_key] : null} isOwner={isOwner}
                            onOpen={() => (s.internal ? onOpenInternal(s.engine_key) : onOpenCatalog(s.id))}
                            onFav={() => api.libraryFavorite(s.id).then(load)} />
                    ))}
                    <button data-testid="add-strategy-card" onClick={onImport}
                        className="group rounded-2xl border-2 border-dashed border-atlas-border hover:border-atlas-cyan/60 bg-atlas-panel/30 min-h-[180px] flex flex-col items-center justify-center gap-2 transition-all hover:bg-atlas-panelHover">
                        <div className="w-11 h-11 rounded-xl grid place-items-center border border-atlas-border group-hover:border-atlas-cyan/50 group-hover:bg-atlas-cyan/10 transition-colors">
                            <Upload className="w-5 h-5 text-atlas-textTertiary group-hover:text-atlas-cyan" />
                        </div>
                        <span className="font-mono text-xs text-atlas-textSecondary group-hover:text-atlas-text">Import Strategy</span>
                        <span className="font-mono text-[9px] text-atlas-textTertiary">Pine · Freqtrade · Jesse · JSON</span>
                    </button>
                    <button data-testid="build-strategy-card" onClick={onBuild}
                        className="group rounded-2xl border-2 border-dashed border-atlas-border hover:border-violet-500/60 bg-atlas-panel/30 min-h-[180px] flex flex-col items-center justify-center gap-2 transition-all hover:bg-atlas-panelHover">
                        <div className="w-11 h-11 rounded-xl grid place-items-center border border-atlas-border group-hover:border-violet-500/50 group-hover:bg-violet-500/10 transition-colors">
                            <Sparkles className="w-5 h-5 text-atlas-textTertiary group-hover:text-violet-400" />
                        </div>
                        <span className="font-mono text-xs text-atlas-textSecondary group-hover:text-atlas-text">Build with AI</span>
                        <span className="font-mono text-[9px] text-atlas-textTertiary">Design a strategy conversationally</span>
                    </button>
                </div>
            )}

            {showFilter && (
                <FilterDrawer facets={facets} filters={filters} favOnly={favOnly} activeCount={activeCount}
                    onToggle={toggleFilter} onFav={() => setFavOnly((v) => !v)} onClear={clearFilters}
                    onClose={() => setShowFilter(false)} />
            )}
            {searchOpen && (
                <SearchScreen lib={lib} query={query} setQuery={setQuery} activeCount={activeCount}
                    onOpenFilters={() => { setSearchOpen(false); setShowFilter(true); }}
                    onOpen={(s) => { setSearchOpen(false); (s.internal ? onOpenInternal(s.engine_key) : onOpenCatalog(s.id)); }}
                    onClose={() => setSearchOpen(false)} />
            )}
        </div>
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

const LB_LABELS = {
    net_pnl: "Net P&L", roi: "ROI", win_rate: "Win Rate", ai_health_score: "AI Health Score",
    sharpe: "Sharpe Ratio", sortino: "Sortino Ratio", profit_factor: "Profit Factor",
    max_drawdown: "Max Drawdown", avg_trade: "Avg Trade", trades: "Total Trades", rating: "Rating",
};

export function StrategyLeaderboard({ onOpen }) {
    const [sort, setSort] = useState("ai_health_score");
    const [data, setData] = useState(null);
    const [showAll, setShowAll] = useState(false);
    useEffect(() => { api.analyticsLeaderboard(sort).then(setData).catch(() => {}); }, [sort]);
    const opts = data?.sort_options || Object.keys(LB_LABELS);
    const all = (data?.leaderboard || []).slice(0, 8);
    const rows = showAll ? all : all.slice(0, 2);
    const fmt = (k, v) => (k === "net_pnl" ? `$${(v || 0).toLocaleString()}` : ["roi", "win_rate", "max_drawdown"].includes(k) ? `${v}%` : v);
    return (
        <div className="panel p-4" data-testid="strategy-leaderboard">
            <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
                <div className="flex items-center gap-2"><BarChart3 className="w-4 h-4 text-atlas-cyan" /><span className="label-tag">STRATEGY LEADERBOARD</span></div>
                <Select value={sort} onValueChange={setSort}>
                    <SelectTrigger data-testid="leaderboard-sort-select"
                        className="w-auto bg-atlas-panel border-atlas-border rounded px-2.5 py-1.5 font-mono text-[11px] text-atlas-text focus:border-atlas-cyan h-auto gap-1.5">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-atlas-panel border-atlas-border text-atlas-text font-mono text-[11px]">
                        {opts.map((o) => <SelectItem key={o} value={o} className="font-mono text-[11px]">{`Sort: ${LB_LABELS[o] || o}`}</SelectItem>)}
                    </SelectContent>
                </Select>
            </div>
            <div className="space-y-1">
                {rows.map((r) => (
                    <button key={r.key} data-testid={`leaderboard-row-${r.key}`} onClick={() => onOpen && onOpen(r)}
                        className="w-full flex items-center gap-3 px-3 py-2 rounded-lg bg-atlas-panelHover/40 border border-atlas-border hover:border-atlas-cyan/40 transition-colors text-left">
                        <span className="font-mono text-[11px] text-atlas-textTertiary w-5">#{r.rank}</span>
                        <span className="font-heading text-sm text-atlas-text flex-1 truncate">{r.name}</span>
                        <span className={`font-mono text-[8px] font-bold uppercase px-1.5 py-0.5 rounded-full border ${GRADE_CLS[r.ai_grade] || GRADE_CLS.C}`}>{r.ai_grade}</span>
                        <span className="font-mono text-sm font-bold tabular-nums text-atlas-cyan w-24 text-right">{fmt(sort, r[sort])}</span>
                    </button>
                ))}
            </div>
            {all.length > 2 && (
                <button data-testid="strategy-leaderboard-show-more" onClick={() => setShowAll((v) => !v)}
                    className="mt-2 w-full rounded-lg border border-atlas-border py-2 font-mono text-[11px] text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors">
                    {showAll ? "Show less" : `Show more (${all.length - 2})`}
                </button>
            )}
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


function LibraryCard({ s, metric, isOwner, onOpen, onFav }) {
    const Icon = ICONS[s.engine_key] || CATEGORY_ICON[s.category] || Boxes;
    const r = s.historical_results || {};
    const wired = !!(s.internal || (s.wireable && s.engine_key));
    const roi = metric ? metric.roi : r.roi;
    const roiCls = roi > 0 ? "text-atlas-positive" : roi < 0 ? "text-atlas-negative" : "text-atlas-text";
    const status = wired ? (metric?.status || "PAPER") : "CATALOG";
    return (
        <div data-testid={`library-card-${s.id}`}
            className="group relative text-left rounded-2xl border border-atlas-border bg-atlas-panel/70 p-4 md:p-5 flex flex-col gap-3 transition-all hover:-translate-y-0.5 hover:bg-atlas-panelHover hover:shadow-[0_16px_50px_-20px_rgba(0,0,0,0.95)]">
            <button onClick={onOpen} className="absolute inset-0 z-0" aria-label={`Open ${s.name}`} data-testid={`library-open-${s.id}`} />
            <div className="flex items-start justify-between gap-2 relative z-10 pointer-events-none">
                <div className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5">
                    <Icon className="w-5 h-5 text-atlas-cyan" strokeWidth={2} />
                </div>
                <div className="flex items-center gap-1.5 pointer-events-auto">
                    <span className={`font-mono text-[8px] font-bold uppercase tracking-wider px-2 py-1 rounded-full border ${GRADE_CLS[s.ai_grade] || GRADE_CLS.C}`} data-testid={`card-grade-${s.id}`}>Grade {s.ai_grade}</span>
                    {isOwner && (
                        <button data-testid={`card-fav-${s.id}`} onClick={onFav} className="text-atlas-textTertiary hover:text-atlas-cyan">
                            <Heart className={`w-3.5 h-3.5 ${s.favorite ? "fill-atlas-cyan text-atlas-cyan" : ""}`} />
                        </button>
                    )}
                </div>
            </div>
            <div className="relative z-10 pointer-events-none">
                <div className="font-heading font-medium text-base md:text-lg text-atlas-text leading-tight truncate">{s.name}</div>
                <div className="flex items-center gap-2 mt-0.5">
                    <span className="font-mono text-[9px] text-atlas-textTertiary truncate">{s.style} · {s.source}</span>
                </div>
                <div className="flex items-center gap-1 mt-1">
                    {[1, 2, 3, 4, 5].map((n) => <Star key={n} className={`w-3 h-3 ${n <= s.rating ? "text-atlas-warning fill-atlas-warning" : "text-atlas-textTertiary"}`} />)}
                    <span className={`ml-auto font-mono text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full border ${STATUS[status] || "text-atlas-textTertiary border-atlas-border"}`}>{status}</span>
                </div>
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 font-mono text-[11px] relative z-10 pointer-events-none">
                <Kv label="ROI" value={`${roi > 0 ? "+" : ""}${roi}%`} cls={roiCls} />
                <Kv label="Health" value={s.ai_health_score} cls={s.ai_health_score >= 60 ? "text-atlas-positive" : s.ai_health_score >= 35 ? "text-atlas-warning" : "text-atlas-negative"} />
                <Kv label="Win Rate" value={`${r.win_rate}%`} />
                <Kv label="Sharpe" value={r.sharpe} />
            </div>
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
const TABS = ["Overview", "Parameters", "AI", "History"];

function StrategyDetail({ sKey, schema, metric, isOwner, onBack, onChanged }) {
    const [tab, setTab] = useState("Overview");
    const [status, setStatus] = useState(metric?.status || "PAPER");
    const [analyseOpen, setAnalyseOpen] = useState(false);
    const [analyseMode, setAnalyseMode] = useState("choice"); // choice | run
    const Icon = ICONS[sKey] || Boxes;
    const grade = schema?.ai_grade || metric?.grade;
    const stars = metric?.stars ?? Math.round((metric?.health ?? 0) / 20);

    const setState = async (patch) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try {
            const r = await api.strategySetState(sKey, patch);
            if (r.status) setStatus(r.status);
            toast.success("Strategy updated", { description: JSON.stringify(patch) });
            onChanged?.();
        } catch (e) { toast.error("Update failed", { description: String(e?.response?.data?.detail || e?.message) }); }
    };

    const openEdit = () => { setTab("Parameters"); window.scrollTo({ top: 0, behavior: "smooth" }); };
    const openAnalyse = () => { setAnalyseMode("choice"); setAnalyseOpen(true); };

    return (
        <div className="space-y-5" data-testid={`strategy-detail-${sKey}`}>
            {/* header */}
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
                            <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">v{schema?.version || "1.0.0"} · {metric?.trades ?? 0} trades · {metric?.config_count ?? 0} configs</div>
                        </div>
                    </div>
                    {/* Grade + love/rating pinned top-right next to the name */}
                    <div className="flex items-center gap-2 flex-wrap justify-end">
                        {grade && <span className={`font-mono text-[9px] font-bold uppercase px-2.5 py-1.5 rounded-lg border ${GRADE_CLS[grade] || GRADE_CLS.C}`} data-testid="detail-grade">Grade {grade}</span>}
                        <span className="flex items-center gap-0.5" data-testid="detail-rating">
                            {[1, 2, 3, 4, 5].map((n) => <Star key={n} className={`w-3.5 h-3.5 ${n <= stars ? "text-atlas-warning fill-atlas-warning" : "text-atlas-textTertiary"}`} />)}
                        </span>
                        <span className={`font-mono text-[9px] font-bold uppercase px-2.5 py-1.5 rounded-lg border ${STATUS[status]}`} data-testid="detail-status">{status}</span>
                    </div>
                </div>
                {/* headline metrics */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                    <Stat label="ROI" value={`${(metric?.roi ?? 0) > 0 ? "+" : ""}${metric?.roi ?? 0}%`} cls={(metric?.roi ?? 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative"} />
                    <Stat label="Win Rate" value={`${metric?.win_rate ?? 0}%`} />
                    <Stat label="Health" value={metric?.health ?? "—"} />
                    <Stat label="Confidence" value={`${metric?.confidence ?? 0}%`} />
                </div>
                {/* top action row: Edit + Analyse */}
                <div className="flex items-center gap-2 mt-4">
                    <button data-testid="detail-edit-strategy" onClick={openEdit}
                        className="flex items-center gap-2 rounded-lg border border-atlas-border px-4 py-2.5 font-mono text-[11px] font-bold tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-cyan/50 transition-colors">
                        <Pencil className="w-3.5 h-3.5" /> EDIT STRATEGY
                    </button>
                    <button data-testid="detail-analyse-strategy-top" onClick={openAnalyse}
                        className="flex items-center gap-2 rounded-lg border border-atlas-cyan/50 bg-atlas-cyan/10 px-4 py-2.5 font-mono text-[11px] font-bold tracking-widest text-atlas-cyan hover:bg-atlas-cyan/20 transition-colors">
                        <BarChart3 className="w-3.5 h-3.5" /> ANALYSE STRATEGY
                    </button>
                    <Select value={status} onValueChange={(v) => setState({ status: v })} disabled={!isOwner}>
                        <SelectTrigger data-testid="detail-status-select"
                            className="ml-auto w-auto bg-atlas-panel border-atlas-border rounded-lg px-2.5 py-2.5 font-mono text-[10px] text-atlas-text disabled:opacity-50 h-auto gap-1.5">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-atlas-panel border-atlas-border text-atlas-text font-mono text-[10px]">
                            {Object.keys(STATUS).map((st) => <SelectItem key={st} value={st} className="font-mono text-[10px]">{st}</SelectItem>)}
                        </SelectContent>
                    </Select>
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
                {tab === "AI" && <AIAnalystTerminal isOwner={isOwner} strategy={sKey} />}
                {tab === "History" && <History metric={metric} />}
            </div>

            {/* full-width Analyse this Strategy */}
            <button data-testid="detail-analyse-strategy-bottom" onClick={openAnalyse}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-atlas-cyan text-black font-mono text-sm font-bold tracking-wide py-3.5 hover:brightness-110 active:scale-[0.99] transition-all">
                <BarChart3 className="w-4 h-4" /> ANALYSE THIS STRATEGY
            </button>

            {/* analyse flow */}
            <LabModal open={analyseOpen} onOpenChange={setAnalyseOpen} icon={BarChart3} title={`Analyse · ${schema?.name || sKey}`}
                subtitle="Backtest & validate — asset · timeframe · exit" testid="analyse-modal">
                {analyseMode === "choice" ? (
                    <div className="space-y-3 p-1">
                        <button data-testid="analyse-current-params" onClick={() => setAnalyseMode("run")}
                            className="w-full text-left rounded-xl border border-atlas-cyan/40 bg-atlas-cyan/5 px-4 py-4 hover:bg-atlas-cyan/10 transition-colors">
                            <div className="font-heading text-sm text-atlas-text">Analyse with current parameters</div>
                            <div className="font-mono text-[11px] text-atlas-textTertiary mt-1">Use the strategy&apos;s saved defaults — pick asset, timeframe &amp; exit next.</div>
                        </button>
                        <button data-testid="analyse-edit-params" onClick={() => { setAnalyseOpen(false); openEdit(); }}
                            className="w-full text-left rounded-xl border border-atlas-border px-4 py-4 hover:bg-atlas-panelHover transition-colors">
                            <div className="font-heading text-sm text-atlas-text">Edit parameters &amp; analyse</div>
                            <div className="font-mono text-[11px] text-atlas-textTertiary mt-1">Tune entry/exit settings in the engine first, then analyse.</div>
                        </button>
                    </div>
                ) : (
                    <StrategyValidationPanel />
                )}
            </LabModal>
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
            <HealthCard metric={metric} />
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

    if (!s) return <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> LOADING</div>;
    const r = s.historical_results || {};
    const Icon = CATEGORY_ICON[s.category] || Boxes;

    return (
        <div className="space-y-5" data-testid="catalog-detail">
            <button data-testid="catalog-back" onClick={onBack} className="flex items-center gap-2 font-mono text-[11px] text-atlas-textSecondary hover:text-atlas-text">
                <ArrowLeft className="w-4 h-4" /> Back to Library
            </button>

            <div className="panel p-5">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Icon className="w-6 h-6 text-atlas-cyan" /></div>
                        <div>
                            <div className="font-heading text-xl text-atlas-text">{s.name}</div>
                            <div className="font-mono text-[10px] text-atlas-textTertiary">{s.style} · {s.category} · {s.source}</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className={`font-mono text-[9px] font-bold uppercase px-2.5 py-1 rounded-full border ${GRADE_CLS[s.ai_grade] || GRADE_CLS.C}`}>Grade {s.ai_grade}</span>
                        {s.imported && <span data-testid="imported-badge" className="font-mono text-[9px] font-bold uppercase px-2.5 py-1 rounded-full border border-atlas-cyan/40 bg-atlas-cyan/10 text-atlas-cyan flex items-center gap-1"><Upload className="w-3 h-3" /> Imported</span>}
                        <button data-testid="catalog-favorite" onClick={() => api.libraryFavorite(id).then(load)} className="text-atlas-textTertiary hover:text-atlas-cyan" title="Favorite">
                            <Heart className={`w-5 h-5 ${s.favorite ? "fill-atlas-cyan text-atlas-cyan" : ""}`} />
                        </button>
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
