/** Shared AI reasoning timeline component used by both the operator AIReasoning page
 *  and the Judge View read-only mode.
 */
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

const BIAS_STYLE = {
    BULLISH: { text: "text-atlas-positive", bg: "bg-atlas-positive/10", border: "border-atlas-positive/40" },
    BEARISH: { text: "text-atlas-negative", bg: "bg-atlas-negative/10", border: "border-atlas-negative/40" },
    NEUTRAL: { text: "text-atlas-warning", bg: "bg-atlas-warning/10", border: "border-atlas-warning/40" },
};

const DECISION_STYLE = {
    BUY: "text-atlas-positive border-atlas-positive/40",
    SELL: "text-atlas-negative border-atlas-negative/40",
    HOLD: "text-atlas-textSecondary border-atlas-border",
    BLOCKED: "text-atlas-negative border-atlas-negative/60 bg-atlas-negative/5",
};

export default function ReasoningTimeline({ items }) {
    const [open, setOpen] = useState({});
    const toggle = (id) => setOpen((s) => ({ ...s, [id]: !s[id] }));

    if (!items || items.length === 0) {
        return (
            <div className="panel p-8 text-center font-mono text-[11px] text-atlas-textSecondary" data-testid="reasoning-empty">
                <span className="blink-cursor">AWAITING FIRST EVALUATION CYCLE</span>
            </div>
        );
    }

    return (
        <div className="panel" data-testid="ai-reasoning-timeline">
            <ol className="relative">
                {items.map((r, idx) => {
                    const biasStyle = BIAS_STYLE[r.bias] || BIAS_STYLE.NEUTRAL;
                    const decisionCls = DECISION_STYLE[r.decision] || DECISION_STYLE.HOLD;
                    const isOpen = open[r.id];
                    return (
                        <li
                            key={r.id || idx}
                            className={`border-b border-atlas-border last:border-b-0 transition-colors ${
                                isOpen ? "bg-atlas-panelHover" : ""
                            }`}
                            data-testid={`reasoning-entry-${idx}`}
                        >
                            <button
                                type="button"
                                onClick={() => toggle(r.id || idx)}
                                className="w-full px-4 py-3 flex items-center gap-4 text-left hover:bg-atlas-panelHover transition-colors"
                                data-testid={`reasoning-entry-toggle-${idx}`}
                            >
                                <div className="flex items-center gap-3 min-w-0 flex-1">
                                    {isOpen ? (
                                        <ChevronDown className="w-3.5 h-3.5 text-atlas-textSecondary flex-shrink-0" />
                                    ) : (
                                        <ChevronRight className="w-3.5 h-3.5 text-atlas-textSecondary flex-shrink-0" />
                                    )}
                                    <div className="font-mono text-[10px] text-atlas-textTertiary w-28 flex-shrink-0">
                                        {new Date(r.timestamp).toLocaleTimeString(undefined, { hour12: false })}
                                    </div>
                                    <div className="font-mono text-[11px] font-bold text-white w-20 flex-shrink-0">
                                        {r.symbol}
                                    </div>
                                    <div
                                        className={`px-2 py-0.5 border font-mono text-[10px] tracking-widest font-bold flex-shrink-0 ${biasStyle.text} ${biasStyle.border} ${biasStyle.bg}`}
                                    >
                                        {r.bias}
                                    </div>
                                    <div className="font-mono text-[11px] text-atlas-cyan tabular-nums flex-shrink-0">
                                        {Number(r.confidence).toFixed(2)}
                                    </div>
                                    <div
                                        className={`px-2 py-0.5 border font-mono text-[10px] tracking-widest font-bold flex-shrink-0 ${decisionCls}`}
                                    >
                                        {r.decision}
                                    </div>
                                    <div className="font-mono text-[11px] text-atlas-textSecondary truncate hidden md:block">
                                        {r.reason}
                                    </div>
                                </div>
                            </button>
                            {isOpen && <DetailPanel reasoning={r} />}
                        </li>
                    );
                })}
            </ol>
        </div>
    );
}

function DetailPanel({ reasoning }) {
    const e = reasoning.evidence || {};
    return (
        <div className="px-4 pb-4 pt-1 grid grid-cols-1 lg:grid-cols-3 gap-4" data-testid="reasoning-detail-panel">
            <div className="lg:col-span-2 border border-atlas-border p-4 bg-atlas-bg">
                <div className="label-tag mb-2">LLM OUTPUT · {reasoning.model}</div>
                <div className="font-mono text-[12px] text-white leading-relaxed whitespace-pre-wrap">
                    {reasoning.reason}
                </div>
                <div className="mt-4 label-tag">FUSION SUMMARY</div>
                <div className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed mt-1">
                    {e.fusion_summary || "—"}
                </div>
                {reasoning.blocked_reasons && reasoning.blocked_reasons.length > 0 && (
                    <>
                        <div className="mt-4 label-tag text-atlas-negative">BLOCKED REASONS</div>
                        <ul className="mt-1 space-y-0.5">
                            {reasoning.blocked_reasons.map((b) => (
                                <li key={b} className="font-mono text-[11px] text-atlas-negative">
                                    · {b}
                                </li>
                            ))}
                        </ul>
                    </>
                )}
                <div className="mt-4 label-tag">NEWS / MACRO INPUT</div>
                <div className="font-mono text-[11px] text-atlas-textTertiary leading-relaxed mt-1 italic">
                    "{reasoning.news_summary}"
                </div>
            </div>
            <div className="border border-atlas-border p-4 bg-atlas-bg">
                <div className="label-tag mb-3">EVIDENCE SNAPSHOT</div>
                <EvidenceRow k="PRICE" v={`$${(e.price ?? 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}`} />
                <EvidenceRow k="BID / ASK" v={`$${(e.bid ?? 0).toFixed(4)} / $${(e.ask ?? 0).toFixed(4)}`} />
                <EvidenceRow k="SPREAD" v={`${(e.spread_pct ?? 0).toFixed(3)}%`} />
                <EvidenceRow
                    k="OB IMBALANCE"
                    v={`${(e.orderbook_imbalance ?? 0) >= 0 ? "+" : ""}${(e.orderbook_imbalance ?? 0).toFixed(3)}`}
                />
                <EvidenceRow k="EXCHANGE" v={(e.exchange || "").toUpperCase()} />
                <div className="my-3 h-px bg-atlas-border" />
                <div className="label-tag mb-2">KILL-SWITCH STATE</div>
                {e.kill_switch_details &&
                    Object.entries(e.kill_switch_details).map(([k, v]) => (
                        <EvidenceRow key={k} k={k.toUpperCase()} v={String(v)} />
                    ))}
            </div>
        </div>
    );
}

function EvidenceRow({ k, v }) {
    return (
        <div className="flex items-center justify-between font-mono text-[10px] py-1 border-b border-atlas-border/60 last:border-b-0">
            <span className="text-atlas-textSecondary">{k}</span>
            <span className="text-white tabular-nums">{v}</span>
        </div>
    );
}
