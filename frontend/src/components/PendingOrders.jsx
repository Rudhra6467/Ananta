import { Clock } from "lucide-react";

/**
 * Resting Post-Only MAKER buy orders (PAPER). Shows the Execution Friction
 * Layer at work — orders rest at the best bid until price crosses or stays
 * flat for 2 ticks, otherwise they're cancelled as MISSED_FILL_PRICE_RUN.
 */
export default function PendingOrders({ pending }) {
    const items = pending?.items || [];
    if (items.length === 0) return null;

    return (
        <section data-testid="pending-orders-section">
            <div className="mb-3">
                <div className="label-tag">EXECUTION FRICTION LAYER · POST-ONLY</div>
                <h2 className="font-heading font-bold text-2xl tracking-tight mt-1">Resting Maker Orders</h2>
            </div>
            <div className="panel" data-testid="pending-orders-table">
                <table className="w-full text-[12px] font-mono">
                    <thead>
                        <tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest border-b border-atlas-border">
                            <th className="text-left px-4 py-2 font-bold">Symbol</th>
                            <th className="text-right px-4 py-2 font-bold">Qty</th>
                            <th className="text-right px-4 py-2 font-bold">Resting Bid</th>
                            <th className="text-right px-4 py-2 font-bold">Flat Ticks</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((o) => (
                            <tr
                                key={o.id}
                                className="border-b border-atlas-border last:border-b-0"
                                data-testid={`pending-order-${o.symbol.replace("/", "-")}`}
                            >
                                <td className="px-4 py-2 text-white font-bold flex items-center gap-2">
                                    <Clock className="w-3 h-3 text-atlas-cyan animate-pulse" />
                                    {o.symbol}
                                </td>
                                <td className="px-4 py-2 text-right tabular-nums">{Number(o.quantity).toFixed(6)}</td>
                                <td className="px-4 py-2 text-right tabular-nums text-atlas-cyan">
                                    ${Number(o.limit_price).toFixed(4)}
                                </td>
                                <td className="px-4 py-2 text-right tabular-nums">{o.ticks_flat} / 2</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
