import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowRight, BarChart3, Boxes, ChevronDown, ChevronRight, Sparkles, Plus, Search, TrendingUp, X, Zap, Loader2 } from "lucide-react";
import {
    Cell as RCell,
    Pie,
    PieChart,
    ResponsiveContainer,
    Tooltip as RTooltip,
} from "recharts";
import api from "@/lib/api";
import { toast } from "sonner";
import { useAppData } from "@/context/AppDataContext";
import { useAuth } from "@/context/AuthContext";
import CandleChart from "@/components/CandleChart";
import ManualExitButton from "@/components/ManualExitButton";
import WatchlistControl from "@/components/WatchlistControl";
import TradingWizard from "@/components/TradingWizard";
import ComingSoonPromo from "@/components/ComingSoonPromo";
import { Rocket } from "lucide-react";
import { Drawer, DrawerContent, DrawerTrigger } from "@/components/ui/drawer";

const SILVER = "#C0C5CE";
const GREEN = "#10B981";
const ROSE = "#F43F5E";
const MUTED = "#5C6370";

export default function Dashboard() {
    const { portfolio, snapshots, enabledSymbols, trades, summary, regime, refresh } = useAppData();
    const { isOwner } = useAuth();
    const [selected, setSelected] = useState(null);
    const [candles, setCandles] = useState([]);
    const [loadingChart, setLoadingChart] = useState(false);
    const [wizardOpen, setWizardOpen] = useState(false);
    const [weeklyOpen, setWeeklyOpen] = useState(false);

    useEffect(() => {
        const onWizard = () => setWizardOpen(true);
        window.addEventListener("ananta:wizard", onWizard);
        return () => window.removeEventListener("ananta:wizard", onWizard);
    }, []);

    useEffect(() => {
        if (!selected && enabledSymbols.length) setSelected(enabledSymbols[0]);
    }, [selected, enabledSymbols]);

    useEffect(() => {
        if (!selected) return;
        setLoadingChart(true);
        api.candles(selected, "4h", 120)
            .then((d) => setCandles(d.candles || []))
            .catch(() => setCandles([]))
            .finally(() => setLoadingChart(false));
    }, [selected]);

    return (
        <div className="space-y-5" data-testid="cockpit-page">
            {/* First-login welcome sheet (Coming Soon to Ananta) — Cockpit only */}
            <ComingSoonPromo variant="sheet" isOwner={isOwner} />
            {/* Action hub — dual control row directly beneath Account Value */}
            <div className="grid grid-cols-2 gap-3">
                <button data-testid="cockpit-start-trading" onClick={() => (isOwner ? setWizardOpen(true) : toast.error("Owner login required"))}
                    className="flex items-center justify-center gap-2 rounded-xl bg-atlas-cyan text-black font-mono text-sm font-bold tracking-wide py-3.5 hover:brightness-110 active:scale-[0.99] transition-all">
                    <Rocket className="w-4 h-4" /> START TRADING
                </button>
                <button data-testid="cockpit-weekly-review" onClick={() => setWeeklyOpen(true)}
                    className="flex items-center justify-center gap-2 rounded-xl border border-atlas-cyan/40 text-atlas-cyan font-mono text-sm font-bold tracking-wide py-3.5 hover:bg-atlas-cyan/10 active:scale-[0.99] transition-all">
                    <Sparkles className="w-4 h-4" /> WEEKLY AI REVIEW
                </button>
            </div>
            <StrategyHealthToday />
            {/* Watchlist (80%) + Charts (20%) on one row */}
            <div className="flex gap-3 items-stretch">
                <div className="flex-[4] min-w-0">
                    <WatchlistRibbon snapshots={snapshots} symbols={enabledSymbols} selected={selected} onSelect={setSelected} onChanged={refresh} />
                </div>
                <div className="flex-1 min-w-0">
                    <ChartDrawer selected={selected} candles={candles} loading={loadingChart} />
                </div>
            </div>
            <TradeLifecyclePanel portfolio={portfolio} regime={regime} />
            <AnalyticsGroup summary={summary} trades={trades} />
            <ConsolidatedPositions portfolio={portfolio} onDone={refresh} />
            <TradingWizard open={wizardOpen} onClose={() => setWizardOpen(false)} onLaunched={refresh} />
            <WeeklyReviewModal open={weeklyOpen} onClose={() => setWeeklyOpen(false)} />
        </div>
    );
}

