import { ArrowRight } from "lucide-react";

// A single high-impact cockpit quadrant. Reads its face data from props (localized
// state store on the parent) so the face updates the instant a modal dismisses.
// `accent` maps to one of the tokenised colour families below.
const ACCENTS = {
    cyan: { text: "text-atlas-cyan", border: "border-atlas-cyan/30", bg: "bg-atlas-cyan/10", glow: "group-hover:shadow-[0_0_0_1px_rgba(20,224,201,0.4)]" },
    violet: { text: "text-violet-400", border: "border-violet-500/30", bg: "bg-violet-500/10", glow: "group-hover:shadow-[0_0_0_1px_rgba(167,139,250,0.4)]" },
    amber: { text: "text-atlas-warning", border: "border-atlas-warning/30", bg: "bg-atlas-warning/10", glow: "group-hover:shadow-[0_0_0_1px_rgba(245,180,60,0.4)]" },
    green: { text: "text-atlas-positive", border: "border-atlas-positive/30", bg: "bg-atlas-positive/10", glow: "group-hover:shadow-[0_0_0_1px_rgba(52,211,153,0.4)]" },
};

const DOT = { good: "bg-atlas-positive", warn: "bg-atlas-warning", bad: "bg-atlas-negative", muted: "bg-atlas-textTertiary" };

export default function QuadrantCard({
    testid, icon: Icon, accent = "cyan", title, subtitle,
    stats = [], rows = [], cta = "Open", onOpen, children,
}) {
    const a = ACCENTS[accent] || ACCENTS.cyan;
    return (
        <button
            data-testid={testid}
            onClick={onOpen}
            className={`group relative flex flex-col gap-4 text-left rounded-2xl border ${a.border} bg-atlas-panel/70 p-5 md:p-6 transition-all duration-200
                hover:-translate-y-0.5 hover:bg-atlas-panelHover hover:shadow-[0_16px_50px_-20px_rgba(0,0,0,0.95)] ${a.glow} focus:outline-none focus-visible:ring-1 focus-visible:ring-atlas-cyan`}
        >
            {/* header */}
            <div className="flex items-start gap-3">
                <div className={`w-11 h-11 shrink-0 rounded-xl grid place-items-center border ${a.border} ${a.bg}`}>
                    <Icon className={`w-5 h-5 ${a.text}`} strokeWidth={2} />
                </div>
                <div className="min-w-0">
                    <div className="font-heading font-medium text-lg md:text-xl text-atlas-text leading-tight truncate">{title}</div>
                    <div className="font-mono text-[10px] uppercase tracking-widest text-atlas-textTertiary mt-0.5">{subtitle}</div>
                </div>
            </div>

            {/* headline stats (max 2) */}
            {stats.length > 0 && (
                <div className={`grid ${stats.length > 1 ? "grid-cols-2" : "grid-cols-1"} gap-3`}>
                    {stats.map((st) => (
                        <div key={st.label} data-testid={st.testid} className="rounded-lg border border-atlas-border bg-atlas-panel px-3 py-2.5">
                            <div className="font-mono text-[9px] uppercase tracking-wider text-atlas-textTertiary truncate">{st.label}</div>
                            <div className="flex items-center gap-1.5 mt-0.5">
                                <span className={`font-heading font-bold text-lg md:text-2xl tabular-nums ${st.valueCls || a.text}`}>{st.value}</span>
                                {st.dot && <span className={`w-2 h-2 rounded-full ${DOT[st.dot] || DOT.muted}`} />}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* metric rows */}
            {rows.length > 0 && (
                <div className="space-y-1.5">
                    {rows.map((r) => {
                        const RIcon = r.icon;
                        return (
                            <div key={r.label} data-testid={r.testid} className="flex items-center justify-between gap-3 text-[12px]">
                                <span className="flex items-center gap-2 text-atlas-textSecondary font-mono min-w-0">
                                    {RIcon && <RIcon className="w-3.5 h-3.5 text-atlas-textTertiary shrink-0" strokeWidth={2} />}
                                    <span className="truncate">{r.label}</span>
                                </span>
                                <span className={`font-mono font-bold tabular-nums shrink-0 ${r.valueCls || "text-atlas-text"}`}>{r.value}</span>
                            </div>
                        );
                    })}
                </div>
            )}

            {children}

            {/* CTA */}
            <div className={`mt-auto flex items-center justify-between rounded-lg border ${a.border} bg-transparent px-4 py-2.5 font-mono text-xs font-bold tracking-wide ${a.text} transition-colors group-hover:${a.bg.replace("/10", "/15")}`}>
                <span>{cta}</span>
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </div>
        </button>
    );
}
