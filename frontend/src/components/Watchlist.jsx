import { useEffect, useMemo, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip as RTooltip,
    XAxis,
    YAxis,
} from "recharts";
import api from "@/lib/api";
import { toast } from "sonner";

// Curated set of well-vetted Kraken spot pairs (high liquidity tier).
// We intentionally cap the universe to avoid illiquid books distorting our
// orderbook-imbalance math.
const CURATED_SYMBOLS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "PAXG/USD", "AVAX/USD", "LINK/USD",
    "ADA/USD", "XRP/USD", "DOT/USD", "MATIC/USD", "LTC/USD", "ATOM/USD",
    "UNI/USD", "AAVE/USD", "NEAR/USD", "ARB/USD", "OP/USD", "INJ/USD",
    "RNDR/USD", "FET/USD", "TAO/USD", "SUI/USD", "APT/USD", "TIA/USD", "SEI/USD",
    "BTC/USDC", "ETH/USDC", "SOL/USDC", "PAXG/USDC", "AVAX/USDC", "LINK/USDC",
];

const TF_OPTIONS = [
    { label: "1H", limit: 1 },
    { label: "6H", limit: 6 },
    { label: "24H", limit: 24 },
];

export default function Watchlist({ snapshots = [], enabledSymbols = [], onSymbolsChange }) {
    const [selected, setSelected] = useState(null);
    const [tf, setTf] = useState(24);
    const [candles, setCandles] = useState([]);
    const [loadingChart, setLoadingChart] = useState(false);
    const [showModal, setShowModal] = useState(false);

    const symbolPrice = useMemo(() => {
        const m = {};
        snapshots.forEach((s) => (m[s.symbol] = s));
        return m;
    }, [snapshots]);

    // auto-select first symbol on first render
    useEffect(() => {
        if (!selected && enabledSymbols.length > 0) setSelected(enabledSymbols[0]);
    }, [selected, enabledSymbols]);

    // fetch candles when selected/tf changes
    useEffect(() => {
        if (!selected) return;
        setLoadingChart(true);
        api.candles(selected, "1h", tf)
            .then((d) => setCandles(d.candles || []))
            .catch(() => setCandles([]))
            .finally(() => setLoadingChart(false));
    }, [selected, tf]);

    const addSymbol = async (sym) => {
        if (enabledSymbols.includes(sym)) {
            toast.error("ALREADY TRACKED", { description: sym });
            return;
        }
        const next = [...enabledSymbols, sym];
        try {
            await api.updateSettings({ enabled_symbols: next });
            onSymbolsChange && onSymbolsChange(next);
            toast.success("SYMBOL ADDED", { description: sym });
            setShowModal(false);
        } catch (e) {
            toast.error("ADD FAILED", { description: String(e?.message || e) });
        }
    };

    const removeSymbol = async (sym) => {
        if (enabledSymbols.length <= 1) {
            toast.error("CANNOT REMOVE", { description: "Watchlist must have at least 1 symbol." });
            return;
        }
        const next = enabledSymbols.filter((s) => s !== sym);
        try {
            await api.updateSettings({ enabled_symbols: next });
            onSymbolsChange && onSymbolsChange(next);
            if (selected === sym) setSelected(next[0]);
            toast.success("REMOVED", { description: sym });
        } catch (e) {
            toast.error("REMOVE FAILED", { description: String(e?.message || e) });
        }
    };

    const available = CURATED_SYMBOLS.filter((s) => !enabledSymbols.includes(s));

    return (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" data-testid="watchlist-section">
            {/* LIST */}
            <div className="panel lg:col-span-4 flex flex-col" data-testid="watchlist-panel">
                <div className="px-4 pt-3 pb-2 border-b border-atlas-border flex items-center justify-between">
                    <div className="label-tag">WATCHLIST · {enabledSymbols.length}</div>
                    <button
                        data-testid="watchlist-add-btn"
                        onClick={() => setShowModal(true)}
                        className="text-atlas-cyan hover:text-cyan-300 transition-colors"
                        aria-label="Add symbol"
                    >
                        <Plus className="w-4 h-4" strokeWidth={2.5} />
                    </button>
                </div>
                <div className="max-h-[420px] overflow-y-auto">
                    {enabledSymbols.length === 0 && (
                        <div className="p-4 text-[11px] font-mono text-atlas-textSecondary">
                            Watchlist is empty. Click + to add a symbol.
                        </div>
                    )}
                    {enabledSymbols.map((sym) => {
                        const s = symbolPrice[sym];
                        const isSel = selected === sym;
                        return (
                            <div
                                key={sym}
                                role="button"
                                tabIndex={0}
                                data-testid={`watchlist-item-${sym.replace("/", "-")}`}
                                onClick={() => setSelected(sym)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter" || e.key === " ") setSelected(sym);
                                }}
                                className={`w-full cursor-pointer text-left px-4 py-3 border-b border-atlas-border flex items-center justify-between transition-colors ${
                                    isSel ? "bg-atlas-cyan/10 border-l-2 border-l-atlas-cyan" : "panel-hover"
                                }`}
                            >
                                <div className="font-mono">
                                    <div className="text-white text-sm font-bold tracking-wide">{sym}</div>
                                    <div className="text-[10px] text-atlas-textSecondary uppercase">
                                        {s ? s.exchange : "—"}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <div className="font-mono text-right">
                                        <div className="text-white tabular-nums text-sm">
                                            {s ? `$${s.price.toFixed(s.price < 10 ? 4 : 2)}` : "—"}
                                        </div>
                                        <div className="text-[10px] text-atlas-textSecondary tabular-nums">
                                            {s ? `${(s.spread_pct || 0).toFixed(3)}%` : ""}
                                        </div>
                                    </div>
                                    <button
                                        data-testid={`watchlist-remove-${sym.replace("/", "-")}`}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            removeSymbol(sym);
                                        }}
                                        className="text-atlas-textTertiary hover:text-atlas-negative transition-colors"
                                        aria-label={`Remove ${sym}`}
                                    >
                                        <X className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* CHART */}
            <div className="panel lg:col-span-8 flex flex-col" data-testid="watchlist-chart-panel">
                <div className="px-4 pt-3 pb-2 border-b border-atlas-border flex items-center justify-between flex-wrap gap-2">
                    <div>
                        <div className="label-tag">PRICE · 1H CANDLES</div>
                        <div className="text-white font-bold text-base mt-1 font-mono tracking-wide" data-testid="watchlist-chart-symbol">
                            {selected || "—"}
                        </div>
                    </div>
                    <div className="flex items-center gap-0 border border-atlas-border" data-testid="watchlist-timeframe">
                        {TF_OPTIONS.map((o) => (
                            <button
                                key={o.label}
                                data-testid={`watchlist-tf-${o.label}`}
                                onClick={() => setTf(o.limit)}
                                className={`px-3 py-1.5 font-mono text-[10px] tracking-widest font-bold border-r border-atlas-border last:border-r-0 transition-colors ${
                                    tf === o.limit ? "bg-atlas-cyan text-atlas-bg" : "text-atlas-textSecondary hover:text-white"
                                }`}
                            >
                                {o.label}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="p-3 h-[420px]">
                    {loadingChart && (
                        <div className="h-full flex items-center justify-center text-atlas-textSecondary font-mono text-xs">
                            <span className="blink-cursor">LOADING CHART</span>
                        </div>
                    )}
                    {!loadingChart && candles.length === 0 && (
                        <div className="h-full flex items-center justify-center text-atlas-textSecondary font-mono text-xs">
                            NO CANDLES AVAILABLE
                        </div>
                    )}
                    {!loadingChart && candles.length > 0 && (
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={candles} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
                                <defs>
                                    <linearGradient id="atlasGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} />
                                        <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid stroke="#1f2937" strokeDasharray="2 4" />
                                <XAxis
                                    dataKey="t"
                                    tickFormatter={(t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                                    tick={{ fill: "#64748b", fontSize: 10, fontFamily: "JetBrains Mono" }}
                                    stroke="#1f2937"
                                />
                                <YAxis
                                    domain={["auto", "auto"]}
                                    tickFormatter={(v) => (v < 10 ? v.toFixed(2) : v.toFixed(0))}
                                    tick={{ fill: "#64748b", fontSize: 10, fontFamily: "JetBrains Mono" }}
                                    stroke="#1f2937"
                                    width={50}
                                />
                                <RTooltip
                                    contentStyle={{
                                        background: "#0a0e1a",
                                        border: "1px solid #1f2937",
                                        fontFamily: "JetBrains Mono",
                                        fontSize: "11px",
                                    }}
                                    labelFormatter={(t) => new Date(t).toLocaleString()}
                                    formatter={(v) => [`$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 })}`, "Close"]}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="close"
                                    stroke="#22d3ee"
                                    strokeWidth={1.5}
                                    fill="url(#atlasGrad)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    )}
                </div>
            </div>

            {/* ADD-SYMBOL MODAL */}
            {showModal && (
                <AddSymbolModal
                    available={available}
                    onSelect={addSymbol}
                    onClose={() => setShowModal(false)}
                />
            )}
        </div>
    );
}

function AddSymbolModal({ available, onSelect, onClose }) {
    const [q, setQ] = useState("");
    const filtered = available.filter((s) => s.toLowerCase().includes(q.toLowerCase()));
    return (
        <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
            data-testid="add-symbol-modal"
            onClick={onClose}
        >
            <div
                className="panel w-full max-w-md max-h-[80vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="px-4 py-3 border-b border-atlas-border flex items-center justify-between">
                    <div className="label-tag">ADD SYMBOL · CURATED</div>
                    <button
                        data-testid="add-symbol-close"
                        onClick={onClose}
                        className="text-atlas-textSecondary hover:text-white"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
                <div className="px-4 py-3 border-b border-atlas-border flex items-center gap-2">
                    <Search className="w-3.5 h-3.5 text-atlas-textSecondary" />
                    <input
                        autoFocus
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder="search BTC, ETH, PAXG ..."
                        data-testid="add-symbol-search"
                        className="flex-1 bg-transparent outline-none text-white text-sm font-mono placeholder:text-atlas-textTertiary"
                    />
                </div>
                <div className="overflow-y-auto">
                    {filtered.length === 0 && (
                        <div className="p-4 font-mono text-xs text-atlas-textSecondary">
                            No symbols match — all curated pairs already tracked.
                        </div>
                    )}
                    {filtered.map((sym) => (
                        <button
                            key={sym}
                            data-testid={`add-symbol-option-${sym.replace("/", "-")}`}
                            onClick={() => onSelect(sym)}
                            className="w-full text-left px-4 py-3 border-b border-atlas-border last:border-b-0 panel-hover transition-colors font-mono text-sm text-white"
                        >
                            {sym}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
