import { useEffect, useMemo, useState } from "react";
import { BarChart3, Brain, ChevronDown, ChevronRight, RefreshCw, Trophy, Scale } from "lucide-react";
import {
    Bar,
    BarChart,
    Cell as RCell,
    Pie,
    PieChart,
    ResponsiveContainer,
    Tooltip as RTooltip,
    XAxis,
    YAxis,
} from "recharts";
import api from "@/lib/api";
import { useAppData } from "@/context/AppDataContext";
import CandleChart from "@/components/CandleChart";
import ManualExitButton from "@/components/ManualExitButton";
import WatchlistControl from "@/components/WatchlistControl";
import ReasoningTimeline from "@/components/ReasoningTimeline";
import { Drawer, DrawerContent, DrawerTrigger } from "@/components/ui/drawer";

const SILVER = "#C0C5CE";
const GREEN = "#10B981";
const ROSE = "#F43F5E";
const MUTED = "#5C6370";

export default function Dashboard() {
    const { portfolio, snapshots, enabledSymbols, trades, brain, summary, regime, reasoning, refresh } = useAppData();
    const [selected, setSelected] = useState(null);
    const [candles, setCandles] = useState([]);
    const [loadingChart, setLoadingChart] = useState(false);

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
        <div className="space-y-6" data-testid="cockpit-page">
            <BotBrainStrip brain={brain} regime={regime} scanned={enabledSymbols.length} onRefresh={refresh} />
            <WatchlistRibbon snapshots={snapshots} symbols={enabledSymbols} selected={selected} onSelect={setSelected} />
            <ChartDrawer selected={selected} candles={candles} loading={loadingChart} />
            <TradeLifecyclePanel portfolio={portfolio} />
            <AnalyticsGroup summary={summary} trades={trades} reasoning={reasoning} regime={regime} />
            <ConsolidatedPositions portfolio={portfolio} trades={trades} onDone={refresh} />
        </div>
    );
}

/* ---------------- Bot-brain strip (account metrics live in the top header now) ---------------- */
function BotBrainStrip({ brain, regime, scanned, onRefresh }) {
    const total = brain?.total_evaluations ?? 0;
    const qualified = brain?.greenlit ?? 0;
    const rejected = Math.max(total - qualified, 0);
    const regimeCls = regime === "BULLISH" ? "text-atlas-positive"
        : regime === "BEARISH" ? "text-atlas-negative" : "text-atlas-textSecondary";
    return (
        <div className="panel px-5 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-xs" data-testid="bot-brain-strip">
            <BrainStat label="Scanned" value={scanned} />
            <Sep />
            <BrainStat label="Setups" value={total} />
            <Sep />
            <BrainStat label="Rejected" value={rejected} valueClass="text-atlas-negative" />
            <Sep />
            <BrainStat label="Qualified" value={qualified} valueClass="text-atlas-positive" />
            <Sep />
            <span className="text-atlas-textTertiary">Regime: <span className={`font-bold ${regimeCls}`} data-testid="regime-value">{regime}</span></span>
            <button data-testid="cockpit-refresh" onClick={onRefresh} className="ml-auto text-atlas-textSecondary hover:text-atlas-text transition-colors">
                <RefreshCw className="w-4 h-4" />
            </button>
        </div>
    );
}

function BrainStat({ label, value, valueClass = "text-atlas-text" }) {
    return <span className="text-atlas-textTertiary">{label}: <span className={`font-bold tabular-nums ${valueClass}`}>{value}</span></span>;
}
const Sep = () => <span className="text-atlas-border">|</span>;

