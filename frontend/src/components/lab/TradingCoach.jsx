import { useState } from "react";
import { Sparkles, Loader2, TrendingUp, TrendingDown, AlertTriangle, Check, Zap } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * Weekly Review — one-click 7-day AI performance review with an applyable tweak.
 * Header/tagline live in the parent AnalysisSection; this renders only the button + results.
 */
export default function TradingCoach({ isOwner }) {
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
        <div data-testid="trading-coach">
            {!review ? (
                <button data-testid="coach-generate-btn" onClick={generate} disabled={loading || !isOwner}
                    className="w-full flex items-center justify-center gap-2 rounded-xl bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-5 py-3.5 transition-colors disabled:opacity-40">
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                    {loading ? "REVIEWING…" : "GENERATE WEEKLY REVIEW"}
                </button>
            ) : (
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

                    <button data-testid="coach-regenerate-btn" onClick={generate} disabled={loading}
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
