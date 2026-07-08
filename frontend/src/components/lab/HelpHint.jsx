import { useState, useRef, useEffect } from "react";
import { Info } from "lucide-react";

// Minimalist contextual help — a small circled (i) that pops a lightweight, non-blocking
// floating card beside the control (Notion / Stripe / Linear style). Click-away closes it.
export default function HelpHint({ text, title, className = "", side = "top" }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        if (!open) return;
        const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener("mousedown", onDoc);
        document.addEventListener("touchstart", onDoc);
        return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("touchstart", onDoc); };
    }, [open]);

    if (!text) return null;
    const pos = side === "bottom" ? "top-full mt-2" : "bottom-full mb-2";

    return (
        <span ref={ref} className={`relative inline-flex ${className}`}>
            <button type="button" data-testid="help-hint-trigger" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
                className="text-atlas-textTertiary hover:text-atlas-cyan transition-colors" aria-label="Help">
                <Info className="w-3.5 h-3.5" />
            </button>
            {open && (
                <span data-testid="help-hint-card"
                    className={`absolute ${pos} left-1/2 -translate-x-1/2 z-50 w-56 rounded-lg border border-atlas-border bg-atlas-panel shadow-[0_12px_40px_-12px_rgba(0,0,0,0.9)] p-3 help-fade`}>
                    {title && <span className="block font-mono text-[10px] font-bold text-atlas-text mb-1">{title}</span>}
                    <span className="block font-mono text-[10px] leading-relaxed text-atlas-textSecondary">{text}</span>
                </span>
            )}
        </span>
    );
}
