import { useEffect, useMemo, useState } from "react";
import { Activity, Layers, Archive, Compass } from "lucide-react";
import api from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import ManualExitButton from "@/components/ManualExitButton";

const fmtPrice = (v) => (v == null ? "—" : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: Number(v) < 10 ? 4 : 2, maximumFractionDigits: Number(v) < 10 ? 4 : 2 })}`);
const fmtDateTime = (ts) => (ts ? new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

function fmtDuration(seconds) {
    if (seconds == null || Number.isNaN(seconds)) return "—";
    const s = Math.max(0, Math.floor(seconds));
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}
const durationFrom = (ts) => (ts ? fmtDuration((Date.now() - new Date(ts).getTime()) / 1000) : "—");
const pnlCls = (v) => (v > 0 ? "text-atlas-positive" : v < 0 ? "text-atlas-negative" : "text-atlas-textSecondary");

export default function Portfolio() {
    const [portfolio, setPortfolio] = useState(null);
    const [trades, setTrades] = useState([]);

    const refresh = () => {
        api.portfolio().then(setPortfolio).catch(() => {});
        api.trades(300).then((t) => setTrades(t.items || [])).catch(() => setTrades([]));
    };

    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 10000);
        return () => clearInterval(t);
    }, []);

    const positions = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    const closed = (trades || []).filter((t) => t.side === "SELL" && (t.status || "FILLED") === "FILLED");

    return (
        <div className="space-y-6" data-testid="portfolio-page">
            <div className="flex items-end justify-between gap-4 flex-wrap">
                <div>
                    <div className="label-tag">EXECUTION · PORTFOLIO</div>
                    <h2 className="font-heading font-light text-3xl tracking-tight mt-1 text-atlas-text">Portfolio</h2>
                </div>
            </div>

            <Tabs defaultValue="active" className="atlas-tabs">
                <TabsList className="bg-transparent border-b border-atlas-border w-full justify-start gap-0 rounded-none h-auto p-0 mb-6">
                    <SubTab value="active" label="ACTIVE" icon={Activity} />
                    <SubTab value="open" label="OPEN" icon={Layers} />
                    <SubTab value="closed" label="CLOSED" icon={Archive} />
                </TabsList>

                <TabsContent value="active" className="m-0">
                    <ActivePositions positions={positions} onDone={refresh} />
                </TabsContent>
                <TabsContent value="open" className="m-0">
                    <OpenPositions positions={positions} />
                </TabsContent>
                <TabsContent value="closed" className="m-0">
                    <ClosedPositions closed={closed} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

function SubTab({ value, label, icon: Icon }) {
    return (
        <TabsTrigger value={value} data-testid={`portfolio-subtab-${value}`}
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-atlas-cyan data-[state=active]:bg-transparent data-[state=active]:text-white text-atlas-textSecondary font-mono text-[11px] tracking-[0.2em] uppercase font-bold px-5 py-3 transition-colors duration-150 hover:text-white">
            <Icon className="w-4 h-4 mr-2" strokeWidth={2} /> {label}
        </TabsTrigger>
    );
}

function ZeroState({ testid, title, sub }) {
    return (
        <div className="panel p-12 flex flex-col items-center justify-center text-center gap-3" data-testid={testid}>
            <Compass className="w-9 h-9 text-atlas-textTertiary" strokeWidth={1.5} />
            <div className="font-heading text-lg text-atlas-text">{title}</div>
            <div className="font-mono text-xs text-atlas-textSecondary max-w-sm">{sub}</div>
        </div>
    );
}

/* ---------------- TAB 1 · ACTIVE POSITIONS ---------------- */
function ActivePositions({ positions, onDone }) {
    if (positions.length === 0) return <ZeroState testid="active-zero-state" title="No active positions." sub="Positions managed by the live execution loops appear here the moment a setup clears all gates." />;
    return (
        <div className="panel overflow-hidden" data-testid="active-positions">
            <div className="px-6 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between">
                <div>
                    <div className="font-heading text-base text-atlas-text">Active Positions</div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary uppercase tracking-wider mt-0.5">Live-tracked by the active execution engines</div>
                </div>
                <span className="font-mono text-[10px] text-atlas-textTertiary">{positions.length} active</span>
            </div>
            <div className="overflow-x-auto atlas-scroll">
                <table className="w-full text-[12px] font-mono whitespace-nowrap">
                    <thead>
                        <tr className="border-b border-atlas-border text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                            <th className="text-left px-4 py-3">Asset</th>
                            <th className="text-right px-4 py-3">Entry Price</th>
                            <th className="text-right px-4 py-3">Current Price</th>
                            <th className="text-right px-4 py-3">Unrealized PnL</th>
                            <th className="text-right px-4 py-3">Duration</th>
                            <th className="text-right px-4 py-3">Stop Level</th>
                            <th className="text-right px-4 py-3">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {positions.map((p) => {
                            const base = p.symbol.split("/")[0];
                            const pnl = p.unrealized_pnl || 0;
                            const pnlPct = p.avg_cost > 0 ? ((p.last_price - p.avg_cost) / p.avg_cost) * 100 : 0;
                            return (
                                <tr key={p.symbol} className="border-b border-atlas-border last:border-b-0 hover:bg-atlas-panelHover/40" data-testid={`active-row-${base}`}>
                                    <td className="px-4 py-3 text-atlas-text font-bold">{base}{p.breakout_mode && <span className="ml-1.5 text-[9px] text-atlas-cyan">BO</span>}</td>
                                    <td className="px-4 py-3 text-right tabular-nums text-atlas-textSecondary">{fmtPrice(p.avg_cost)}</td>
                                    <td className="px-4 py-3 text-right tabular-nums text-atlas-text">{fmtPrice(p.last_price)}</td>
                                    <td className={`px-4 py-3 text-right tabular-nums font-bold ${pnlCls(pnl)}`} data-testid={`active-pnl-${base}`}>
                                        {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}<span className="block text-[10px] font-normal opacity-80">{pnl >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%</span>
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums text-atlas-textSecondary">{durationFrom(p.entry_timestamp)}</td>
                                    <td className="px-4 py-3 text-right tabular-nums text-atlas-negative/80">{fmtPrice(p.structural_stop)}</td>
                                    <td className="px-4 py-3 text-right"><ManualExitButton symbol={p.symbol} onDone={onDone} compact /></td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

/* ---------------- TAB 2 · OPEN POSITIONS ---------------- */
function OpenPositions({ positions }) {
    if (positions.length === 0) return <ZeroState testid="open-zero-state" title="No open positions." sub="A consolidated, date-agnostic view of every open trade across the account will appear here." />;
    return (
        <div className="panel overflow-hidden" data-testid="open-positions">
            <div className="px-6 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between">
                <div>
                    <div className="font-heading text-base text-atlas-text">Open Positions</div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary uppercase tracking-wider mt-0.5">All open trades across the account · no date boundaries</div>
                </div>
                <span className="font-mono text-[10px] text-atlas-textTertiary">{positions.length} open</span>
            </div>
            <div className="overflow-x-auto atlas-scroll">
                <table className="w-full text-[12px] font-mono whitespace-nowrap">
                    <thead>
                        <tr className="border-b border-atlas-border text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                            <th className="text-left px-4 py-3">Asset</th>
                            <th className="text-left px-4 py-3">Entry Date</th>
                            <th className="text-right px-4 py-3">Entry Price</th>
                            <th className="text-right px-4 py-3">Current Price</th>
                            <th className="text-right px-4 py-3">PnL</th>
                            <th className="text-left px-4 py-3 pl-6">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {positions.map((p) => {
                            const base = p.symbol.split("/")[0];
                            const pnl = p.unrealized_pnl || 0;
                            const status = pnl > 0 ? "IN PROFIT" : pnl < 0 ? "DRAWDOWN" : "FLAT";
                            const statusCls = pnl > 0 ? "bg-atlas-positive/15 text-atlas-positive" : pnl < 0 ? "bg-atlas-negative/15 text-atlas-negative" : "bg-atlas-border text-atlas-textSecondary";
                            return (
                                <tr key={p.symbol} className="border-b border-atlas-border last:border-b-0 hover:bg-atlas-panelHover/40" data-testid={`open-row-${base}`}>
                                    <td className="px-4 py-3 text-atlas-text font-bold">{base}{p.breakout_mode && <span className="ml-1.5 text-[9px] text-atlas-cyan">BO</span>}</td>
                                    <td className="px-4 py-3 text-atlas-textSecondary">{fmtDateTime(p.entry_timestamp)}</td>
                                    <td className="px-4 py-3 text-right tabular-nums text-atlas-textSecondary">{fmtPrice(p.avg_cost)}</td>
                                    <td className="px-4 py-3 text-right tabular-nums text-atlas-text">{fmtPrice(p.last_price)}</td>
                                    <td className={`px-4 py-3 text-right tabular-nums font-bold ${pnlCls(pnl)}`}>{pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}</td>
                                    <td className="px-4 py-3 pl-6"><span className={`text-[9px] font-bold px-2 py-0.5 rounded ${statusCls}`}>{status}</span></td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

/* ---------------- TAB 3 · CLOSED POSITIONS ---------------- */
const WINDOWS = [
    { key: "today", label: "TODAY" },
    { key: "7d", label: "7D" },
    { key: "30d", label: "30D" },
    { key: "all", label: "ALL TIME" },
];
function withinWindow(ts, key) {
    if (key === "all") return true;
    if (!ts) return false;
    const t = new Date(ts).getTime();
    const now = Date.now();
    if (key === "today") {
        const d = new Date(ts), n = new Date();
        return d.getUTCFullYear() === n.getUTCFullYear() && d.getUTCMonth() === n.getUTCMonth() && d.getUTCDate() === n.getUTCDate();
    }
    if (key === "7d") return now - t <= 7 * 86400000;
    if (key === "30d") return now - t <= 30 * 86400000;
    return true;
}

function ClosedPositions({ closed }) {
    const [win, setWin] = useState("7d");
    const rows = useMemo(() => closed.filter((t) => withinWindow(t.timestamp, win)), [closed, win]);

    return (
        <div className="panel overflow-hidden" data-testid="closed-positions">
            <div className="px-6 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between flex-wrap gap-3">
                <div>
                    <div className="font-heading text-base text-atlas-text">Closed Positions</div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary uppercase tracking-wider mt-0.5">Chronological historical performance archive</div>
                </div>
                <div className="flex items-center gap-1 font-mono" data-testid="closed-window-filters">
                    {WINDOWS.map((w) => (
                        <button key={w.key} onClick={() => setWin(w.key)} data-testid={`closed-window-${w.key}`}
                            className={`text-[10px] tracking-widest font-bold px-2.5 py-1.5 rounded border transition-colors ${win === w.key ? "border-atlas-cyan text-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>
                            {w.label}
                        </button>
                    ))}
                </div>
            </div>
            {rows.length === 0 ? (
                <ZeroState testid="closed-zero-state" title="No closed trades in this window." sub="Completed round-trips will build a clean, scannable performance archive here." />
            ) : (
                <div className="overflow-x-auto atlas-scroll">
                    <table className="w-full text-[12px] font-mono whitespace-nowrap">
                        <thead>
                            <tr className="border-b border-atlas-border text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                                <th className="text-left px-4 py-3">Asset</th>
                                <th className="text-left px-4 py-3">Entry Date</th>
                                <th className="text-left px-4 py-3">Exit Date</th>
                                <th className="text-right px-4 py-3">PnL</th>
                                <th className="text-right px-4 py-3">Return %</th>
                                <th className="text-right px-4 py-3">Duration</th>
                                <th className="text-left px-4 py-3 pl-6">Exit Reason</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((t) => {
                                const base = (t.symbol || "").split("/")[0];
                                const pnl = t.pnl || 0;
                                return (
                                    <tr key={t.id} className="border-b border-atlas-border last:border-b-0 hover:bg-atlas-panelHover/40" data-testid={`closed-row-${t.id}`}>
                                        <td className="px-4 py-2.5 text-atlas-text font-bold">{base}</td>
                                        <td className="px-4 py-2.5 text-atlas-textSecondary">{fmtDateTime(t.entry_timestamp)}</td>
                                        <td className="px-4 py-2.5 text-atlas-textSecondary">{fmtDateTime(t.timestamp)}</td>
                                        <td className={`px-4 py-2.5 text-right tabular-nums font-bold ${pnlCls(pnl)}`}>{t.pnl != null ? `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(4)}` : "—"}</td>
                                        <td className={`px-4 py-2.5 text-right tabular-nums ${t.return_pct == null ? "text-atlas-textTertiary" : t.return_pct >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{t.return_pct == null ? "—" : `${t.return_pct >= 0 ? "+" : ""}${t.return_pct.toFixed(2)}%`}</td>
                                        <td className="px-4 py-2.5 text-right tabular-nums text-atlas-textSecondary">{fmtDuration(t.hold_seconds)}</td>
                                        <td className="px-4 py-2.5 pl-6 text-[10px] text-atlas-textSecondary">{t.exit_reason || "—"}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
