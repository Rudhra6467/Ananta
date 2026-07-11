import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";
import { useAccessGate } from "@/context/AccessGateContext";

/**
 * Clickable metric explainer — tap the (i) to see what a metric means, its quality
 * bands, and where the current value lands. Educates beginners inline (Stripe/Linear style).
 */
const METRICS = {
    health: {
        title: "Strategy Health",
        desc: "A single 0–100 score = the average of six sub-metrics (win rate, risk, consistency, recent form, sample size, rating). One number to gauge overall quality.",
        unit: "",
        bands: [{ to: 35, label: "At risk", cls: "text-atlas-negative" }, { to: 60, label: "Needs work", cls: "text-atlas-warning" }, { to: 101, label: "Healthy", cls: "text-atlas-positive" }],
    },
    win_rate: {
        title: "Win Rate",
        desc: "Percentage of closed trades that were profitable. High win rate alone doesn't guarantee profit — pair it with profit factor.",
        unit: "%",
        bands: [{ to: 40, label: "Low", cls: "text-atlas-negative" }, { to: 55, label: "Fair", cls: "text-atlas-warning" }, { to: 101, label: "Strong", cls: "text-atlas-positive" }],
    },
    profit_factor: {
        title: "Profit Factor",
        desc: "How much your winners generate vs your losers (gross profit ÷ gross loss). Below 1.0 loses money; above 2.0 is excellent.",
        unit: "",
        bands: [{ to: 1.0, label: "Losing", cls: "text-atlas-negative" }, { to: 1.5, label: "Marginal", cls: "text-atlas-warning" }, { to: 2.0, label: "Good", cls: "text-atlas-positive" }, { to: 999, label: "Excellent", cls: "text-atlas-positive" }],
    },
    roi: {
        title: "Return on Investment",
        desc: "Net profit as a % of capital deployed by this strategy. Positive means the strategy is net profitable over its sample.",
        unit: "%",
        bands: [{ to: 0, label: "Negative", cls: "text-atlas-negative" }, { to: 5, label: "Modest", cls: "text-atlas-warning" }, { to: 999, label: "Strong", cls: "text-atlas-positive" }],
    },
};

export default function MetricExplainer({ metric, value, className = "", side = "top" }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    const { gate } = useAccessGate();
    const m = METRICS[metric];

    useEffect(() => {
        if (!open) return;
        const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener("mousedown", onDoc);
        document.addEventListener("touchstart", onDoc);
        return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("touchstart", onDoc); };
    }, [open]);

    if (!m) return null;
    const pos = side === "bottom" ? "top-full mt-2" : "bottom-full mb-2";
    const numeric = typeof value === "number" ? value : null;
    const band = numeric != null ? m.bands.find((b) => numeric < b.to) || m.bands[m.bands.length - 1] : null;

    return (
        <span ref={ref} className={`relative inline-flex ${className}`}>
            <button type="button" data-testid={`metric-explainer-${metric}`} onClick={(e) => { e.stopPropagation(); if (gate("Detailed metric explanations")) setOpen((v) => !v); }}
                className="text-atlas-textTertiary hover:text-atlas-cyan transition-colors" aria-label={`What is ${m.title}?`}>
                <Info className="w-3.5 h-3.5" />
            </button>
            {open && (
                <span data-testid={`metric-explainer-card-${metric}`}
                    className={`absolute ${pos} left-1/2 -translate-x-1/2 z-50 w-64 rounded-lg border border-atlas-border bg-atlas-panel shadow-[0_12px_40px_-12px_rgba(0,0,0,0.9)] p-3 help-fade text-left`}>
                    <span className="block font-mono text-[11px] font-bold text-atlas-text mb-1">{m.title}</span>
                    <span className="block font-mono text-[10px] leading-relaxed text-atlas-textSecondary mb-2">{m.desc}</span>
                    <span className="block space-y-0.5">
                        {m.bands.map((b, i) => {
                            const prev = i === 0 ? null : m.bands[i - 1].to;
                            const range = prev == null ? `< ${b.to}${m.unit}` : b.to >= 999 ? `≥ ${prev}${m.unit}` : `${prev}–${b.to}${m.unit}`;
                            return (
                                <span key={b.label} className={`flex items-center justify-between font-mono text-[9px] ${band === b ? "font-bold" : "opacity-70"} ${b.cls}`}>
                                    <span>{b.label}</span><span className="tabular-nums">{range}</span>
                                </span>
                            );
                        })}
                    </span>
                    {numeric != null && band && (
                        <span className="block mt-2 pt-2 border-t border-atlas-border font-mono text-[10px] text-atlas-textSecondary">
                            Your value <span className={`font-bold ${band.cls}`}>{numeric}{m.unit} · {band.label}</span>
                        </span>
                    )}
                </span>
            )}
        </span>
    );
}
