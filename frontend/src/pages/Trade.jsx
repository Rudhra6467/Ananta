import { useEffect, useMemo, useState } from "react";
import { Layers, Archive, ListOrdered, BarChart3, Power } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAppData } from "@/context/AppDataContext";
import { useAuth } from "@/context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import EnvironmentToggle from "@/components/EnvironmentToggle";
import ManualExitButton from "@/components/ManualExitButton";
import PendingOrders from "@/components/PendingOrders";
import AnalyticsPanel from "@/components/AnalyticsPanel";

const fmtNum = (v, dp = 2) => (v == null ? "—" : Number(v).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp }));
const fmtPrice = (v) => (v == null ? "—" : `$${fmtNum(v, Number(v) < 10 ? 4 : 2)}`);
const fmtDateTime = (ts) => (ts ? new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
function fmtDuration(seconds) {
    if (seconds == null || Number.isNaN(seconds)) return "—";
    const s = Math.max(0, Math.floor(seconds));
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}
const pnlCls = (v) => (v > 0 ? "text-atlas-positive" : v < 0 ? "text-atlas-negative" : "text-atlas-textSecondary");

export default function Trade() {
    const { portfolio, trades } = useAppData();
    const { isOwner } = useAuth();
    const [pending, setPending] = useState([]);
    const [analytics, setAnalytics] = useState(null);
    const [excludeSynthetic, setExcludeSynthetic] = useState(false);
    const [killed, setKilled] = useState(false);

    const positions = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    const closed = (trades || []).filter((t) => t.side === "SELL" && (t.status || "FILLED") === "FILLED");

    useEffect(() => {
        const load = () => {
            api.pendingOrders().then((d) => setPending(d.orders || d.pending || [])).catch(() => {});
            api.settings().then((s) => setKilled(!!s.manual_kill_switch)).catch(() => {});
        };
        load();
        const t = setInterval(load, 12000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        api.analyticsPerformance(excludeSynthetic).then(setAnalytics).catch(() => {});
        const t = setInterval(() => api.analyticsPerformance(excludeSynthetic).then(setAnalytics).catch(() => {}), 15000);
        return () => clearInterval(t);
    }, [excludeSynthetic]);

    const toggleKill = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try {
            await api.updateSettings({ manual_kill_switch: !killed });
            setKilled(!killed);
            toast[!killed ? "error" : "success"](!killed ? "MANUAL KILL ENGAGED" : "MANUAL KILL RELEASED", {
                description: !killed ? "All new trades blocked until released." : "Trading resumes on next cycle.",
            });
        } catch (e) { toast.error("UPDATE FAILED", { description: String(e?.message || e) }); }
    };

    return (
        <div className="space-y-5" data-testid="trade-page">
            {/* Mode + emergency stop workspace bar */}
            <div className="panel border-atlas-border rounded-2xl p-4 flex items-center justify-between gap-3 flex-wrap" data-testid="trade-mode-bar">
                <div>
                    <div className="label-tag mb-2">EXECUTION MODE</div>
                    <EnvironmentToggle />
                </div>
                <button data-testid="trade-kill-btn" onClick={toggleKill}
                    title={isOwner ? "Emergency stop — blocks all new trades" : "Owner login required"}
                    className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 font-mono text-[11px] font-bold tracking-widest transition-all ${
                        killed ? "border-atlas-negative bg-atlas-negative/15 text-atlas-negative animate-pulse"
                            : "border-atlas-negative/40 text-atlas-negative hover:bg-atlas-negative/10"}`}>
                    <Power className="w-4 h-4" strokeWidth={2.5} />{killed ? "KILL ENGAGED · RELEASE" : "EMERGENCY STOP"}
                </button>
            </div>

            <Tabs defaultValue="positions" className="atlas-tabs">
                <TabsList className="bg-transparent border-b border-atlas-border w-full justify-start gap-0 rounded-none h-auto p-0 mb-5">
                    <SubTab value="positions" label="POSITIONS" count={positions.length} icon={Layers} />
                    <SubTab value="orders" label="ORDERS" count={pending.length} icon={ListOrdered} />
                    <SubTab value="history" label="HISTORY" count={closed.length} icon={Archive} />
                    <SubTab value="performance" label="PERFORMANCE" icon={BarChart3} />
                </TabsList>

                <TabsContent value="positions" className="m-0"><Holdings positions={positions} portfolio={portfolio} /></TabsContent>
                <TabsContent value="orders" className="m-0"><PendingOrders pending={pending} /></TabsContent>
                <TabsContent value="history" className="m-0"><ClosedPositions closed={closed} /></TabsContent>
                <TabsContent value="performance" className="m-0">
                    <AnalyticsPanel analytics={analytics} excludeSynthetic={excludeSynthetic} onToggleSynthetic={setExcludeSynthetic} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

function SubTab({ value, label, count, icon: Icon }) {
    return (
        <TabsTrigger value={value} data-testid={`trade-subtab-${value}`}
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-atlas-cyan data-[state=active]:bg-transparent data-[state=active]:text-white text-atlas-textSecondary font-mono text-[11px] tracking-[0.2em] uppercase font-bold px-5 py-3 transition-colors duration-150 hover:text-white flex items-center gap-2">
            <Icon className="w-4 h-4" strokeWidth={2} /> {label}
            {count != null && <span className="text-[10px] font-bold text-atlas-textTertiary bg-atlas-panelHover rounded-full px-1.5 py-0.5 min-w-[20px] text-center">{count}</span>}
        </TabsTrigger>
    );
}

function Holdings({ positions, portfolio }) {
    const dayStart = portfolio?.day_start_equity ?? portfolio?.starting_balance ?? 0;
    const todayPnl = (portfolio?.equity ?? 0) - dayStart;
    const todayPct = portfolio?.daily_pnl_pct ?? 0;
    if (positions.length === 0) {
        return (
            <div className="panel p-12 flex flex-col items-center justify-center text-center gap-3" data-testid="holdings-zero-state">
                <Layers className="w-9 h-9 text-atlas-textTertiary" strokeWidth={1.5} />
                <div className="font-heading text-lg text-atlas-text">No open positions.</div>
                <div className="font-mono text-xs text-atlas-textSecondary max-w-sm">Positions opened by the live execution engines appear here the moment a setup clears all gates.</div>
            </div>
        );
    }
    return (
        <div className="panel overflow-hidden" data-testid="holdings-list">
            <div className="divide-y divide-atlas-border">
                {positions.map((p) => {
                    const base = p.symbol.split("/")[0];
                    const qty = p.quantity || 0, inv = (p.avg_cost || 0) * qty, rowPnl = p.unrealized_pnl || 0;
                    const rowPct = p.avg_cost > 0 ? ((p.last_price - p.avg_cost) / p.avg_cost) * 100 : 0;
                    return (
                        <div key={p.symbol} className="px-5 py-4" data-testid={`holding-row-${base}`}>
                            <div className="flex items-center justify-between font-mono text-[11px] text-atlas-textTertiary">
                                <span>{qty} Qty. · Avg. {fmtNum(p.avg_cost, p.avg_cost < 10 ? 4 : 2)}</span>
                                <span className={`font-bold ${pnlCls(rowPnl)}`}>{rowPct >= 0 ? "+" : ""}{rowPct.toFixed(2)} %</span>
                            </div>
                            <div className="flex items-center justify-between mt-1">
                                <span className="font-mono font-bold text-base text-atlas-text flex items-center gap-2">{base}{p.breakout_mode && <span className="text-[9px] text-atlas-cyan">BO</span>}</span>
                                <span className={`font-mono text-base font-bold tabular-nums ${pnlCls(rowPnl)}`}>{rowPnl >= 0 ? "+" : ""}{fmtNum(rowPnl)}</span>
                            </div>
                            <div className="flex items-center justify-between mt-1 font-mono text-[11px] text-atlas-textTertiary">
                                <span>Invested {fmtNum(inv)}</span>
                                <span className="flex items-center gap-3"><span>LTP {fmtPrice(p.last_price)}</span><ManualExitButton symbol={p.symbol} compact /></span>
                            </div>
                        </div>
                    );
                })}
            </div>
            <div className="sticky bottom-0 bg-atlas-panel border-t border-atlas-border px-5 py-3 flex items-center justify-between" data-testid="holdings-today-pnl">
                <span className="font-mono text-sm text-atlas-text font-bold">Today&apos;s P&amp;L</span>
                <span className={`font-mono text-sm font-bold tabular-nums ${pnlCls(todayPnl)}`}>
                    {todayPnl >= 0 ? "+" : ""}{fmtNum(todayPnl)} <span className="ml-2">{todayPct >= 0 ? "+" : ""}{todayPct.toFixed(2)} %</span>
                </span>
            </div>
        </div>
    );
}

const WINDOWS = [{ key: "today", label: "TODAY" }, { key: "7d", label: "7D" }, { key: "30d", label: "30D" }, { key: "all", label: "ALL TIME" }];
function withinWindow(ts, key) {
    if (key === "all") return true;
    if (!ts) return false;
    const t = new Date(ts).getTime(), now = Date.now();
    if (key === "today") { const d = new Date(ts), n = new Date(); return d.getUTCFullYear() === n.getUTCFullYear() && d.getUTCMonth() === n.getUTCMonth() && d.getUTCDate() === n.getUTCDate(); }
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
                    <div className="font-heading text-base text-atlas-text">Trade History</div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary uppercase tracking-wider mt-0.5">Chronological historical performance archive</div>
                </div>
                <div className="flex items-center gap-1 font-mono" data-testid="closed-window-filters">
                    {WINDOWS.map((w) => (
                        <button key={w.key} onClick={() => setWin(w.key)} data-testid={`closed-window-${w.key}`}
                            className={`text-[10px] tracking-widest font-bold px-2.5 py-1.5 rounded border transition-colors ${win === w.key ? "border-atlas-cyan text-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"}`}>{w.label}</button>
                    ))}
                </div>
            </div>
            {rows.length === 0 ? (
                <div className="panel p-12 flex flex-col items-center justify-center text-center gap-3 border-0" data-testid="closed-zero-state">
                    <Archive className="w-9 h-9 text-atlas-textTertiary" strokeWidth={1.5} />
                    <div className="font-heading text-lg text-atlas-text">No closed trades in this window.</div>
                    <div className="font-mono text-xs text-atlas-textSecondary max-w-sm">Completed round-trips will build a clean, scannable performance archive here.</div>
                </div>
            ) : (
                <div className="overflow-x-auto atlas-scroll">
                    <table className="w-full text-[12px] font-mono whitespace-nowrap">
                        <thead>
                            <tr className="border-b border-atlas-border text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                                <th className="text-left px-4 py-3">Asset</th><th className="text-left px-4 py-3">Entry Date</th><th className="text-left px-4 py-3">Exit Date</th>
                                <th className="text-right px-4 py-3">PnL</th><th className="text-right px-4 py-3">Return %</th><th className="text-right px-4 py-3">Duration</th><th className="text-left px-4 py-3 pl-6">Exit Reason</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((t) => {
                                const base = (t.symbol || "").split("/")[0], pnl = t.pnl || 0;
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
