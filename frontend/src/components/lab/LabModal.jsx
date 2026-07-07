import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const ACCENTS = {
    cyan: { text: "text-atlas-cyan", border: "border-atlas-cyan/30", bg: "bg-atlas-cyan/10" },
    violet: { text: "text-violet-400", border: "border-violet-500/30", bg: "bg-violet-500/10" },
    amber: { text: "text-atlas-warning", border: "border-atlas-warning/30", bg: "bg-atlas-warning/10" },
    green: { text: "text-atlas-positive", border: "border-atlas-positive/30", bg: "bg-atlas-positive/10" },
};

// Full-screen sub-page overlay pushed by a quadrant. Sticky header + scrollable body
// + optional sticky footer (e.g. a Save bar). Dismisses instantly back to the grid.
export default function LabModal({ open, onOpenChange, icon: Icon, accent = "cyan", title, subtitle, children, footer, testid }) {
    const a = ACCENTS[accent] || ACCENTS.cyan;
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent
                data-testid={testid}
                className="bg-atlas-bg border-atlas-border p-0 gap-0 w-[96vw] max-w-4xl h-[90vh] flex flex-col overflow-hidden rounded-2xl"
            >
                <DialogHeader className="shrink-0 border-b border-atlas-border px-5 md:px-6 py-4 space-y-0 text-left">
                    <div className="flex items-center gap-3">
                        {Icon && (
                            <div className={`w-10 h-10 shrink-0 rounded-xl grid place-items-center border ${a.border} ${a.bg}`}>
                                <Icon className={`w-5 h-5 ${a.text}`} strokeWidth={2} />
                            </div>
                        )}
                        <div>
                            <DialogTitle className="font-heading font-medium text-lg md:text-xl text-atlas-text leading-tight">{title}</DialogTitle>
                            <DialogDescription className="font-mono text-[10px] uppercase tracking-widest text-atlas-textTertiary mt-0.5">
                                {subtitle}
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto atlas-scroll px-4 md:px-6 py-4 space-y-4">
                    {children}
                </div>

                {footer && (
                    <div className="shrink-0 border-t border-atlas-border px-4 md:px-6 py-3 bg-atlas-panel/60">
                        {footer}
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
