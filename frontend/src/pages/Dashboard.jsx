import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
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
import CandleChart from "@/components/CandleChart";
import ManualExitButton from "@/components/ManualExitButton";
import WatchlistControl from "@/components/WatchlistControl";
import { Drawer, DrawerContent, DrawerTrigger } from "@/components/ui/drawer";

const SILVER = "#C0C5CE";
const GREEN = "#10B981";
const ROSE = "#F43F5E";
const MUTED = "#5C6370";

export default function Dashboard() {
    const [portfolio, setPortfolio] = useState(null);
    const [snapshots, setSnapshots] = useState([]);
    const [enabledSymbols, setEnabledSymbols] = useState([]);
    const [selected, setSelected] = useState(null);
    const [candles, setCandles] = useState([]);
    const [loadingChart, setLoadingChart] = useState(false);
    const [brain, setBrain] = useState(null);
    const [regime, setRegime] = useState("—");
    const [summary, setSummary] = useState(null);
    const [trades, setTrades] = useState([]);

    const refreshAll = () => {
        api.portfolio().then(setPortfolio).catch(() => {});
        api.marketSnapshots().then((s) => setSnapshots(s.snapshots || [])).catch(() => {});
        api.settings().then((st) => st?.enabled_symbols && setEnabledSymbols(st.enabled_symbols)).catch(() => {});
        api.researchRejections(24).then(setBrain).catch(() => {});
        api.researchSummary().then(setSummary).catch(() => {});
        api.trades(100).then((t) => setTrades(t.items || [])).catch(() => {});
        api.reasoning(1).then((d) => d.items?.[0] && setRegime(d.items[0].bias || "NEUTRAL")).catch(() => {});
    };

    useEffect(() => {
        refreshAll();
        const t1 = setInterval(() => api.marketSnapshots().then((s) => setSnapshots(s.snapshots || [])).catch(() => {}), 8000);
        const t2 = setInterval(refreshAll, 15000);
        return () => { clearInterval(t1); clearInterval(t2); };
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
        <div className="space-y-6" data-testid="cockpit-page">
            <ExecutiveHeader
                portfolio={portfolio}
                brain={brain}
                regime={regime}
                scanned={enabledSymbols.length}
                onRefresh={refreshAll}
            />
            <WatchlistRibbon snapshots={snapshots} symbols={enabledSymbols} selected={selected} onSelect={setSelected} />
            <ChartDrawer selected={selected} candles={candles} loading={loadingChart} />
            <OpenPositionsSnapshot portfolio={portfolio} onDone={refreshAll} />
            <AnalyticsCarousel summary={summary} />
            <LeaderboardAnalytics trades={trades} />
            <Footer portfolio={portfolio} brain={brain} trades={trades} />
        </div>
    );
}

/* ---------------- Executive Header ---------------- */
function ExecutiveHeader({ portfolio, brain, regime, scanned, onRefresh }) {
    const equity = portfolio?.equity ?? 0;
    const positionsValue = portfolio?.positions_value ?? 0;
    const slots = portfolio?.slots_used ?? 0;
    const totalPnl = portfolio?.total_pnl ?? 0;
    const totalPct = portfolio?.total_pnl_pct ?? 0;
    const dailyPct = portfolio?.daily_pnl_pct ?? 0;
    const up = totalPnl > 0.005, down = totalPnl < -0.005;
    const pnlCls = up ? "text-atlas-positive" : down ? "text-atlas-negative" : "text-atlas-textSecondary";

    const total = brain?.total_evaluations ?? 0;
    const qualified = brain?.greenlit ?? 0;
    const rejected = Math.max(total - qualified, 0);
    const regimeCls = regime === "BULLISH" ? "text-atlas-positive"
        : regime === "BEARISH" ? "text-atlas-negative" : "text-atlas-textSecondary";

    return (
        <div className="panel p-6 md:p-8" data-testid="executive-header">
            {/* Row A — Portfolio */}
            <div className="flex flex-wrap items-end justify-between gap-6">
                <div>
                    <div className="label-tag">ACCOUNT VALUE</div>
                    <div className="font-mono text-4xl md:text-5xl font-light tracking-tight tabular-nums text-atlas-text mt-2" data-testid="portfolio-value">
                        ${equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                </div>
                <div className="flex items-end gap-8">
                    <HeaderStat label="DEPLOYED" testid="deployed-positions"
                        value={`$${positionsValue.toFixed(2)}`} sub={`(${slots})`} />
                    <HeaderStat label="TOTAL P&L" testid="total-pnl" valueClass={pnlCls}
                        value={`${up ? "+" : ""}$${totalPnl.toFixed(2)}`} sub={`${up ? "+" : ""}${totalPct.toFixed(2)}%`} />
                    <HeaderStat label="DAILY P&L" testid="daily-pnl"
                        valueClass={dailyPct > 0.005 ? "text-atlas-positive" : dailyPct < -0.005 ? "text-atlas-negative" : "text-atlas-text"}
                        value={`${dailyPct > 0 ? "+" : ""}${dailyPct.toFixed(2)}%`} />
                    <button data-testid="cockpit-refresh" onClick={onRefresh}
                        className="text-atlas-textSecondary hover:text-atlas-text transition-colors mb-1">
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Row B — Bot Brain */}
            <div className="mt-6 pt-4 border-t border-atlas-border flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-xs" data-testid="bot-brain-strip">
                <BrainStat label="Scanned" value={scanned} />
                <Sep />
                <BrainStat label="Setups" value={total} />
                <Sep />
                <BrainStat label="Rejected" value={rejected} valueClass="text-atlas-negative" />
                <Sep />
                <BrainStat label="Qualified" value={qualified} valueClass="text-atlas-positive" />
                <Sep />
                <span className="text-atlas-textTertiary">Regime: <span className={`font-bold ${regimeCls}`} data-testid="regime-value">{regime}</span></span>
            </div>
        </div>
    );
}

function HeaderStat({ label, value, sub, valueClass = "text-atlas-text", testid }) {
    return (
        <div className="text-right" data-testid={testid}>
            <div className="label-tag text-[9px]">{label}</div>
            <div className={`font-mono text-xl font-medium tabular-nums mt-1 ${valueClass}`}>
                {value} {sub && <span className="text-atlas-textTertiary text-sm">{sub}</span>}
            </div>
        </div>
    );
}
function BrainStat({ label, value, valueClass = "text-atlas-text" }) {
    return <span className="text-atlas-textTertiary">{label}: <span className={`font-bold tabular-nums ${valueClass}`}>{value}</span></span>;
}
const Sep = () => <span className="text-atlas-border">|</span>;

/* ---------------- Watchlist Ribbon ---------------- */
function WatchlistRibbon({ snapshots, symbols, selected, onSelect }) {
    const priceMap = useMemo(() => Object.fromEntries(snapshots.map((s) => [s.symbol, s])), [snapshots]);
    return (
        <div data-testid="watchlist-ribbon">
            <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                <div className="label-tag">WATCHLIST · {symbols.length}</div>
                <WatchlistControl />
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 atlas-scroll">
                {symbols.map((sym) => {
                    const s = priceMap[sym];
                    const sel = selected === sym;
                    const base = sym.split("/")[0];
                    return (
                        <button
                            key={sym}
                            data-testid={`watchlist-card-${base}`}
                            onClick={() => onSelect(sym)}
                            className={`shrink-0 min-w-[140px] text-left px-4 py-3 rounded-lg border-2 transition-all ${
                                sel ? "border-atlas-cyan bg-atlas-panelHover shadow-[0_0_0_1px_rgba(96,165,250,0.4),0_0_18px_-4px_rgba(96,165,250,0.5)]" : "border-atlas-border bg-atlas-panel hover:bg-atlas-panelHover"
                            }`}
                        >
                            <div className="font-mono font-bold text-sm text-atlas-text">{base}</div>
                            <div className="font-mono text-sm tabular-nums text-atlas-textSecondary mt-1">
                                {s ? `$${s.price.toFixed(s.price < 10 ? 4 : 2)}` : "—"}
                            </div>
                            <div className="font-mono text-[10px] tabular-nums text-atlas-textTertiary mt-0.5">
                                {s ? `spread ${(s.spread_pct || 0).toFixed(3)}%` : ""}
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

/* ---------------- Chart Drawer (button → bottom drawer) ---------------- */
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

/* ---------------- Open Positions Snapshot ---------------- */
function OpenPositionsSnapshot({ portfolio, onDone }) {
    const positions = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    return (
        <div className="panel overflow-hidden" data-testid="open-positions-snapshot">
            <div className="px-6 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between">
                <div className="label-tag">OPEN POSITIONS SNAPSHOT</div>
                <span className="font-mono text-[10px] text-atlas-textTertiary">{positions.length} active</span>
            </div>
            {positions.length === 0 ? (
                <div className="p-8 text-center font-mono text-xs text-atlas-textSecondary" data-testid="snapshot-zero-state">
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
                            <div key={p.symbol} className="flex items-center justify-between gap-4 px-6 py-3.5" data-testid={`snapshot-row-${base}`}>
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
        </div>
    );
}

/* ---------------- Analytics Carousel ---------------- */
function AnalyticsCarousel({ summary }) {
    const trackRef = useRef(null);
    const scrollBy = (dir) => {
        const el = trackRef.current;
        if (el) el.scrollBy({ left: dir * el.clientWidth, behavior: "smooth" });
    };
    const buckets = summary?.confidence_buckets || [];
    const correct = buckets.reduce((a, b) => a + (b.correct_rejection || 0), 0);
    const missed = buckets.reduce((a, b) => a + (b.missed_opportunity || 0), 0);

    return (
        <div data-testid="analytics-carousel">
            <div className="flex items-center justify-between mb-2">
                <div className="label-tag">ANALYTICS</div>
                <div className="flex gap-1">
                    <button data-testid="carousel-prev" onClick={() => scrollBy(-1)} className="p-1.5 border border-atlas-border rounded text-atlas-textSecondary hover:text-atlas-text transition-colors"><ChevronLeft className="w-4 h-4" /></button>
                    <button data-testid="carousel-next" onClick={() => scrollBy(1)} className="p-1.5 border border-atlas-border rounded text-atlas-textSecondary hover:text-atlas-text transition-colors"><ChevronRight className="w-4 h-4" /></button>
                </div>
            </div>
            <div ref={trackRef} className="flex gap-6 overflow-x-auto snap-x snap-mandatory atlas-scroll pb-2">
                <CarouselSlide title="Counterfactual Engine" subtitle="Correct Rejections vs Missed Opportunities" testid="slide-counterfactual">
                    {correct + missed === 0 ? (
                        <EmptyChart text="Awaiting counterfactual resolution (24h/72h/7d)..." />
                    ) : (
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
                </CarouselSlide>

                <CarouselSlide title="Confidence Distribution" subtitle="Setups grouped by confidence band" testid="slide-confidence">
                    {buckets.every((b) => !b.count) ? (
                        <EmptyChart text="No setups logged yet for this sprint." />
                    ) : (
                        <ResponsiveContainer width="100%" height={240}>
                            <BarChart data={buckets} margin={{ top: 10, right: 12, bottom: 0, left: -10 }}>
                                <XAxis dataKey="bucket" tick={{ fill: MUTED, fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#2A2D35" />
                                <YAxis allowDecimals={false} tick={{ fill: MUTED, fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="#2A2D35" width={32} />
                                <RTooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(192,197,206,0.06)" }} />
                                <Bar dataKey="count" fill={SILVER} radius={[3, 3, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </CarouselSlide>
            </div>
        </div>
    );
}

function CarouselSlide({ title, subtitle, children, testid }) {
    return (
        <div className="panel p-6 min-w-full snap-center" data-testid={testid}>
            <div className="font-heading font-medium text-lg text-atlas-text">{title}</div>
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">{subtitle}</div>
            {children}
        </div>
    );
}
function EmptyChart({ text }) {
    return <div className="h-[240px] flex items-center justify-center text-atlas-textSecondary font-mono text-xs text-center px-6">{text}</div>;
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
        const pieData = groups.map((g) => ({ name: g.key, value: property === "drawdown" ? Math.abs(g.net) : g.count }))
            .filter((d) => d.value > 0);
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
                    {/* dynamic pie */}
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

                    {/* leaderboard ranked by net P&L */}
                    <div data-testid="leaderboard-table">
                        <div className="label-tag mb-3">RANKED BY NET P&amp;L</div>
                        <div className="space-y-1.5">
                            {leaders.map((g, i) => (
                                <div key={g.key} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-atlas-panelHover/40 border border-atlas-border"
                                    data-testid={`leaderboard-row-${i}`}>
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

/* ---------------- Footer: lifecycle + today's executions ---------------- */
function Footer({ portfolio, brain, trades }) {
    const positions = portfolio?.positions || [];
    const inProfit = positions.some((p) => (p.last_price - p.avg_cost) > 0);
    const today = new Date().toDateString();
    const todays = (trades || []).filter((t) => t.timestamp && new Date(t.timestamp).toDateString() === today);

    const steps = ["Detected", "Qualified", "Entered", "Trailing Armed", "Exited"];
    let active = 0;
    if ((brain?.total_evaluations ?? 0) > 0) active = 0;
    if ((brain?.greenlit ?? 0) > 0) active = 1;
    if (positions.length > 0) active = 2;
    if (inProfit) active = 3;
    if (todays.some((t) => t.side === "SELL")) active = 4;

    return (
        <div className="grid grid-cols-1 gap-6">
            {/* Lifecycle stepper */}
            <div className="panel p-6" data-testid="lifecycle-stepper">
                <div className="label-tag mb-4">TRADE LIFECYCLE</div>
                <div className="flex items-center">
                    {steps.map((s, i) => (
                        <div key={s} className="flex items-center flex-1 last:flex-none">
                            <div className="flex flex-col items-center gap-2">
                                <span className={`w-3 h-3 rounded-full ${i < active ? "bg-atlas-positive" : i === active ? "bg-atlas-cyan" : "bg-atlas-border"}`} />
                                <span className={`font-mono text-[10px] tracking-wide whitespace-nowrap ${i <= active ? "text-atlas-text" : "text-atlas-textTertiary"}`}>{s}</span>
                            </div>
                            {i < steps.length - 1 && <div className={`h-px flex-1 mx-2 ${i < active ? "bg-atlas-positive" : "bg-atlas-border"}`} />}
                        </div>
                    ))}
                </div>
            </div>

            {/* Today's executions — collapsed by default to keep the cockpit focused */}
            <details className="panel group" data-testid="todays-executions">
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