function WeeklyReviewModal({ open, onClose }) {
    const [loading, setLoading] = useState(false);
    const [review, setReview] = useState(null);
    useEffect(() => {
        if (!open) return;
        setLoading(true); setReview(null);
        api.coachReview().then(setReview).catch(() => setReview({ error: true })).finally(() => setLoading(false));
    }, [open]);
    if (!open) return null;
    const rec = review?.recommendation;
    return (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" data-testid="weekly-review-modal" onClick={onClose}>
            <div className="panel border-atlas-border rounded-2xl w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2 font-heading text-lg text-atlas-text"><Sparkles className="w-5 h-5 text-atlas-cyan" /> Weekly AI Review</div>
                    <button data-testid="weekly-review-close" onClick={onClose} className="text-atlas-textSecondary hover:text-white"><X className="w-5 h-5" /></button>
                </div>
                {loading ? (
                    <div className="py-10 grid place-items-center"><Loader2 className="w-6 h-6 text-atlas-cyan animate-spin" /></div>
                ) : review?.error ? (
                    <p className="font-mono text-[12px] text-atlas-textSecondary">Coach review is unavailable right now.</p>
                ) : (
                    <div className="space-y-3 max-h-[55vh] overflow-y-auto atlas-scroll">
                        <p className="font-mono text-[13px] text-atlas-text leading-relaxed whitespace-pre-wrap">{review?.summary || review?.headline || "No review available yet — trade more to unlock weekly coaching."}</p>
                        {rec?.text && <p className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed whitespace-pre-wrap border-t border-atlas-border pt-3">{rec.text}</p>}
                    </div>
                )}
            </div>
        </div>
    );
}

/* ---------------- AI Coach headline banner (credit-free) ---------------- */
const STRAT_ICON = { hunter: TrendingUp, squeeze: Zap, continuation: Activity };
const REC_TONE = {
    positive: "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10",
    warning: "text-atlas-warning border-atlas-warning/40 bg-atlas-warning/10",
    negative: "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/10",
};

/* Strategy Health Today — top recommended strategies from the daily health sweep. */
function StrategyHealthToday() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let alive = true;
        api.labHealth()
            .then((d) => { if (alive) setData(d?.ready ? d : null); })
            .catch(() => { if (alive) setData(null); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, []);

    const viewDashboard = () => {
        localStorage.setItem("ananta_research_sub", "health");
        window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "research" } }));
    };

    const recommended = (data?.strategies || [])
        .filter((s) => s.recommendation?.tone === "positive")
        .sort((a, b) => (b.headline?.net_pnl ?? 0) - (a.headline?.net_pnl ?? 0))
        .slice(0, 2);

    return (
        <div className="panel border-atlas-border rounded-2xl p-4 space-y-3" data-testid="strategy-health-today">
            <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                    <div className="font-heading text-lg text-atlas-text leading-none">Strategy Health</div>
                    {recommended.length > 0 && (
                        <span data-testid="health-recommended-badge"
                            className="font-mono text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-atlas-positive/15 text-atlas-positive border border-atlas-positive/30 leading-none">
                            {recommended.length}
                        </span>
                    )}
                </div>
                <button data-testid="cockpit-view-health-dashboard" onClick={viewDashboard}
                    className="flex items-center gap-1.5 rounded-full border border-atlas-cyan/40 text-atlas-cyan font-mono text-[10px] font-bold tracking-wide px-3 py-1.5 hover:bg-atlas-cyan/10 active:scale-95 transition-all">
                    View Health <ArrowRight className="w-3 h-3" />
                </button>
            </div>

            {loading ? (
                <div className="py-6 grid place-items-center text-atlas-textTertiary" data-testid="health-today-loading">
                    <Loader2 className="w-4 h-4 animate-spin" />
                </div>
            ) : recommended.length === 0 ? (
                <div className="py-2 font-mono text-[11px] text-atlas-textTertiary" data-testid="health-today-empty">
                    No strategies currently recommended for paper trading.
                </div>
            ) : (
                <>
                    <div className="font-mono text-[11px] text-atlas-textSecondary" data-testid="health-today-count">
                        {recommended.length} {recommended.length === 1 ? "strategy" : "strategies"} recommended for paper trading.
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        {recommended.map((s) => <HealthTodayCard key={s.strategy} card={s} />)}
                    </div>
                </>
            )}
        </div>
    );
}

