/** Read-only portfolio card (no reset button) for the Judge View. */
import { ArrowDownRight, ArrowUpRight, Minus, Wallet } from "lucide-react";

export default function PortfolioCardRO({ portfolio }) {
    if (!portfolio) return null;
    const totalPnl = portfolio.total_pnl || 0;
    const totalPnlPct = portfolio.total_pnl_pct || 0;
    const dailyPnlPct = portfolio.daily_pnl_pct || 0;
    const flatTotal = Math.abs(totalPnl) < 0.005;
    const flatDaily = Math.abs(dailyPnlPct) < 0.005;
    const upTotal = !flatTotal && totalPnl > 0;
    const downTotal = !flatTotal && totalPnl < 0;
    const upDaily = !flatDaily && dailyPnlPct > 0;
    const Icon = upTotal ? ArrowUpRight : downTotal ? ArrowDownRight : Minus;
    const totalCls = upTotal ? "text-atlas-positive" : downTotal ? "text-atlas-negative" : "text-atlas-textSecondary";
    const dailyCls = upDaily ? "text-atlas-positive" : flatDaily ? "text-white" : "text-atlas-negative";
    const pnlValue = flatTotal ? "$0.00" : `${upTotal ? "+" : ""}$${totalPnl.toFixed(2)}`;
    const pnlPct = flatTotal ? "0.00%" : `${upTotal ? "+" : ""}${totalPnlPct.toFixed(2)}%`;
    const dailyTxt = flatDaily ? "0.00%" : `${upDaily ? "+" : ""}${dailyPnlPct.toFixed(2)}%`;

    return (
        <div className="panel h-full flex flex-col" data-testid="portfolio-card-readonly">
            <div className="px-5 pt-4 pb-3 border-b border-atlas-border flex items-center gap-2">
                <Wallet className="w-3.5 h-3.5 text-atlas-textSecondary" />
                <span className="label-tag">SIMULATED PORTFOLIO · READ ONLY</span>
            </div>
            <div className="p-5 flex-1">
                <div className="flex items-baseline justify-between gap-4 flex-wrap">
                    <div>
                        <div className="font-mono text-4xl lg:text-5xl font-bold tracking-tight tabular-nums text-white">
                            ${portfolio.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <div className="text-[10px] font-mono text-atlas-textTertiary mt-1">EQUITY (CASH + POSITIONS)</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                        <div className={`flex items-center gap-1 font-mono text-base font-bold ${totalCls}`}>
                            <Icon className="w-4 h-4" strokeWidth={3} />
                            {pnlValue} ({pnlPct})
                        </div>
                        <div className="text-[10px] font-mono text-atlas-textTertiary">VS $100 STARTING</div>
                    </div>
                </div>

                <div className="mt-5 grid grid-cols-3 gap-0 border border-atlas-border">
                    <Cell label="CASH" value={`$${portfolio.cash.toFixed(2)}`} />
                    <Cell label="POSITIONS" value={`$${(portfolio.positions_value || 0).toFixed(2)}`} />
                    <Cell label="DAILY P&L" value={dailyTxt} color={dailyCls} />
                </div>

                {(portfolio.positions || []).length > 0 && (
                    <div className="mt-4">
                        <div className="label-tag mb-2">OPEN POSITIONS</div>
                        <div className="border border-atlas-border">
                            {portfolio.positions.map((p) => {
                                const upos = (p.last_price - p.avg_cost) * p.quantity;
                                const upUp = upos >= 0;
                                return (
                                    <div
                                        key={p.symbol}
                                        className="grid grid-cols-12 items-center px-3 py-2 border-b border-atlas-border last:border-b-0 font-mono text-[11px]"
                                    >
                                        <div className="col-span-3 font-bold text-white">{p.symbol}</div>
                                        <div className="col-span-3 text-atlas-textSecondary tabular-nums">QTY {p.quantity.toFixed(6)}</div>
                                        <div className="col-span-3 text-atlas-textSecondary tabular-nums">@ ${p.avg_cost.toFixed(2)}</div>
                                        <div
                                            className={`col-span-3 text-right tabular-nums font-bold ${
                                                upUp ? "text-atlas-positive" : "text-atlas-negative"
                                            }`}
                                        >
                                            {upUp && upos > 0 ? "+" : ""}${upos.toFixed(4)}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

function Cell({ label, value, color = "text-white" }) {
    return (
        <div className="p-3 border-r border-atlas-border last:border-r-0">
            <div className="label-tag text-[9px]">{label}</div>
            <div className={`font-mono text-base font-bold mt-1 tabular-nums ${color}`}>{value}</div>
        </div>
    );
}
