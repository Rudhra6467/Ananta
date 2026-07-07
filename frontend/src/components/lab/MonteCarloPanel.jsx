import { useState } from "react";
import { Layers, Play, Loader2, ShieldAlert, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";

const VERDICT_CLS = {
    ROBUST: "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10",
    ACCEPTABLE: "text-atlas-warning border-atlas-warning/40 bg-atlas-warning/10",
    FRAGILE: "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/10",
};

// Monte Carlo risk-of-ruin — bootstraps the realised P&L to show the distribution of
// outcomes, not just the single historical path. Credit-free (pure math on the backend).
export default function MonteCarloPanel({ onResult }) {
    const [iterations, setIterations] = useState(2000);
    const [ruin, setRuin] = useState(25);
    const [res, setRes] = useState(null);
    const [busy, setBusy] = useState(false);

    const run = async () => {
        setBusy(true);
        try {
            const r = await api.labMonteCarlo({ source: "live", iterations: Number(iterations), ruin_threshold_pct: Number(ruin) });
            setRes(r);
            onResult?.(r);
            if (!r.ok) toast.message("Not enough data", { description: r.reason });
        } catch (e) {
            toast.error("Monte Carlo failed", { description: String(e?.response?.data?.detail || e?.message) });
        } finally { setBusy(false); }
    };

    const maxCount = res?.ok ? Math.max(...res.histogram.map((h) => h.count), 1) : 1;

    return (
        <div className="panel border-atlas-border rounded-xl overflow-hidden" data-testid="monte-carlo-panel">
            <div className="px-4 py-3 border-b border-atlas-border flex items-center gap-2">
                <Layers className="w-4 h-4 text-violet-400" strokeWidth={2} />
                <span className="font-heading font-medium text-atlas-text">Monte Carlo · Risk of Ruin</span>
                <span className="font-mono text-[9px] uppercase tracking-widest text-atlas-textTertiary ml-1">bootstrapped from your closed trades</span>
            </div>

            <div className="p-4 space-y-4">
                <div className="flex flex-wrap items-end gap-3">
                    <div>
                        <label className="font-mono text-[10px] text-atlas-textTertiary">ITERATIONS</label>
                        <select data-testid="mc-iterations" value={iterations} onChange={(e) => setIterations(e.target.value)}
                            className="block mt-1 bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-xs text-atlas-text">
                            {[1000, 2000, 5000, 10000].map((n) => <option key={n} value={n}>{n.toLocaleString()}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="font-mono text-[10px] text-atlas-textTertiary">RUIN THRESHOLD (%)</label>
                        <select data-testid="mc-ruin" value={ruin} onChange={(e) => setRuin(e.target.value)}
                            className="block mt-1 bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-xs text-atlas-text">
                            {[10, 20, 25, 33, 50].map((n) => <option key={n} value={n}>-{n}%</option>)}
                        </select>
                    </div>
                    <Button data-testid="mc-run-btn" onClick={run} disabled={busy} className="gap-2">
                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} RUN SIMULATION
                    </Button>
                </div>

                {res && !res.ok && (
                    <div className="font-mono text-[11px] text-atlas-textSecondary py-2" data-testid="mc-empty">{res.reason} (have {res.sample_size}).</div>
                )}

                {res?.ok && (
                    <div className="space-y-4" data-testid="mc-result">
                        <div className="flex items-center gap-3 flex-wrap">
                            <span className={`font-mono text-xs font-bold px-2.5 py-1 rounded border ${VERDICT_CLS[res.verdict]}`} data-testid="mc-verdict">{res.verdict}</span>
                            <span className="font-mono text-[10px] text-atlas-textTertiary">{res.iterations.toLocaleString()} paths · {res.sample_size} trades · floor ${res.ruin_floor}</span>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <Stat testid="mc-ror" icon={ShieldAlert} label="Risk of Ruin" value={`${res.risk_of_ruin_pct}%`} good={res.risk_of_ruin_pct <= 5} />
                            <Stat testid="mc-profit" icon={TrendingUp} label="Prob. of Profit" value={`${res.prob_profit_pct}%`} good={res.prob_profit_pct >= 60} />
                            <Stat testid="mc-median" label="Median Return" value={`${res.final_return_pct.median}%`} good={res.final_return_pct.median > 0} />
                            <Stat testid="mc-dd" label="Median Max DD" value={`${res.max_drawdown_pct.median}%`} good={res.max_drawdown_pct.median <= 10} />
                        </div>
                        {/* percentile band */}
                        <div>
                            <div className="label-tag mb-1.5">FINAL RETURN DISTRIBUTION (P5 → P95)</div>
                            <div className="grid grid-cols-5 gap-2 font-mono text-center">
                                {[["p5", "P5"], ["p25", "P25"], ["median", "P50"], ["p75", "P75"], ["p95", "P95"]].map(([k, lbl]) => (
                                    <div key={k} className="rounded-lg border border-atlas-border py-2">
                                        <div className="text-[8px] text-atlas-textTertiary">{lbl}</div>
                                        <div className={`text-xs font-bold ${res.final_return_pct[k] >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{res.final_return_pct[k]}%</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        {/* histogram */}
                        <div>
                            <div className="label-tag mb-1.5">OUTCOME HISTOGRAM</div>
                            <div className="flex items-end gap-1 h-24" data-testid="mc-histogram">
                                {res.histogram.map((h, i) => (
                                    <div key={i} className="flex-1 flex flex-col items-center justify-end" title={`${h.lo}%–${h.hi}% : ${h.count}`}>
                                        <div className={`w-full rounded-t ${h.hi <= 0 ? "bg-atlas-negative/60" : "bg-atlas-positive/60"}`}
                                            style={{ height: `${Math.max(2, (h.count / maxCount) * 100)}%` }} />
                                    </div>
                                ))}
                            </div>
                            <div className="flex justify-between font-mono text-[8px] text-atlas-textTertiary mt-1">
                                <span>{res.histogram[0]?.lo}%</span>
                                <span>{res.histogram[res.histogram.length - 1]?.hi}%</span>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

function Stat({ testid, icon: Icon, label, value, good }) {
    return (
        <div className="rounded-lg border border-atlas-border bg-atlas-panel px-3 py-2.5" data-testid={testid}>
            <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wider text-atlas-textTertiary">
                {Icon && <Icon className="w-3 h-3" />}{label}
            </div>
            <div className={`font-heading font-bold text-lg tabular-nums mt-0.5 ${good ? "text-atlas-positive" : "text-atlas-negative"}`}>{value}</div>
        </div>
    );
}