function HealthTodayCard({ card }) {
    const Icon = STRAT_ICON[card.strategy] || Boxes;
    const rec = card.recommendation || {};
    const pnl = Number(card.headline?.net_pnl ?? 0);
    const pnlCls = pnl >= 0 ? "text-atlas-positive" : "text-atlas-negative";
    return (
        <div className="rounded-xl border border-atlas-border bg-atlas-bg/40 p-3.5 space-y-2.5" data-testid={`health-today-card-${card.strategy}`}>
            <div className="flex items-center gap-2.5">
                <span className="w-8 h-8 rounded-lg grid place-items-center border border-atlas-border bg-atlas-cyan/5 shrink-0"><Icon className="w-4 h-4 text-atlas-cyan" /></span>
                <div className="font-heading text-base text-atlas-text truncate">{card.name}</div>
            </div>
            <span className={`flex w-full items-center justify-center text-center font-mono text-[8px] font-bold tracking-wide uppercase leading-tight px-2 py-1 rounded-full border ${REC_TONE[rec.tone] || REC_TONE.warning}`} data-testid={`health-today-badge-${card.strategy}`}>
                {rec.badge || "Recommended"}
            </span>
            <div className="font-mono text-sm">
                <span className={`font-bold tabular-nums ${pnlCls}`} data-testid={`health-today-pnl-${card.strategy}`}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</span>
                <span className="text-atlas-textTertiary text-[11px]"> P&amp;L</span>
            </div>
        </div>
    );
}

/* Compact market-regime pill shown next to a section title (replaces the full Regime row). */
function RegimeTag({ regime }) {
    const label = regime === "BULLISH" ? "Bull" : regime === "BEARISH" ? "Bear" : "Neutral";
    const cls = regime === "BULLISH" ? "text-atlas-positive" : regime === "BEARISH" ? "text-atlas-negative" : "text-atlas-textSecondary";
    return (
        <span data-testid="regime-tag" className="font-mono text-[10px] text-atlas-textTertiary">
            (Market · <span className={`font-bold ${cls}`} data-testid="regime-value">{label}</span>)
        </span>
    );
}

/* ---------------- Watchlist Ribbon — compact single-line selector ---------------- */
function WatchlistRibbon({ snapshots, symbols, selected, onSelect, onChanged }) {
    const priceMap = useMemo(() => Object.fromEntries(snapshots.map((s) => [s.symbol, s])), [snapshots]);
    const sel = selected ? priceMap[selected] : null;
    const chg = sel?.change_24h_pct ?? null;
    const [addOpen, setAddOpen] = useState(false);
    const fmt = (p) => (p == null ? "—" : `$${p.toLocaleString(undefined, { minimumFractionDigits: p < 10 ? 4 : 2, maximumFractionDigits: p < 10 ? 4 : 2 })}`);
    return (
        <div className="panel px-4 py-3 flex items-center justify-between gap-3 flex-wrap" data-testid="watchlist-ribbon">
            <div className="flex items-center gap-3 min-w-0 flex-wrap">
                <span className="label-tag shrink-0">WATCHLIST</span>
                <select
                    data-testid="watchlist-select"
                    value={selected || ""}
                    onChange={(e) => onSelect(e.target.value)}
                    className="bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-sm font-bold text-atlas-text focus:border-atlas-cyan outline-none"
                >
                    {symbols.map((sym) => {
                        const s = priceMap[sym];
                        const base = sym.split("/")[0];
                        return <option key={sym} value={sym}>{base}{s ? ` · ${fmt(s.price)}` : ""}</option>;
                    })}
                </select>
                <button data-testid="watchlist-add-asset" onClick={() => setAddOpen(true)} title="Add a crypto to track"
                    className="w-8 h-8 grid place-items-center rounded-lg border border-atlas-border text-atlas-cyan hover:bg-atlas-cyan/10 hover:border-atlas-cyan/50 transition-colors shrink-0">
                    <Plus className="w-4 h-4" strokeWidth={2.5} />
                </button>
                {sel && chg != null && (
                    <span data-testid="watchlist-change" className={`font-mono text-xs font-bold shrink-0 ${chg > 0 ? "text-atlas-positive" : chg < 0 ? "text-atlas-negative" : "text-atlas-textTertiary"}`}>
                        {chg > 0 ? "+" : ""}{chg.toFixed(2)}%
                    </span>
                )}
            </div>
            <WatchlistControl />
            {addOpen && <AddAssetModal onClose={() => setAddOpen(false)} onAdded={(sym) => { setAddOpen(false); onSelect(sym); onChanged && onChanged(); }} />}
        </div>
    );
}

