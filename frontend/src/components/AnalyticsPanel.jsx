import { useState } from "react";
import { Layers, Brain, FlaskConical, Activity } from "lucide-react";

function fmtUsd(v, signed = false) {
    if (v === null || v === undefined) return "—";
    const sign = signed && v > 0 ? "+" : "";
    return `${sign}$${Number(v).toFixed(2)}`;
}

function MetricTile({ label, value, accent = "text-white", sub, testid }) {
    return (
        <div className="panel p-4" data-testid={testid}>
            <div className="label-tag">{label}</div>
            <div className={`font-heading font-bold text-2xl mt-1 tabular-nums ${accent}`}>{value}</div>
            {sub && <div className="font-mono text-[10px] text-atlas-textTertiary mt-1">{sub}</div>}
        </div>
    );
}

function RegimeInsightCard({ insight }) {
    if (!insight) return null;

    // Not enough data yet → elegant placeholder
    if (!insight.ready) {
        const pct = Math.min(100, (insight.total_completed_trades / insight.min_trades_required) * 100);
        return (
            <div className="panel p-5 mb-4 relative overflow-hidden" data-testid="regime-insight-placeholder">
                <div className="flex items-center gap-3">
                    <Brain className="w-5 h-5 text-atlas-cyan animate-pulse shrink-0" />
                    <div className="flex-1">
                        <div className="font-heading font-bold text-base text-white tracking-tight">
                            Analyzing Market Regimes…
                        </div>
                        <div className="font-mono text-[11px] text-atlas-textSecondary mt-0.5">
                            Accumulating Trade Data Base — {insight.total_completed_trades}/
                            {insight.min_trades_required} round-trips
                        </div>
                        <div className="mt-3 h-1.5 bg-atlas-border rounded-full overflow-hidden">
                            <div
                                className="h-full bg-atlas-cyan transition-all duration-700"
                                style={{ width: `${pct}%` }}
                            />
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    const positive = (insight.best_expectancy_usd || 0) > 0;
    return (
        <div
            className={`panel p-5 mb-4 border-l-2 ${positive ? "border-l-atlas-positive" : "border-l-atlas-warning"}`}
            data-testid="regime-insight-card"
        >
            <div className="flex items-start gap-3">
                <Brain className={`w-5 h-5 shrink-0 mt-0.5 ${positive ? "text-atlas-positive" : "text-atlas-warning"}`} />
                <div className="flex-1">
                    <div className="label-tag">BEST REGIME TO TRADE</div>
                    {insight.best_regime && (
                        <div className="font-heading font-bold text-2xl tracking-tight mt-1" data-testid="best-regime-name">
                            {insight.best_regime}
                            {positive && (
                                <span className="text-atlas-positive text-lg ml-3 tabular-nums">
                                    {`$${Number(insight.best_expectancy_usd).toFixed(2)}/trade`}
                                </span>
                            )}
                        </div>
                    )}
                    <div className="font-mono text-[11px] text-atlas-textSecondary mt-2 leading-relaxed">
                        {insight.insight_text}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function AnalyticsPanel({ analytics, excludeSynthetic = false, onToggleSynthetic }) {
    const [win, setWin] = useState("rolling_24h");
    const m = analytics ? analytics[win] : null;
    const insight = analytics ? analytics.regime_insight : null;
    const syntheticCount = analytics ? analytics.synthetic_count || 0 : 0;

    const expectancyAccent =
        m && m.expectancy_usd > 0 ? "text-atlas-positive" : m && m.expectancy_usd < 0 ? "text-atlas-negative" : "text-atlas-textSecondary";
    const netAccent =
        m && m.net_pnl_usd > 0 ? "text-atlas-positive" : m && m.net_pnl_usd < 0 ? "text-atlas-negative" : "text-atlas-textSecondary";
    const pf = m && m.profit_factor !== null && m.profit_factor !== undefined ? m.profit_factor.toFixed(2) : "∞ / —";

    const regimes = (m && m.regime_breakdown) || {};
    const regimeKeys = Object.keys(regimes);

    return (
        <section data-testid="analytics-panel">
            <div className="flex items-center justify-between mb-3">
                <div>
                    <h2 className="font-heading font-bold text-2xl tracking-tight">Performance Analytics</h2>
                    <p className="text-atlas-textSecondary text-xs mt-1 max-w-xl">
                        How your closed trades are performing — win rate, average win/loss, and your profit edge per trade. Populates as round-trips complete.
                    </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                    <div className="flex border border-atlas-border" data-testid="analytics-window-toggle">
                        {[
                            { id: "rolling_24h", label: "ROLLING 24H" },
                            { id: "calendar_day", label: "TODAY" },
                        ].map((w) => (
                            <button
                                key={w.id}
                                type="button"
                                data-testid={`analytics-window-${w.id}`}
                                onClick={() => setWin(w.id)}
                                className={`px-3 py-1.5 font-mono text-[10px] tracking-widest font-bold transition-colors ${
                                    win === w.id ? "bg-atlas-cyan text-atlas-bg" : "text-atlas-textSecondary hover:text-white"
                                }`}
                            >
                                {w.label}
                            </button>
                        ))}
                    </div>
                    {onToggleSynthetic && (
                        <div
                            className="flex border border-atlas-border"
                            data-testid="analytics-source-toggle"
                            title={
                                syntheticCount > 0
                                    ? `${syntheticCount} synthetic DEMO_SEED trades in the database`
                                    : "No synthetic demo trades present"
                            }
                        >
                            <button
                                type="button"
                                data-testid="analytics-source-all"
                                onClick={() => onToggleSynthetic(false)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 font-mono text-[10px] tracking-widest font-bold transition-colors ${
                                    !excludeSynthetic ? "bg-atlas-cyan text-atlas-bg" : "text-atlas-textSecondary hover:text-white"
                                }`}
                            >
                                <FlaskConical className="w-3 h-3" />
                                ALL DATA
                            </button>
                            <button
                                type="button"
                                data-testid="analytics-source-organic"
                                onClick={() => onToggleSynthetic(true)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 font-mono text-[10px] tracking-widest font-bold transition-colors ${
                                    excludeSynthetic ? "bg-atlas-positive text-atlas-bg" : "text-atlas-textSecondary hover:text-white"
                                }`}
                            >
                                <Activity className="w-3 h-3" />
                                LIVE ONLY
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {excludeSynthetic && syntheticCount > 0 && (
                <div
                    className="font-mono text-[10px] text-atlas-positive mb-3 flex items-center gap-1.5"
                    data-testid="analytics-synthetic-hidden-note"
                >
                    <Activity className="w-3 h-3" />
                    Showing ORGANIC trades only — {syntheticCount} synthetic demo trade
                    {syntheticCount === 1 ? "" : "s"} hidden.
                </div>
            )}

            {/* BEST REGIME TO TRADE — insight card */}
            <RegimeInsightCard insight={insight} />

            {!m || m.closed_trades === 0 ? (
                <div
                    className="panel p-8 text-center font-mono text-[11px] text-atlas-textSecondary"
                    data-testid="analytics-empty"
                >
                    NO CLOSED TRADES IN THIS WINDOW YET. METRICS POPULATE AS ROUND-TRIPS COMPLETE.
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <MetricTile
                            testid="metric-expectancy"
                            label="EXPECTANCY / TRADE"
                            value={fmtUsd(m.expectancy_usd, true)}
                            accent={expectancyAccent}
                            sub={`(${m.win_rate_pct}% × ${fmtUsd(m.avg_win_usd)}) − (${m.loss_rate_pct}% × ${fmtUsd(m.avg_loss_usd)})`}
                        />
                        <MetricTile
                            testid="metric-profit-factor"
                            label="PROFIT FACTOR"
                            value={pf}
                            accent="text-atlas-cyan"
                            sub={`gross ${fmtUsd(m.gross_profit_usd)} / ${fmtUsd(m.gross_loss_usd)}`}
                        />
                        <MetricTile
                            testid="metric-win-rate"
                            label="WIN RATE"
                            value={`${m.win_rate_pct}%`}
                            sub={`${m.winning_trades}W · ${m.losing_trades}L · ${m.closed_trades} closed`}
                        />
                        <MetricTile
                            testid="metric-net-pnl"
                            label="NET REALIZED P&L"
                            value={fmtUsd(m.net_pnl_usd, true)}
                            accent={netAccent}
                            sub={`max drawdown ${fmtUsd(m.max_drawdown_usd)}`}
                        />
                        <MetricTile
                            testid="metric-avg-win"
                            label="AVG WIN"
                            value={fmtUsd(m.avg_win_usd)}
                            accent="text-atlas-positive"
                        />
                        <MetricTile
                            testid="metric-avg-loss"
                            label="AVG LOSS"
                            value={fmtUsd(m.avg_loss_usd)}
                            accent="text-atlas-negative"
                        />
                        <MetricTile
                            testid="metric-asymmetry"
                            label="WIN/LOSS ASYMMETRY"
                            value={m.win_loss_asymmetry !== null && m.win_loss_asymmetry !== undefined ? `${m.win_loss_asymmetry.toFixed(2)}×` : "—"}
                        />
                        <MetricTile
                            testid="metric-friction"
                            label="TOTAL FRICTION"
                            value={fmtUsd(m.total_friction_usd)}
                            accent="text-atlas-warning"
                            sub={`fees ${fmtUsd(m.total_fees_usd)} · slippage ${fmtUsd(m.total_slippage_usd)}`}
                        />
                    </div>

                    {/* Volatility regime breakdown */}
                    <div className="panel mt-4" data-testid="analytics-regime-breakdown">
                        <div className="flex items-center gap-2 px-4 py-3 border-b border-atlas-border">
                            <Layers className="w-3.5 h-3.5 text-atlas-cyan" />
                            <span className="label-tag">VOLATILITY REGIME PERFORMANCE (ATR-14 AT ENTRY)</span>
                        </div>
                        {regimeKeys.length === 0 ? (
                            <div className="px-4 py-4 font-mono text-[11px] text-atlas-textSecondary">
                                No regime-tagged closed trades yet.
                            </div>
                        ) : (
                            <table className="w-full text-[12px] font-mono">
                                <thead>
                                    <tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest border-b border-atlas-border">
                                        <th className="text-left px-4 py-2 font-bold">Regime</th>
                                        <th className="text-right px-4 py-2 font-bold">Trades</th>
                                        <th className="text-right px-4 py-2 font-bold">Win Rate</th>
                                        <th className="text-right px-4 py-2 font-bold">Expectancy</th>
                                        <th className="text-right px-4 py-2 font-bold">Net P&L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {regimeKeys.map((k) => (
                                        <tr key={k} className="border-b border-atlas-border last:border-b-0" data-testid={`regime-row-${k}`}>
                                            <td className="px-4 py-2 text-white font-bold tracking-wider">{k}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{regimes[k].trades}</td>
                                            <td className="px-4 py-2 text-right tabular-nums">{regimes[k].win_rate_pct}%</td>
                                            <td className={`px-4 py-2 text-right tabular-nums ${
                                                regimes[k].expectancy_usd > 0 ? "text-atlas-positive" : regimes[k].expectancy_usd < 0 ? "text-atlas-negative" : "text-atlas-textSecondary"
                                            }`}>
                                                {fmtUsd(regimes[k].expectancy_usd, true)}
                                            </td>
                                            <td className={`px-4 py-2 text-right tabular-nums font-bold ${
                                                regimes[k].net_pnl_usd > 0 ? "text-atlas-positive" : regimes[k].net_pnl_usd < 0 ? "text-atlas-negative" : "text-atlas-textSecondary"
                                            }`}>
                                                {fmtUsd(regimes[k].net_pnl_usd, true)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </>
            )}
        </section>
    );
}
