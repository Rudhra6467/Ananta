import { useState } from "react";
import { ChevronDown } from "lucide-react";

/**
 * CollapsibleSection — an in-place expand/collapse panel (no dialog/modal).
 * Native <details> with a shared `name` = single-open accordion (only one open per group).
 * `open` is React-controlled (synced via onToggle) so background data-polling re-renders never
 * fight the user, and children are mounted ONLY when open — this guarantees charts/graphs
 * measure a real width on expand (fixes blank/stalled charts inside a collapsed section).
 */
export function CollapsibleSection({
    groupName = "rl-accordion",
    label,
    title,
    subtitle,
    right,
    testId,
    className = "",
    defaultOpen = false,
    children,
}) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <details
            name={groupName}
            open={open}
            onToggle={(e) => setOpen(e.currentTarget.open)}
            className={`panel group ${className}`}
            data-testid={testId}
        >
            <summary
                data-testid={testId ? `${testId}-toggle` : undefined}
                className="list-none cursor-pointer select-none px-5 pt-4 pb-3 flex items-center justify-between gap-3 hover:bg-atlas-panelHover transition-colors group-open:border-b group-open:border-atlas-border [&::-webkit-details-marker]:hidden"
            >
                <div className="min-w-0">
                    {label && <div className="label-tag">{label}</div>}
                    <h3 className={`font-heading text-xl font-bold ${label ? "mt-1" : ""}`}>{title}</h3>
                    {subtitle && (
                        <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-0.5">
                            {subtitle}
                        </div>
                    )}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                    {right}
                    <ChevronDown className="w-4 h-4 text-atlas-textTertiary transition-transform group-open:rotate-180" />
                </div>
            </summary>
            {open && <div>{children}</div>}
        </details>
    );
}

export default CollapsibleSection;
