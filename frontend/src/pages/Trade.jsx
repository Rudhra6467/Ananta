import { useEffect, useMemo, useState } from "react";
import { Layers, Archive, ListOrdered, BarChart3, Power, Download, RefreshCw, RotateCcw, PlusCircle } from "lucide-react";
import { toast } from "sonner";
import api, { API } from "@/lib/api";
import { registerPdf } from "@/lib/pdfRegistry";
import { useAppData } from "@/context/AppDataContext";
import { useAuth } from "@/context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
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
    const { portfolio, trades, snapshots } = useAppData();
    const { isOwner } = useAuth();
    const [pending, setPending] = useState([]);
    const [analytics, setAnalytics] = useState(null);
    const [excludeSynthetic, setExcludeSynthetic] = useState(false);
    const [killed, setKilled] = useState(false);
    const [symbols, setSymbols] = useState([]);
    const [strategies, setStrategies] = useState([]);

    const positions = (portfolio?.positions || []).filter((p) => p.quantity > 0);
    const closed = (trades || []).filter((t) => t.side === "SELL" && (t.status || "FILLED") === "FILLED");

    const reloadStrategies = () => api.strategyMetrics().then((d) => setStrategies(Object.values(d?.metrics || {}))).catch(() => {});

    const loadAll = () => {
        api.pendingOrders().then((d) => setPending(d.orders || d.pending || [])).catch(() => {});
        api.settings().then((s) => { setKilled(!!s.manual_kill_switch); setSymbols(s.enabled_symbols || []); }).catch(() => {});
        reloadStrategies();
        api.analyticsPerformance(excludeSynthetic).then(setAnalytics).catch(() => {});
    };

    useEffect(() => {
        loadAll();
        const t = setInterval(loadAll, 12000);
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
            toast[!killed ? "error" : "success"](!killed ? "ANANTA STOPPED" : "ANANTA RESUMED", {
                description: !killed ? "All new trades blocked until you resume." : "Trading resumes on next cycle.",
            });
        } catch (e) { toast.error("UPDATE FAILED", { description: String(e?.message || e) }); }
    };

    const freshStart = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        if (!window.confirm("FRESH START: wipe ALL trade & strategy history and reset the paper book to $1200 ($75/trade). This cannot be undone. Continue?")) return;
        try {
            const r = await api.freshStart();
            toast.success(`Fresh start done — $${r.starting_balance} book, $${r.lot_usd}/trade`);
            setTimeout(loadAll, 600);
        } catch { toast.error("Fresh start failed (owner login required)"); }
    };

    const downloadPdf = () => {
        window.open(`${API}/report/full.pdf`, "_blank");
        registerPdf({ title: "Ananta Full Report", type: "full", url: `${API}/report/full.pdf` });
        toast.success("PDF DOWNLOAD STARTED", { description: "Trades + full analysis · saved to Workspace › AI Analytics · Ananta PDFs" });
    };

    return (
        <div className="space-y-5" data-testid="trade-page">
            {/* Persistent trade toolbar — actions on the left, Stop Ananta pinned top-right */}
            <div className="flex items-center justify-between gap-2 flex-wrap" data-testid="trade-toolbar">
                <div className="flex items-center gap-2 flex-wrap">
                    <button data-testid="trade-fresh-start" onClick={freshStart}
                        className="flex items-center gap-2 font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-border rounded-lg text-atlas-textSecondary hover:border-atlas-cyan hover:text-atlas-text transition-colors">
                        <RotateCcw className="w-3 h-3" /> FRESH START
                    </button>
                    <button data-testid="trade-download-pdf" onClick={downloadPdf}
                        className="flex items-center gap-2 font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-border rounded-lg text-atlas-textSecondary hover:border-atlas-cyan hover:text-atlas-text transition-colors">
                        <Download className="w-3 h-3" /> PDF
                    </button>
                    <button data-testid="trade-refresh" onClick={loadAll}
                        className="flex items-center gap-2 font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-border rounded-lg text-atlas-textSecondary hover:border-atlas-cyan hover:text-atlas-text transition-colors">
                        <RefreshCw className="w-3 h-3" /> REFRESH
                    </button>
                </div>
                <button data-testid="trade-stop-ananta" onClick={toggleKill}
                    title={isOwner ? "Stop Ananta — blocks all new trades" : "Owner login required"}
                    className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 font-mono text-[11px] font-bold tracking-widest transition-all ${
                        killed ? "border-atlas-negative bg-atlas-negative/15 text-atlas-negative animate-pulse"
                            : "border-atlas-negative/40 text-atlas-negative hover:bg-atlas-negative/10"}`}>
                    <Power className="w-4 h-4" strokeWidth={2.5} />{killed ? "STOPPED · RESUME" : "STOP ANANTA"}
                </button>
            </div>

            <Tabs defaultValue="orders" className="atlas-tabs">
                <TabsList className="bg-transparent border-b border-atlas-border w-full justify-start gap-0 rounded-none h-auto p-0 mb-5">
                    <SubTab value="orders" label="ORDERS" count={pending.length} icon={ListOrdered} />
                    <SubTab value="positions" label="POSITIONS" count={positions.length} icon={Layers} />
                    <SubTab value="history" label="HISTORY" count={closed.length} icon={Archive} />
                    <SubTab value="performance" label="PERFORMANCE" icon={BarChart3} />
                </TabsList>

                <TabsContent value="orders" className="m-0 space-y-5">
                    <OrdersSection isOwner={isOwner} symbols={symbols} snapshots={snapshots}
                        onDone={() => api.pendingOrders().then((d) => setPending(d.orders || d.pending || [])).catch(() => {})} />
                    <ActiveStrategies isOwner={isOwner} strategies={strategies} onDone={reloadStrategies} />
                    <PendingOrders pending={pending} />
                </TabsContent>
                <TabsContent value="positions" className="m-0"><Holdings positions={positions} portfolio={portfolio} /></TabsContent>
                <TabsContent value="history" className="m-0"><ClosedPositions closed={closed} /></TabsContent>
                <TabsContent value="performance" className="m-0">
                    <AnalyticsPanel analytics={analytics} excludeSynthetic={excludeSynthetic} onToggleSynthetic={setExcludeSynthetic} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

/* Orders first section — a single Start Order button (matches cockpit's Start Trading),
   revealing the order-details form on click. */
function OrdersSection({ isOwner, symbols, snapshots, onDone }) {
    const [open, setOpen] = useState(false);
    if (!open) {
        return (
            <button data-testid="orders-start-order" onClick={() => setOpen(true)}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-atlas-cyan text-black font-mono text-sm font-bold tracking-wide py-3.5 hover:brightness-110 active:scale-[0.99] transition-all">
                <PlusCircle className="w-4 h-4" /> START ORDER
            </button>
        );
    }
    return (
        <ManualOrder isOwner={isOwner} symbols={symbols} snapshots={snapshots} onClose={() => setOpen(false)}
            onDone={() => { onDone && onDone(); }} />
    );
}

function ManualOrder({ isOwner, symbols, snapshots, onDone, onClose }) {
    const [sym, setSym] = useState("");
    const [side, setSide] = useState("BUY");
    const [otype, setOtype] = useState("MARKET");
    const [amount, setAmount] = useState("100");
    const [fraction, setFraction] = useState("100");
    const [limit, setLimit] = useState("");
    const [busy, setBusy] = useState(false);
    const symList = symbols || [];
    const activeSym = sym || symList[0] || "";
    const priceMap = useMemo(() => Object.fromEntries((snapshots || []).map((s) => [s.symbol, s])), [snapshots]);
    const px = priceMap[activeSym]?.price ?? priceMap[activeSym]?.ask ?? 0;
    const amt = parseFloat(amount) || 0;
    const estUnits = px > 0 && amt > 0 ? amt / px : 0;

    const submit = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        const b = (activeSym || "").split("/")[0];
        if (!b) { toast.error("Select a symbol"); return; }
        const payload = { symbol: b, side, order_type: otype };
        if (side === "BUY") {
            if (!(amt > 0)) { toast.error("Enter a valid USD amount"); return; }
            payload.notional_usd = amt;
        } else {
            const f = parseFloat(fraction);
            if (!(f > 0)) { toast.error("Enter a valid % to sell"); return; }
            payload.fraction = Math.min(1, Math.max(0, f / 100));
        }
        if (otype === "LIMIT") {
            const lp = parseFloat(limit);
            if (!(lp > 0)) { toast.error("Enter a valid limit price"); return; }
            payload.limit_price = lp;
        }
        setBusy(true);
        try {
            const r = await api.manualOrder(payload);
            toast.success(r?.resting ? "Limit order resting" : `${side} ${b} filled`);
            onDone && onDone();
        } catch (e) { toast.error("Order failed", { description: String(e?.response?.data?.detail || e?.message || e) }); }
        finally { setBusy(false); }
    };

    return (
        <div className="panel border-atlas-border rounded-2xl p-5" data-testid="manual-order-card">
            <div className="flex items-center justify-between mb-3">
                <div className="label-tag">ORDER DETAILS</div>
                {onClose && (
                    <button data-testid="manual-order-close" onClick={onClose}
                        className="font-mono text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text transition-colors">
                        ← BACK
                    </button>
                )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                {/* 1. Amount */}
                {side === "BUY" ? (
                    <NumField label="AMOUNT (USD)" value={amount} onChange={setAmount} testid="manual-order-notional" />
                ) : (
                    <NumField label="SELL % OF POSITION" value={fraction} onChange={setFraction} testid="manual-order-fraction" />
                )}
                {/* 2. Crypto dropdown */}
                <div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary uppercase tracking-wider mb-1">SELECT CRYPTO</div>
                    <select data-testid="manual-order-symbol" value={activeSym} onChange={(e) => setSym(e.target.value)}
                        className="w-full bg-atlas-bg border border-atlas-border rounded-lg px-3 py-2.5 font-mono text-sm text-white focus:border-atlas-cyan outline-none">
                        {symList.map((s) => {
                            const b = s.split("/")[0];
                            const sp = priceMap[s];
                            return <option key={s} value={s}>{b}{sp ? ` · $${(sp.price ?? sp.ask ?? 0).toLocaleString()}` : ""}</option>;
                        })}
                    </select>
                </div>
            </div>
            {side === "BUY" && estUnits > 0 && (
                <div data-testid="manual-order-estimate" className="font-mono text-[11px] text-atlas-textSecondary mb-3">≈ {estUnits.toFixed(estUnits < 1 ? 6 : 4)} {activeSym.split("/")[0]}</div>
            )}
            {/* 3. Parameters */}
            <div className="grid grid-cols-2 gap-3">
                <Seg options={[["BUY", "BUY"], ["SELL", "SELL"]]} value={side} onChange={setSide} testid="manual-order-side" />
                <Seg options={[["MARKET", "MARKET"], ["LIMIT", "LIMIT"]]} value={otype} onChange={setOtype} testid="manual-order-type" />
            </div>
            {otype === "LIMIT" && <div className="mt-3"><NumField label="LIMIT PRICE" value={limit} onChange={setLimit} testid="manual-order-limit" /></div>}
            {/* 4. Action — Cancel + submit share one row */}
            <div className="mt-4 grid grid-cols-2 gap-3">
                {onClose && (
                    <button data-testid="manual-order-cancel" onClick={onClose} disabled={busy}
                        className="w-full rounded-lg py-3 font-mono text-xs font-bold tracking-widest border border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary disabled:opacity-50 transition-colors">
                        CANCEL ORDER
                    </button>
                )}
                <button data-testid="manual-order-submit" disabled={busy} onClick={submit}
                    className={`w-full rounded-lg py-3 font-mono text-xs font-bold tracking-widest transition-colors ${onClose ? "" : "col-span-2"} ${side === "SELL" ? "bg-atlas-negative text-white hover:opacity-90" : "bg-atlas-cyan text-black hover:opacity-90"} disabled:opacity-50`}>
                    {busy ? "PLACING…" : `${side} ${(activeSym || "").split("/")[0]}`}
                </button>
            </div>
        </div>
    );
}

function Seg({ options, value, onChange, testid }) {
    return (
        <div className="flex bg-atlas-panelHover rounded-lg p-1 border border-atlas-border">
            {options.map(([k, l]) => (
                <button key={k} data-testid={`${testid}-${k.toLowerCase()}`} onClick={() => onChange(k)}
                    className={`flex-1 text-[11px] font-mono font-bold tracking-wider py-2 rounded-md transition-colors ${value === k ? "bg-atlas-cyan text-black" : "text-atlas-textSecondary hover:text-white"}`}>{l}</button>
            ))}
        </div>
    );
}

function NumField({ label, value, onChange, testid }) {
    return (
        <div>
            <div className="font-mono text-[10px] text-atlas-textTertiary uppercase tracking-wider mb-1">{label}</div>
            <input data-testid={testid} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)}
                className="w-full bg-atlas-bg border border-atlas-border rounded-lg px-3 py-2.5 font-mono text-sm text-white focus:border-atlas-cyan outline-none" />
        </div>
    );
}

function ActiveStrategies({ isOwner, strategies, onDone }) {
    const [visible, setVisible] = useState(3);
    const toggle = async (key, isOn) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try { isOn ? await api.strategySetState(key, { status: "DISABLED" }) : await api.strategySetState(key, { enabled: true }); onDone && onDone(); }
        catch (e) { toast.error("Toggle failed", { description: String(e?.message || e) }); }
    };
    if (!strategies || strategies.length === 0) return null;
    const shown = strategies.slice(0, visible);
    return (
        <div className="panel border-atlas-border rounded-2xl p-5" data-testid="active-strategies-card">
            <div className="label-tag mb-3">ACTIVE STRATEGIES</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {shown.map((s) => {
                    const isOn = !!s.enabled && s.status !== "DISABLED" && s.status !== "ERROR";
                    return (
                        <div key={s.key} className="flex items-center justify-between rounded-lg border border-atlas-border px-4 py-3 bg-atlas-bg/40">
                            <div className="min-w-0 mr-3">
                                <div className="font-mono text-sm text-white font-bold truncate">{s.name}</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary uppercase tracking-wider">{s.status} · {s.trades} trades · WR {s.win_rate}%</div>
                            </div>
                            <Switch data-testid={`strategy-toggle-${s.key}`} checked={isOn} onCheckedChange={() => toggle(s.key, isOn)} />
                        </div>
                    );
                })}
            </div>
            {visible < strategies.length && (
                <button data-testid="strategies-show-more" onClick={() => setVisible((v) => v + 3)}
                    className="mt-3 w-full rounded-lg border border-atlas-border py-2 font-mono text-[11px] tracking-widest text-atlas-cyan hover:bg-atlas-cyan/10 transition-colors">
                    SHOW MORE ({strategies.length - visible})
                </button>
            )}
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
