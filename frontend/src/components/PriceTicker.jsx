import { ArrowDown, ArrowUp, Minus } from "lucide-react";

function fmtPrice(p) {
    if (p == null) return "—";
    if (p >= 1000) return p.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (p >= 1) return p.toFixed(3);
    return p.toFixed(5);
}

export default function PriceTicker({ snapshot, prevPrice }) {
    if (!snapshot) return null;
    const change = snapshot.change_24h_pct || 0;
    const isUp = change >= 0;
    const flashClass =
        prevPrice == null
            ? ""
            : snapshot.price > prevPrice
                ? "flash-up"
                : snapshot.price < prevPrice
                    ? "flash-down"
                    : "";

    const imb = snapshot.orderbook_imbalance || 0;
    const imbColor = imb > 0.15 ? "text-atlas-positive" : imb < -0.15 ? "text-atlas-negative" : "text-atlas-textSecondary";
    const Icon = isUp ? ArrowUp : ArrowDown;

    return (
        <div
            data-testid={`price-ticker-${snapshot.symbol.replace("/", "-")}`}
            className={`p-4 border-r border-b border-atlas-border last:border-r-0 panel-hover transition-colors ${flashClass}`}
        >
            <div className="flex items-center justify-between">
                <div className="font-mono text-[11px] font-bold tracking-wider text-white">
                    {snapshot.symbol}
                </div>
                <div className="label-tag text-[9px]">{snapshot.exchange}</div>
            </div>
            <div className="mt-2 font-mono text-2xl font-bold tracking-tight tabular-nums">
                ${fmtPrice(snapshot.price)}
            </div>
            <div className="mt-1 flex items-center gap-1 font-mono text-[11px] tabular-nums">
                <Icon className={`w-3 h-3 ${isUp ? "text-atlas-positive" : "text-atlas-negative"}`} strokeWidth={3} />
                <span className={isUp ? "text-atlas-positive" : "text-atlas-negative"}>
                    {isUp ? "+" : ""}
                    {change.toFixed(2)}%
                </span>
                <span className="text-atlas-textTertiary ml-2">24H</span>
            </div>
            <div className="mt-3 pt-3 border-t border-atlas-border/60 grid grid-cols-2 gap-1 font-mono text-[10px]">
                <div>
                    <div className="text-atlas-textTertiary">BID</div>
                    <div className="text-atlas-positive tabular-nums">${fmtPrice(snapshot.bid)}</div>
                </div>
                <div>
                    <div className="text-atlas-textTertiary">ASK</div>
                    <div className="text-atlas-negative tabular-nums">${fmtPrice(snapshot.ask)}</div>
                </div>
                <div>
                    <div className="text-atlas-textTertiary">SPREAD</div>
                    <div className="text-white tabular-nums">{(snapshot.spread_pct || 0).toFixed(3)}%</div>
                </div>
                <div>
                    <div className="text-atlas-textTertiary">IMBALANCE</div>
                    <div className={`tabular-nums ${imbColor}`}>
                        {imb >= 0 ? "+" : ""}
                        {imb.toFixed(2)}
                    </div>
                </div>
            </div>
        </div>
    );
}
