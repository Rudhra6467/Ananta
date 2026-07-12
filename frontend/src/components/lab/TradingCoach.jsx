import { useState } from "react";
import { Sparkles, Loader2, TrendingUp, TrendingDown, AlertTriangle, Check, Zap } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Switch } from "@/components/ui/switch";

/**
 * AI Trading Coach — proactive weekly review with a one-click applyable tweak.
 * Gated by a visible AI credits switch (owner-only, consumes LLM credits).
 */
export default function TradingCoach({ isOwner }) {
    const [aiOn, setAiOn] = useState(false);
    const [loading, setLoading] = useState(false);
    const [review, setReview] = useState(null);
    const [applied, setApplied] = useState(false);

    const generate = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setLoading(true); setApplied(false);
        try {
            const r = await api.coachReview();
            setReview(r);
        } catch (e) {
            toast.error("Coach unavailable", { description: String(e?.response?.data?.detail || e?.message) });
        } finally { setLoading(false); }
    };

    const apply = async () => {
        const rec = review?.recommendation;
        if (!rec?.applyable) return;
        try {
            await api.coachApply(rec.setting_key, rec.suggested_value);
            setApplied(true);
            toast.success("Applied", { description: `${rec.setting_key} → ${rec.suggested_value}` });
        } catch (e) {
            toast.error("Apply failed", { description: String(e?.response?.data?.detail || e?.message) });
        }
    };

    const rec = review?.recommendation;
    return (
        <div className="panel border-atlas-border rounded-2xl p-5" data-testid="trading-coach">
            <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
                <div className="flex items-center gap-2.5">
                    <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-cyan/40 bg-atlas-cyan/10"><Sparkles className="w-4.5 h-4.5 text-atlas-cyan" /></span>
                    <div>
                        <div className="font-heading text-lg text-atlas-text leading-none">AI Trading Coach</div>
                        <div className="label-tag mt-1 text-[9px] text-atlas-textTertiary">Weekly review · continuous improvement</div>
                    </div>
                </div>
                <label className="flex items-center gap-2 cursor-pointer" title="Uses LLM credits when on">
                    <span className="font-mono text-[10px] text-atlas-textSecondary uppercase tracking-widest">AI · uses credits</span>
                    <Switch data-testid="coach-ai-switch" checked={aiOn} onCheckedChange={setAiOn} disabled={!isOwner} />
                </label>
            </div>

            {!review && (
                <div className="flex flex-col items-center text-center gap-3 py-6">
                    <p className="font-mono text-[11px] text-atlas-textSecondary max-w-md">
                        Get a 7 day performance review
                    </p>
                    <button data-testid="coach-generate-btn" onClick={generate} disabled={!aiOn || loading || !isOwner}
                        className="flex items-center gap-2 rounded-xl bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-5 py-2.5 transition-colors disabled:opacity-40">
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                        {loading ? "REVIEWING…" : "GENERATE WEEKLY REVIEW"}
                    </button>
                    {!aiOn && <span className="font-mono text-[9px] text-atlas-warning">Enable the AI switch to run (consumes credits)</span>}
                </div>
            )}

            {review && (
                <div className="space-y-4" data-testid="coach-review">
                    <p className="font-mono text-[12px] text-atlas-text leading-relaxed">{review.summary}</p>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <Chip icon={TrendingUp} label="Best" value={review.best_strategy} cls="text-atlas-positive" />
                        <Chip icon={TrendingDown} label="Worst" value={review.worst_strategy} cls="text-atlas-negative" />
                        <Chip icon={AlertTriangle} label="Confidence" value={`${review.confidence}%`} cls="text-atlas-warning" />
                    </div>

                    <div className="panel border-atlas-border rounded-xl p-4">
                        <div className="label-tag mb-1.5 text-atlas-warning">MOST COMMON MISTAKE</div>
                        <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">{review.common_mistake}</p>
                    </div>

                    {rec?.title && (
                        <div className="panel border-atlas-cyan/30 bg-atlas-cyan/5 rounded-xl p-4" data-testid="coach-recommendation">
                            <div className="label-tag mb-1.5 text-atlas-cyan">RECOMMENDATION</div>
                            <div className="font-heading text-sm text-atlas-text mb-1">{rec.title}</div>
                            <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">{rec.detail}</p>
                            {review.estimated_impact && (
                                <div className="mt-2 font-mono text-[10px] text-atlas-positive">Estimated impact: {review.estimated_impact}</div>
                            )}
                            {rec.applyable && (
                                <div className="flex items-center justify-between gap-3 mt-3 pt-3 border-t border-atlas-border flex-wrap">
                                    <div className="font-mono text-[11px] text-atlas-text">
                                        <span className="text-atlas-textTertiary">{rec.setting_key}</span>{" "}
                                        <span className="text-atlas-textSecondary tabular-nums">{rec.current_value}</span>
                                        <span className="text-atlas-textTertiary mx-1.5">→</span>
                                        <span className="text-atlas-cyan font-bold tabular-nums">{rec.suggested_value}</span>
                                    </div>
                                    <button data-testid="coach-apply-btn" onClick={apply} disabled={applied || !isOwner}
                                        className="flex items-center gap-2 rounded-lg bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[10px] tracking-widest font-bold px-4 py-2 transition-colors disabled:opacity-50">
                                        {applied ? <Check className="w-3.5 h-3.5" /> : <Zap className="w-3.5 h-3.5" />}{applied ? "APPLIED" : "APPLY CHANGE"}
                                    </button>
                                </div>
                            )}
                        </div>
                    )}

                    <button data-testid="coach-regenerate-btn" onClick={generate} disabled={loading || !aiOn}
                        className="font-mono text-[10px] tracking-widest text-atlas-textTertiary hover:text-atlas-text transition-colors disabled:opacity-40">
                        {loading ? "REVIEWING…" : "↻ REGENERATE"}
                    </button>
                </div>
            )}
        </div>
    );
}

function Chip({ icon: Icon, label, value, cls }) {
    return (
        <div className="panel border-atlas-border rounded-lg px-3 py-2.5 flex items-center gap-2">
            <Icon className={`w-4 h-4 ${cls}`} />
            <div>
                <div className="font-mono text-[9px] text-atlas-textTertiary uppercase tracking-widest">{label}</div>
                <div className={`font-heading text-sm capitalize ${cls}`}>{value || "—"}</div>
            </div>
        </div>
    );
}