/* ---------------- Watchlist Ribbon — compact single-line selector ---------------- */
function WatchlistRibbon({ snapshots, symbols, selected, onSelect }) {
    const priceMap = useMemo(() => Object.fromEntries(snapshots.map((s) => [s.symbol, s])), [snapshots]);
    const sel = selected ? priceMap[selected] : null;
    const chg = sel?.change_24h_pct ?? null;
    const fmt = (p) => (p == null ? "—" : `$${p.toLocaleString(undefined, { minimumFractionDigits: p < 10 ? 4 : 2, maximumFractionDigits: p < 10 ? 4 : 2 })}`);
    return (
        <div className="panel px-4 py-3 flex items-center justify-between gap-3 flex-wrap" data-testid="watchlist-ribbon">
            <div className="flex items-center gap-3 min-w-0">
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
                {sel && (
                    <span className="font-mono text-sm tabular-nums text-atlas-textSecondary flex items-center gap-2">
                        {fmt(sel.price)}
                        {chg != null && (
                            <span className={`text-xs font-bold ${chg > 0 ? "text-atlas-positive" : chg < 0 ? "text-atlas-negative" : "text-atlas-textTertiary"}`}>
                                {chg > 0 ? "+" : ""}{chg.toFixed(2)}%
                            </span>
                        )}
                    </span>
                )}
            </div>
            <WatchlistControl />
        </div>
    );
}

