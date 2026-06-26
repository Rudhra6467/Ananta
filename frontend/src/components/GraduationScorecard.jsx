import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, ShieldCheck, Gauge } from "lucide-react";
import api from "@/lib/api";

function Metric({ label, value }) {
    return (
        <div className="border border-atlas-border p-3">
            <div className="label-tag">{label}</div>
            <div className="font-mono text-sm font-bold mt-1 tabular-nums">{value}</div>
        </div>
    );
}

/**
 * 10-gate paper -> live graduation scorecard. Proves the system has a
 * repeatable edge that survives fees, slippage and different regimes — NOT
 * mere profitability. Reads GET /api/analytics/graduation.
 */
export default function GraduationScorecard() {
    const [g, setG] = useState(null);
    const [error, setError] = useState(false);

    useEffect(() => {
        let alive = true;
        const load = () =>
            api
                .analyticsGraduation()
                .then((d) => {
                    if (alive) {
                        setG(d);
                        setError(false);
                    }
                })
                .catch(() => {
                    if (alive) setError(true);
                });
        load();
        const t = setInterval(load, 20000);
        return () => {
            alive = false;
            clearInterval(t);
        };
    }, []);

    if (!g) {
        return (
            <section className="panel p-5" data-testid="graduation-scorecard">
                <div className="label-tag">GRADUATION READINESS</div>
                <div className="font-mono text-xs text-atlas-textTertiary mt-2" data-testid="graduation-status">
                    {error ? "Could not load scorecard — retrying…" : "Loading scorecard…"}
                </div>
            </section>
        );
    }

    const ready = g.all_passed;
    const m = g.metrics || {};

    return (
        <section className="panel" data-testid="graduation-scorecard">
            <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-atlas-border">
                <div>
                    <div className="label-tag flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-atlas-cyan" />
                        GRADUATION READINESS · PAPER → $300 LIVE
                    </div>
                    <p className="text-atlas-textSecondary text-xs mt-1 max-w-xl">
                        Proves a repeatable edge that survives fees, slippage and different market regimes — not just profit. All 10 gates must pass before any live capital.
                    </p>
                </div>
                <div
                    data-testid="graduation-verdict"
                    className={`shrink-0 font-mono text-sm font-bold px-4 py-2 border ${
                        ready
                            ? "text-atlas-positive border-atlas-positive/50 bg-atlas-positive/10"
                            : "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/5"
                    }`}
                >
                    {g.headline}
                </div>
            </div>

            <div className="p-5 space-y-5">
                {/* gates checklist */}
                <div className="space-y-2" data-testid="graduation-criteria">
                    {g.criteria.map((c) => (
                        <div
                            key={c.id}
                            data-testid={`gate-${c.id}`}
                            className="flex items-start gap-3 border border-atlas-border px-3 py-2.5"
                        >
                            {c.passed ? (
                                <CheckCircle2 className="w-4 h-4 text-atlas-positive shrink-0 mt-0.5" />
                            ) : (
                                <XCircle className="w-4 h-4 text-atlas-negative shrink-0 mt-0.5" />
                            )}
                            <div className="flex-1 min-w-0">
                                <div className="font-mono text-xs font-bold text-white">{c.label}</div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">
                                    target {c.target}
                                </div>
                            </div>
                            <div
                                className={`font-mono text-[11px] font-bold text-right shrink-0 ${
                                    c.passed ? "text-atlas-positive" : "text-atlas-negative"
                                }`}
                            >
                                {c.actual}
                            </div>
                        </div>
                    ))}
                </div>

                {/* transparent supporting metrics */}
                <div>
                    <div className="label-tag flex items-center gap-1.5 mb-2">
                        <Gauge className="w-3.5 h-3.5" />
                        SUPPORTING METRICS
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="graduation-metrics">
                        <Metric label="CLOSED TRADES" value={m.closed_trades ?? 0} />
                        <Metric label="EXPECTANCY / TRADE" value={`$${(m.expectancy_usd ?? 0).toFixed(2)}`} />
                        <Metric label="PROFIT FACTOR" value={m.profit_factor != null ? m.profit_factor.toFixed(2) : "n/a"} />
                        <Metric label="MAX DRAWDOWN" value={`${(m.max_drawdown_pct ?? 0).toFixed(1)}%`} />
                        <Metric label="STOP-LOSS FREQUENCY" value={`${(m.stop_loss_frequency_pct ?? 0).toFixed(0)}%`} />
                        <Metric
                            label="TRAIL-EXIT QUALITY"
                            value={`${m.trail_exit_count ?? 0} exits · ${(m.trail_exit_win_pct ?? 0).toFixed(0)}% win`}
                        />
                        <Metric
                            label="FRICTION (FEES+SLIP)"
                            value={`$${(m.total_friction_usd ?? 0).toFixed(2)}${
                                m.friction_pct_of_gross != null ? ` · ${m.friction_pct_of_gross.toFixed(0)}%` : ""
                            }`}
                        />
                        <Metric
                            label="AVG ENTRY EXTENSION"
                            value={
                                m.avg_entry_extension_pct != null
                                    ? `${m.avg_entry_extension_pct.toFixed(1)}% (max ${(m.max_entry_extension_pct ?? 0).toFixed(1)}%)`
                                    : "—"
                            }
                        />
                        <Metric label="OBSERVATION WINDOW" value={`${(m.observation_days ?? 0).toFixed(0)} days`} />
                    </div>
                    <p className="font-mono text-[10px] text-atlas-textTertiary mt-2">
                        Entry Extension = how far above the 4h EMA50 price sat at entry. High values = chasing extended moves (worse risk). Watch this stays low.
                    </p>
                </div>
            </div>
        </section>
    );
}
