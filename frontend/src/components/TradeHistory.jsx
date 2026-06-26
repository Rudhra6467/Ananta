import { ArrowDownLeft, ArrowUpRight } from "lucide-react";

function fmtDateTime(iso) {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        const hh = String(d.getHours()).padStart(2, "0");
        const mi = String(d.getMinutes()).padStart(2, "0");
        const ss = String(d.getSeconds()).padStart(2, "0");
        return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
    } catch (e) {
        return iso;
    }
}

export default function TradeHistory({ trades }) {
    if (!trades || trades.length === 0) {
        return (
            <div className="panel p-8 text-center font-mono text-[11px] text-atlas-textSecondary" data-testid="trade-history-empty">
                NO TRADES YET. THE ENGINE WILL ACT ONLY WHEN CONVICTION + MICROSTRUCTURE ALIGN AND ALL KILL-SWITCHES ARE GREEN.
            </div>
        );
    }
    return (
        <div className="panel" data-testid="trade-history-table">
            {/* internal scroll — top 10 visible (~420px), the rest scroll below */}
            <div className="max-h-[420px] overflow-y-auto overflow-x-auto">
                <table className="w-full text-[12px] font-mono">
                    <thead className="sticky top-0 bg-atlas-panel z-10">
                        <tr className="border-b border-atlas-border text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                            <th className="text-left px-4 py-3 font-bold">Date / Time</th>
                            <th className="text-left px-4 py-3 font-bold">Symbol</th>
                            <th className="text-left px-4 py-3 font-bold">Side</th>
                            <th className="text-right px-4 py-3 font-bold">Tokens</th>
                            <th className="text-right px-4 py-3 font-bold">Price</th>
                            <th className="text-right px-4 py-3 font-bold">Total USD</th>
                            <th className="text-right px-4 py-3 font-bold">AI Confidence</th>
                            <th className="text-right px-4 py-3 font-bold">Fee</th>
                            <th className="text-right px-4 py-3 font-bold">Net P&L</th>
                            <th className="text-left px-4 py-3 font-bold">Exit Reason</th>
                            <th className="text-left px-4 py-3 font-bold">Mode</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trades.map((t) => {
                            const isBuy = t.side === "BUY";
                            return (
                                <tr
                                    key={t.id}
                                    className="border-b border-atlas-border last:border-b-0 panel-hover transition-colors"
                                    data-testid={`trade-row-${t.id}`}
                                >
                                    <td className="px-4 py-2 text-atlas-textSecondary whitespace-nowrap">{fmtDateTime(t.timestamp)}</td>
                                    <td className="px-4 py-2 text-white font-bold">{t.symbol}</td>
                                    <td className={`px-4 py-2 font-bold ${isBuy ? "text-atlas-positive" : "text-atlas-negative"}`}>
                                        <span className="inline-flex items-center gap-1">
                                            {isBuy ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownLeft className="w-3 h-3" />}
                                            {t.side}
                                        </span>
                                    </td>
                                    <td className="px-4 py-2 text-right tabular-nums">{(t.quantity || 0).toFixed(6)}</td>
                                    <td className="px-4 py-2 text-right tabular-nums">${(t.price || 0).toFixed(2)}</td>
                                    <td className="px-4 py-2 text-right tabular-nums">${(t.notional || 0).toFixed(2)}</td>
                                    <td className="px-4 py-2 text-right text-atlas-cyan tabular-nums">{(t.confidence || 0).toFixed(2)}</td>
                                    <td className="px-4 py-2 text-right text-atlas-textSecondary tabular-nums">
                                        {t.fee_usd ? `-$${t.fee_usd.toFixed(4)}` : "—"}
                                    </td>
                                    <td
                                        className={`px-4 py-2 text-right tabular-nums font-bold ${
                                            (t.pnl || 0) > 0
                                                ? "text-atlas-positive"
                                                : (t.pnl || 0) < 0
                                                    ? "text-atlas-negative"
                                                    : "text-atlas-textSecondary"
                                        }`}
                                    >
                                        {t.pnl ? `${t.pnl > 0 ? "+" : ""}$${t.pnl.toFixed(4)}` : "—"}
                                    </td>
                                    <td className="px-4 py-2 text-[10px] tracking-wider text-atlas-textSecondary">
                                        {t.exit_reason || "—"}
                                    </td>
                                    <td className="px-4 py-2 text-[10px] tracking-widest text-atlas-textSecondary">{t.mode}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