/* ---------------- Chart Drawer ---------------- */
function ChartDrawer({ selected, candles, loading }) {
    return (
        <Drawer>
            <DrawerTrigger asChild>
                <button data-testid="open-chart-button"
                    className="w-full panel flex items-center justify-center gap-3 py-4 hover:bg-atlas-panelHover transition-colors group">
                    <BarChart3 className="w-5 h-5 text-atlas-cyan" strokeWidth={2} />
                    <span className="font-mono text-sm font-bold tracking-widest text-atlas-text">CLICK HERE FOR CHARTS</span>
                    <span className="font-mono text-[10px] text-atlas-textTertiary border border-atlas-border px-2 py-0.5 rounded">{selected ? selected.split("/")[0] : "—"} · 4H</span>
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

function TradeLifecyclePanel({ portfolio }) {
    const open = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    return (
        <div className="panel p-6" data-testid="trade-lifecycle">
            <div className="flex items-center justify-between mb-4">
                <div className="label-tag">TRADE LIFE CYCLE</div>
                <span className="font-mono text-[10px] text-atlas-textTertiary">{open.length} live</span>
            </div>
            {open.length === 0 ? (
                <div className="py-8 text-center font-mono text-xs text-atlas-textSecondary" data-testid="lifecycle-empty">
                    No live trades. The Hunter is evaluating support zones.
                </div>
            ) : (
                <div className="space-y-6">
                    {open.map((p) => <LifecycleRow key={p.symbol} p={p} />)}
                </div>
            )}
        </div>
    );
}

/* ---------------- Analytics group — expandable preview tiles ---------------- */
function AnalyticsGroup({ summary, trades, reasoning, regime }) {
    const [expanded, setExpanded] = useState("leaderboard");
    const sells = (trades || []).filter((t) => t.side === "SELL");
    const net = sells.reduce((a, t) => a + (t.pnl || 0), 0);
    const wins = sells.filter((t) => (t.pnl || 0) > 0).length;
    const buckets = summary?.confidence_buckets || [];
    const correct = buckets.reduce((a, b) => a + (b.correct_rejection || 0), 0);
    const missed = buckets.reduce((a, b) => a + (b.missed_opportunity || 0), 0);

    const CARDS = [
        { id: "leaderboard", title: "Leaderboard & Analytics", icon: Trophy,
          preview: <PreviewStat main={`${sells.length} closed`} sub={`${net >= 0 ? "+" : ""}$${net.toFixed(2)} net · ${sells.length ? Math.round((wins / sells.length) * 100) : 0}% win`} tone={net >= 0 ? "pos" : "neg"} /> },
        { id: "counterfactual", title: "Counterfactual Engine", icon: Scale,
          preview: <PreviewStat main={`${correct + missed} resolved`} sub={`${correct} correct · ${missed} missed`} tone={correct >= missed ? "pos" : "neg"} /> },
        { id: "reasoning", title: "AI Reasoning", icon: Brain,
          preview: <PreviewStat main={regime} sub={`${(reasoning || []).length} recent decisions`} tone={regime === "BULLISH" ? "pos" : regime === "BEARISH" ? "neg" : "mut"} /> },
    ];

    return (
        <div data-testid="analytics-group">
            <div className="label-tag mb-2">ANALYTICS</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {CARDS.map((c) => {
                    const Icon = c.icon;
                    const on = expanded === c.id;
                    return (
                        <button key={c.id} data-testid={`analytics-preview-${c.id}`}
                            onClick={() => setExpanded((e) => (e === c.id ? null : c.id))}
                            className={`panel p-4 text-left transition-all ${on ? "border-atlas-cyan shadow-[0_0_0_1px_rgba(96,165,250,0.4),0_0_18px_-4px_rgba(96,165,250,0.5)]" : "hover:bg-atlas-panelHover"}`}>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Icon className="w-4 h-4 text-atlas-cyan" strokeWidth={2} />
                                    <span className="font-heading font-medium text-[15px] text-atlas-text">{c.title}</span>
                                </div>
                                <ChevronDown className={`w-4 h-4 text-atlas-textSecondary transition-transform ${on ? "rotate-180" : ""}`} />
                            </div>
                            <div className="mt-3">{c.preview}</div>
                        </button>
                    );
                })}
            </div>

            <div className={`overflow-hidden transition-all duration-300 ease-out ${expanded ? "max-h-[1600px] opacity-100 mt-3" : "max-h-0 opacity-0"}`}>
                {expanded === "leaderboard" && <LeaderboardAnalytics trades={trades} />}
                {expanded === "counterfactual" && <CounterfactualPanel summary={summary} correct={correct} missed={missed} />}
                {expanded === "reasoning" && <ReasoningPanel reasoning={reasoning} />}
            </div>
        </div>
    );
}

function PreviewStat({ main, sub, tone }) {
    const cls = tone === "pos" ? "text-atlas-positive" : tone === "neg" ? "text-atlas-negative" : "text-atlas-text";
    return (
        <div>
            <div className={`font-mono text-lg font-bold tabular-nums ${cls}`}>{main}</div>
            <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">{sub}</div>
        </div>
    );
}

/* ---------------- Counterfactual + confidence distribution (expanded) ---------------- */
function CounterfactualPanel({ summary, correct, missed }) {
    const buckets = summary?.confidence_buckets || [];
    return (
        <section className="panel p-6" data-testid="counterfactual-panel">
            <div className="font-heading font-medium text-lg text-atlas-text">Counterfactual Engine</div>
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-0.5 mb-4">Correct rejections vs missed opportunities · confidence distribution</div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div>
                    {correct + missed === 0 ? <EmptyChart text="Awaiting counterfactual resolution (24h/72h/7d)..." /> : (
                        <ResponsiveContainer width="100%" height={240}>
                            <PieChart>
                                <Pie data={[{ name: "Correct Rejections", value: correct }, { name: "Missed Opportunities", value: missed }]}
                                    dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={2} stroke="none">
                                    <RCell fill={GREEN} />
                                    <RCell fill={ROSE} />
                                </Pie>
                                <RTooltip contentStyle={tooltipStyle} />
                            </PieChart>
                        </ResponsiveContainer>
                    )}
                    <Legend items={[["Correct Rejections", GREEN, correct], ["Missed Opportunities", ROSE, missed]]} />
                </div>
                <div>
                    <div className="label-tag mb-2">CONFIDENCE DISTRIBUTION</div>
                    {buckets.every((b) => !b.count) ? <EmptyChart text="No setups logged yet for this sprint." /> : (
                        <ResponsiveContainer width="100%" height={240}>
                            <BarChart data={buckets} margin={{ top: 10, right: 12, bottom: 0, left: -10 }}>
                                <XAxis dataKey="bucket" tick={{ fill: MUTED, fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#2A2D35" />
                                <YAxis allowDecimals={false} tick={{ fill: MUTED, fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#2A2D35" width={32} />
                                <RTooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(192,197,206,0.06)" }} />
                                <Bar dataKey="count" fill={SILVER} radius={[3, 3, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </div>
            </div>
        </section>
    );
}

/* ---------------- AI Reasoning (expanded) ---------------- */
function ReasoningPanel({ reasoning }) {
    return (
        <section className="panel p-6" data-testid="reasoning-panel">
            <div className="font-heading font-medium text-lg text-atlas-text">AI Reasoning</div>
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-0.5 mb-4">Latest engine decisions · bias · conviction</div>
            {(!reasoning || reasoning.length === 0) ? (
                <EmptyChart text="Awaiting first evaluation cycle..." />
            ) : (
                <ReasoningTimeline items={reasoning} />
            )}
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
        <section className="panel p-6" data-testid="leaderboard-analytics">
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
                            {leaders.map((g, i) => (
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
                    </div>
                </div>
            )}
        </section>
    );
}

/* ---------------- Consolidated positions + today's executions (bottom) ---------------- */
function ConsolidatedPositions({ portfolio, trades, onDone }) {
    const positions = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    const today = new Date().toDateString();
    const todays = (trades || []).filter((t) => t.timestamp && new Date(t.timestamp).toDateString() === today);

    return (
        <div className="panel overflow-hidden" data-testid="consolidated-positions">
            <div className="px-6 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between">
                <div className="label-tag">POSITION TRACKER</div>
                <span className="font-mono text-[10px] text-atlas-textTertiary">{positions.length} open · {todays.length} today</span>
            </div>

            {positions.length === 0 ? (
                <div className="p-8 text-center font-mono text-xs text-atlas-textSecondary" data-testid="tracker-zero-state">
                    No open positions. The Hunter is evaluating support zones.
                </div>
            ) : (
                <div className="divide-y divide-atlas-border">
                    {positions.map((p) => {
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
            )}

            <details className="group border-t border-atlas-border" data-testid="tracker-todays-executions">
                <summary className="px-6 py-3 flex items-center justify-between cursor-pointer list-none select-none">
                    <span className="label-tag">TODAY&apos;S EXECUTIONS</span>
                    <span className="font-mono text-[10px] text-atlas-textTertiary flex items-center gap-2">
                        {todays.length} today
                        <ChevronRight className="w-3.5 h-3.5 transition-transform group-open:rotate-90" />
                    </span>
                </summary>
                {todays.length === 0 ? (
                    <div className="p-6 text-center font-mono text-xs text-atlas-textSecondary border-t border-atlas-border">No executions today. Tracking zones...</div>
                ) : (
                    <div className="overflow-x-auto border-t border-atlas-border">
                        <table className="w-full text-[12px] font-mono">
                            <thead>
                                <tr className="border-b border-atlas-border text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                                    <th className="text-left px-4 py-3">Time</th>
                                    <th className="text-left px-4 py-3">Symbol</th>
                                    <th className="text-left px-4 py-3">Side</th>
                                    <th className="text-right px-4 py-3">Price</th>
                                    <th className="text-right px-4 py-3">Total</th>
                                    <th className="text-right px-4 py-3">Net P&L</th>
                                    <th className="text-left px-4 py-3">Exit</th>
                                </tr>
                            </thead>
                            <tbody>
                                {todays.map((t) => (
                                    <tr key={t.id} className="border-b border-atlas-border last:border-b-0" data-testid={`today-trade-${t.id}`}>
                                        <td className="px-4 py-2 text-atlas-textSecondary">{new Date(t.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td>
                                        <td className="px-4 py-2 text-atlas-text font-bold">{t.symbol}</td>
                                        <td className={`px-4 py-2 font-bold ${t.side === "BUY" ? "text-atlas-positive" : "text-atlas-negative"}`}>{t.side}</td>
                                        <td className="px-4 py-2 text-right tabular-nums">${(t.price || 0).toFixed(2)}</td>
                                        <td className="px-4 py-2 text-right tabular-nums">${(t.notional || 0).toFixed(2)}</td>
                                        <td className={`px-4 py-2 text-right tabular-nums font-bold ${(t.pnl || 0) > 0 ? "text-atlas-positive" : (t.pnl || 0) < 0 ? "text-atlas-negative" : "text-atlas-textSecondary"}`}>{t.pnl ? `${t.pnl > 0 ? "+" : ""}$${t.pnl.toFixed(4)}` : "—"}</td>
                                        <td className="px-4 py-2 text-[10px] text-atlas-textSecondary">{t.exit_reason || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </details>
        </div>
    );
}