function AddAssetModal({ onClose, onAdded }) {
    const [q, setQ] = useState("");
    const [results, setResults] = useState([]);
    const [busy, setBusy] = useState("");
    useEffect(() => {
        const t = setTimeout(() => { api.watchlistSearch(q).then((d) => setResults(d.results || [])).catch(() => setResults([])); }, 180);
        return () => clearTimeout(t);
    }, [q]);
    const add = async (sym) => {
        setBusy(sym);
        try { await api.watchlistAdd(sym); toast.success("Added to Active Watchlist", { description: sym }); onAdded(sym); }
        catch (e) { toast.error("Add failed", { description: String(e?.response?.data?.detail || e?.message) }); setBusy(""); }
    };
    return (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" data-testid="add-asset-modal" onClick={onClose}>
            <div className="panel w-full max-w-md max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
                <div className="px-4 py-3 border-b border-atlas-border flex items-center justify-between">
                    <div className="label-tag">ADD TO ACTIVE WATCHLIST</div>
                    <button data-testid="add-asset-close" onClick={onClose} className="text-atlas-textSecondary hover:text-white"><X className="w-4 h-4" /></button>
                </div>
                <div className="px-4 py-3 border-b border-atlas-border flex items-center gap-2">
                    <Search className="w-3.5 h-3.5 text-atlas-textSecondary" />
                    <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search any crypto — BTC, DOGE, SUI…"
                        data-testid="add-asset-search" className="flex-1 bg-transparent outline-none text-white text-sm font-mono placeholder:text-atlas-textTertiary" />
                </div>
                <div className="overflow-y-auto">
                    {results.length === 0 && <div className="p-4 font-mono text-xs text-atlas-textSecondary">No matches.</div>}
                    {results.map((r) => (
                        <button key={r.symbol} data-testid={`add-asset-option-${r.symbol.replace("/", "-")}`} onClick={() => add(r.symbol)} disabled={!!busy}
                            className="w-full text-left px-4 py-3 border-b border-atlas-border last:border-b-0 panel-hover transition-colors font-mono text-sm text-white flex items-center justify-between">
                            <span>{r.symbol} <span className="text-atlas-textTertiary">· {r.name}</span></span>
                            {busy === r.symbol ? <Loader2 className="w-3.5 h-3.5 animate-spin text-atlas-cyan" /> : <Plus className="w-3.5 h-3.5 text-atlas-cyan" />}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ---------------- Chart Drawer ---------------- */
function ChartDrawer({ selected, candles, loading }) {
    return (
        <Drawer>
            <DrawerTrigger asChild>
                <button data-testid="open-chart-button"
                    className="w-full h-full panel flex flex-col items-center justify-center gap-1.5 py-4 hover:bg-atlas-panelHover transition-colors group">
                    <BarChart3 className="w-5 h-5 text-atlas-cyan" strokeWidth={2} />
                    <span className="font-mono text-[11px] font-bold tracking-widest text-atlas-text">CHARTS</span>
                    <span className="font-mono text-[9px] text-atlas-textTertiary border border-atlas-border px-1.5 py-0.5 rounded">{selected ? selected.split("/")[0] : "—"} · 4H</span>
                </button>
            </DrawerTrigger>
            <DrawerContent className="bg-atlas-panel border-atlas-border max-h-[88vh]" data-testid="chart-drawer">
                <div className="px-6 pt-2 pb-3 flex items-center justify-between">
                    <div>
                        <div className="label-tag">4-HOUR CANDLES</div>
                        <div className="font-mono font-bold text-lg text-atlas-text mt-1" data-testid="chart-symbol">{selected || "—"}</div>
                    </div>
                    <span className="font-mono text-[10px] text-atlas-textTertiary border border-atlas-border px-2 py-1 rounded">4H</span>
                </div>
                <div className="p-4 pb-8">
                    {loading && <div className="h-[60vh] flex items-center justify-center text-atlas-textSecondary font-mono text-xs"><span className="blink-cursor">LOADING CHART</span></div>}
                    {!loading && candles.length === 0 && <div className="h-[60vh] flex items-center justify-center text-atlas-textSecondary font-mono text-xs">NO CANDLES AVAILABLE</div>}
                    {!loading && candles.length > 0 && <CandleChart candles={candles} height={Math.round(window.innerHeight * 0.6)} />}
                </div>
            </DrawerContent>
        </Drawer>
    );
}

/* ---------------- Trade Life Cycle — one live progress line per open trade ---------------- */
const LC_STEPS = ["Entered", "In Profit", "Trail Armed", "Exit Watch"];

function LifecycleRow({ p }) {
    const base = p.symbol.split("/")[0];
    const avg = p.avg_cost || 0;
    const last = p.last_price || avg;
    const peak = p.peak_price || Math.max(last, avg);
    const stop = p.structural_stop || avg * 0.95;
    const pnl = p.unrealized_pnl || 0;
    const gainPct = avg > 0 ? ((last - avg) / avg) * 100 : 0;
    const peakGainPct = avg > 0 ? ((peak - avg) / avg) * 100 : 0;
    const pullbackPct = peak > 0 ? ((peak - last) / peak) * 100 : 0;
    const distStopPct = last > 0 ? ((last - stop) / last) * 100 : 0;

    let active = 0;
    if (gainPct > 0) active = 1;
    if (peakGainPct >= 1.5) active = 2;
    if (pullbackPct >= 1 || (distStopPct <= 1 && distStopPct >= -50)) active = 3;

    // marker position of current price within [stop, peak]
    const lo = Math.min(stop, avg, last), hi = Math.max(peak, last);
    const frac = hi > lo ? Math.min(1, Math.max(0, (last - lo) / (hi - lo))) : 0.5;
    const entryFrac = hi > lo ? Math.min(1, Math.max(0, (avg - lo) / (hi - lo))) : 0.5;
    const pnlCls = pnl > 0 ? "text-atlas-positive" : pnl < 0 ? "text-atlas-negative" : "text-atlas-textSecondary";

    return (
        <div data-testid={`lifecycle-row-${base}`}>
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-sm text-atlas-text">{base}</span>
                    {p.breakout_mode && <span className="text-[9px] text-atlas-cyan font-bold">BO</span>}
                </div>
                <span className={`font-mono text-sm font-bold tabular-nums ${pnlCls}`}>
                    {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)} <span className="text-[10px] font-normal opacity-80">({gainPct >= 0 ? "+" : ""}{gainPct.toFixed(2)}%)</span>
                </span>
            </div>
            {/* stepper */}
            <div className="flex items-center">
                {LC_STEPS.map((s, i) => (
                    <div key={s} className="flex items-center flex-1 last:flex-none">
                        <div className="flex flex-col items-center gap-1.5">
                            <span className={`w-2.5 h-2.5 rounded-full ${i < active ? "bg-atlas-positive" : i === active ? "bg-atlas-cyan glow-cyan" : "bg-atlas-border"}`} />
                            <span className={`font-mono text-[9px] tracking-wide whitespace-nowrap ${i <= active ? "text-atlas-text" : "text-atlas-textTertiary"}`}>{s}</span>
                        </div>
                        {i < LC_STEPS.length - 1 && <div className={`h-px flex-1 mx-2 ${i < active ? "bg-atlas-positive" : "bg-atlas-border"}`} />}
                    </div>
                ))}
            </div>
            {/* price range: stop --- entry --- current --- peak */}
            <div className="relative mt-3 h-1.5 rounded-full bg-atlas-bg border border-atlas-border">
                <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-atlas-negative/40 to-atlas-positive/60" style={{ width: `${frac * 100}%` }} />
                <span className="absolute -top-0.5 w-2 h-2 rounded-full bg-atlas-textTertiary" style={{ left: `calc(${entryFrac * 100}% - 4px)` }} title={`Entry ${avg}`} />
                <span className="absolute -top-1 w-3.5 h-3.5 rounded-full bg-atlas-cyan border-2 border-atlas-bg" style={{ left: `calc(${frac * 100}% - 7px)` }} title={`Now ${last}`} />
            </div>
            <div className="flex items-center justify-between mt-1.5 font-mono text-[9px] text-atlas-textTertiary tabular-nums">
                <span>STOP ${stop.toFixed(stop < 10 ? 4 : 2)}</span>
                <span>PEAK +{peakGainPct.toFixed(1)}%{pullbackPct > 0.05 ? ` · −${pullbackPct.toFixed(1)}% off` : ""}</span>
            </div>
        </div>
    );
}

function TradeLifecyclePanel({ portfolio, regime }) {
    const open = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    const [showAll, setShowAll] = useState(false);
    const visible = showAll ? open : open.slice(0, 1);
    return (
        <div className="panel p-6" data-testid="trade-lifecycle">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className="label-tag">TRADE LIFE CYCLE</div>
                    <RegimeTag regime={regime} />
                </div>
                <span className="font-mono text-[10px] text-atlas-textTertiary">{open.length} live</span>
            </div>
            {open.length === 0 ? (
                <div className="py-8 text-center font-mono text-xs text-atlas-textSecondary" data-testid="lifecycle-empty">
                    No live trades. The Hunter is evaluating support zones.
                </div>
            ) : (
                <>
                    <div className="space-y-3">
                        {visible.map((p, idx) => (
                            <div key={p.symbol} className={idx === 0 ? "" : "border-t border-atlas-border pt-3"}>
                                <LifecycleRow p={p} />
                            </div>
                        ))}
                    </div>
                    {open.length > 1 && (
                        <button data-testid="lifecycle-show-more" onClick={() => setShowAll((v) => !v)}
                            className="mt-3 w-full flex items-center justify-center gap-1.5 pt-3 border-t border-atlas-border font-mono text-[11px] text-atlas-textTertiary hover:text-atlas-cyan transition-colors">
                            {showAll ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                            {showAll ? "Show less" : `Show ${open.length - 1} more trade${open.length - 1 > 1 ? "s" : ""}`}
                        </button>
                    )}
                </>
            )}
        </div>
    );
}

/* ---------------- Analytics group — side-by-side slider (Leaderboard | Counterfactual) ---------------- */
function AnalyticsGroup({ summary, trades }) {
    const stop = (e) => e.stopPropagation();
    return (
        <div data-testid="analytics-group" className="space-y-2">
            <div className="flex items-center justify-between">
                <div className="label-tag">ANALYTICS</div>
                <span className="font-mono text-[9px] text-atlas-textTertiary md:hidden">← swipe →</span>
            </div>
            <div onTouchStart={stop} onTouchEnd={stop}>
                <div className="flex gap-3 overflow-x-auto atlas-scroll snap-x snap-mandatory pb-1" data-testid="analytics-slider">
                    <div className="snap-center shrink-0 w-full md:w-[calc(50%-6px)]"><LeaderboardAnalytics trades={trades} /></div>
                    <div className="snap-center shrink-0 w-full md:w-[calc(50%-6px)]"><CounterfactualPanel summary={summary} /></div>
                </div>
            </div>
        </div>
    );
}

/* ---------------- Counterfactual — correct rejections vs missed opportunities ---------------- */
function CounterfactualPanel({ summary }) {
    const buckets = summary?.confidence_buckets || [];
    const correct = buckets.reduce((a, b) => a + (b.correct_rejection || 0), 0);
    const missed = buckets.reduce((a, b) => a + (b.missed_opportunity || 0), 0);
    return (
        <section className="panel p-6 h-full" data-testid="counterfactual-panel">
            <div className="font-heading font-medium text-lg text-atlas-text">Counterfactual Engine</div>
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-0.5 mb-4">Correct rejections vs missed opportunities</div>
            {correct + missed === 0 ? <EmptyChart text="Awaiting counterfactual resolution (24h/72h/7d)..." /> : (
                <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                        <Pie data={[{ name: "Correct Rejections", value: correct }, { name: "Missed Opportunities", value: missed }]}
                            dataKey="value" nameKey="name" innerRadius={62} outerRadius={95} paddingAngle={2} stroke="none">
                            <RCell fill={GREEN} />
                            <RCell fill={ROSE} />
                        </Pie>
                        <RTooltip contentStyle={tooltipStyle} />
                    </PieChart>
                </ResponsiveContainer>
            )}
            <Legend items={[["Correct Rejections", GREEN, correct], ["Missed Opportunities", ROSE, missed]]} />
        </section>
    );
}

function EmptyChart({ text }) {
    return <div className="h-[200px] flex items-center justify-center text-atlas-textSecondary font-mono text-xs text-center px-6">{text}</div>;
}
function Legend({ items }) {
    return (
        <div className="flex flex-wrap gap-6 mt-4 justify-center font-mono text-[11px]">
            {items.map(([label, color, val]) => (
                <span key={label} className="flex items-center gap-2 text-atlas-textSecondary">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
                    {label} <span className="text-atlas-text font-bold tabular-nums">{val}</span>
                </span>
            ))}
        </div>
    );
}
const tooltipStyle = { background: "#121418", border: "1px solid #2A2D35", borderRadius: 6, fontFamily: "JetBrains Mono", fontSize: 11, color: "#E2E4E9" };

/* ---------------- Leaderboard & Analytics: dynamic property pie ---------------- */
const PIE_PALETTE = [SILVER, GREEN, ROSE, "#38BDF8", "#F59E0B", "#14B8A6", "#EAB308", MUTED];
const LB_PROPERTIES = [
    { v: "strategy", label: "Strategy / Model" },
    { v: "asset", label: "Crypto Asset" },
    { v: "exit", label: "Exit Module (A–F)" },
    { v: "winloss", label: "Win / Loss" },
    { v: "drawdown", label: "Drawdown by Asset" },
];

function LeaderboardAnalytics({ trades }) {
    const [property, setProperty] = useState("strategy");
    const [showAllLeaders, setShowAllLeaders] = useState(false);

    const { pieData, leaders, total } = useMemo(() => {
        const sells = (trades || []).filter((t) => t.side === "SELL");
        const map = {};
        const add = (key, pnl, win) => {
            const g = map[key] || (map[key] = { key, count: 0, net: 0, wins: 0 });
            g.count += 1; g.net += pnl; if (win) g.wins += 1;
        };
        sells.forEach((t) => {
            const pnl = t.pnl || 0; const win = pnl > 0; const base = (t.symbol || "—").split("/")[0];
            if (property === "strategy") add((t.strategy || "unknown").toUpperCase(), pnl, win);
            else if (property === "asset") add(base, pnl, win);
            else if (property === "exit") add(t.exit_module ? `Module ${t.exit_module}` : (t.exit_reason || "—"), pnl, win);
            else if (property === "winloss") add(win ? "Wins" : pnl < 0 ? "Losses" : "Breakeven", pnl, win);
            else if (property === "drawdown") { if (pnl < 0) add(base, pnl, false); }
        });
        const groups = Object.values(map);
        const pieData = groups.map((g) => ({ name: g.key, value: property === "drawdown" ? Math.abs(g.net) : g.count })).filter((d) => d.value > 0);
        const leaders = [...groups].sort((a, b) => property === "drawdown" ? a.net - b.net : b.net - a.net).slice(0, 6);
        const total = pieData.reduce((a, d) => a + d.value, 0);
        return { pieData, leaders, total };
    }, [trades, property]);

    return (
        <section className="panel p-6 h-full" data-testid="leaderboard-analytics">
            <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
                <div>
                    <div className="font-heading font-medium text-lg text-atlas-text">Leaderboard &amp; Analytics</div>
                    <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-0.5">
                        Closed-trade breakdown · switch the lens to slice the data live
                    </div>
                </div>
                <select data-testid="leaderboard-property-select" value={property} onChange={(e) => setProperty(e.target.value)}
                    className="bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-xs text-atlas-text">
                    {LB_PROPERTIES.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
                </select>
            </div>

            {total === 0 ? (
                <EmptyChart text="No closed trades yet for this breakdown." />
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
                    <div data-testid="leaderboard-pie">
                        <ResponsiveContainer width="100%" height={260}>
                            <PieChart>
                                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={62} outerRadius={95} paddingAngle={2} stroke="none">
                                    {pieData.map((d, i) => <RCell key={d.name} fill={PIE_PALETTE[i % PIE_PALETTE.length]} />)}
                                </Pie>
                                <RTooltip contentStyle={tooltipStyle} />
                            </PieChart>
                        </ResponsiveContainer>
                        <Legend items={pieData.slice(0, 6).map((d, i) => [d.name, PIE_PALETTE[i % PIE_PALETTE.length], d.value])} />
                    </div>
                    <div data-testid="leaderboard-table">
                        <div className="label-tag mb-3">RANKED BY NET P&amp;L</div>
                        <div className="space-y-1.5">
                            {(showAllLeaders ? leaders : leaders.slice(0, 2)).map((g, i) => (
                                <div key={g.key} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-atlas-panelHover/40 border border-atlas-border" data-testid={`leaderboard-row-${i}`}>
                                    <div className="flex items-center gap-3 min-w-0">
                                        <span className="font-mono text-[11px] text-atlas-textTertiary w-4">{i + 1}</span>
                                        <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: PIE_PALETTE[i % PIE_PALETTE.length] }} />
                                        <span className="font-mono text-xs text-atlas-text truncate">{g.key}</span>
                                    </div>
                                    <div className="flex items-center gap-4 font-mono text-[11px] tabular-nums shrink-0">
                                        <span className="text-atlas-textTertiary">{g.count}t</span>
                                        <span className="text-atlas-textSecondary">{Math.round((g.wins / g.count) * 100)}%</span>
                                        <span className={`font-bold w-20 text-right ${g.net > 0 ? "text-atlas-positive" : g.net < 0 ? "text-atlas-negative" : "text-atlas-textSecondary"}`}>
                                            {g.net >= 0 ? "+" : ""}${g.net.toFixed(2)}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                        {leaders.length > 2 && (
                            <button data-testid="leaderboard-show-more" onClick={() => setShowAllLeaders((v) => !v)}
                                className="mt-2 w-full rounded-lg border border-atlas-border py-2 font-mono text-[11px] text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors">
                                {showAllLeaders ? "Show less" : `Show more (${leaders.length - 2})`}
                            </button>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
}

/* ---------------- Consolidated positions (bottom) ---------------- */
function ConsolidatedPositions({ portfolio, onDone }) {
    const positions = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    const [showAll, setShowAll] = useState(false);
    const visible = showAll ? positions : positions.slice(0, 1);

    return (
        <div className="panel overflow-hidden" data-testid="consolidated-positions">
            <div className="px-6 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between">
                <div className="label-tag">POSITION TRACKER</div>
                <span className="font-mono text-[10px] text-atlas-textTertiary">{positions.length} open</span>
            </div>

            {positions.length === 0 ? (
                <div className="p-8 text-center font-mono text-xs text-atlas-textSecondary" data-testid="tracker-zero-state">
                    No open positions. The Hunter is evaluating support zones.
                </div>
            ) : (
                <>
                    <div className="divide-y divide-atlas-border">
                        {visible.map((p) => {
                            const base = p.symbol.split("/")[0];
                            const pnl = p.unrealized_pnl || 0;
                            const pnlPct = p.avg_cost > 0 ? ((p.last_price - p.avg_cost) / p.avg_cost) * 100 : 0;
                            const pnlCls = pnl > 0 ? "text-atlas-positive" : pnl < 0 ? "text-atlas-negative" : "text-atlas-textSecondary";
                            return (
                                <div key={p.symbol} className="flex items-center justify-between gap-4 px-6 py-3.5" data-testid={`tracker-row-${base}`}>
                                    <div className="flex items-center gap-4 min-w-0">
                                        <span className="font-mono font-bold text-sm text-atlas-text w-14">{base}</span>
                                        <span className="font-mono text-xs tabular-nums text-atlas-textSecondary">${(p.market_value || 0).toFixed(2)}</span>
                                        <span className="font-mono text-[11px] tabular-nums text-atlas-textTertiary hidden sm:inline">@ ${(p.avg_cost || 0).toFixed(p.avg_cost < 10 ? 4 : 2)}</span>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <span className={`font-mono text-sm font-bold tabular-nums text-right ${pnlCls}`}>
                                            {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)} <span className="text-[10px] font-normal opacity-80">({pnl >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)</span>
                                        </span>
                                        <ManualExitButton symbol={p.symbol} onDone={onDone} compact />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    {positions.length > 1 && (
                        <button data-testid="tracker-show-more" onClick={() => setShowAll((v) => !v)}
                            className="w-full flex items-center justify-center gap-1.5 px-6 py-2.5 border-t border-atlas-border font-mono text-[11px] text-atlas-textTertiary hover:text-atlas-cyan hover:bg-atlas-panelHover transition-colors">
                            {showAll ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                            {showAll ? "Show less" : `Show ${positions.length - 1} more position${positions.length - 1 > 1 ? "s" : ""}`}
                        </button>
                    )}
                </>
            )}
        </div>
    );
}
