import { useState } from "react";
import { Download, FileDown } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/lib/api";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";

const iso = (d) => d.toISOString().slice(0, 10);

/**
 * Top-right header control: a compact PDF button that opens a small popup
 * asking for an optional FROM / TO date range (with quick presets) and then
 * downloads the chronological Trade-History PDF (win/loss rate + trades).
 */
export default function TradeHistoryPdfDialog() {
    const [open, setOpen] = useState(false);
    const [start, setStart] = useState("");
    const [end, setEnd] = useState("");

    const applyPreset = (days) => {
        if (days === null) {
            setStart("");
            setEnd("");
            return;
        }
        const to = new Date();
        const from = new Date();
        from.setDate(from.getDate() - days);
        setStart(iso(from));
        setEnd(iso(to));
    };

    const exportPdf = () => {
        if (start && end && start > end) {
            toast.error("INVALID RANGE", { description: "Start date is after end date." });
            return;
        }
        const params = new URLSearchParams();
        if (start) params.set("start", start);
        if (end) params.set("end", end);
        const qs = params.toString();
        window.open(`${API}/report/trades.pdf${qs ? `?${qs}` : ""}`, "_blank");
        toast.success("PDF DOWNLOAD STARTED", {
            description: start || end ? `Range ${start || "…"} → ${end || "now"}` : "All executed trades",
        });
        setOpen(false);
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <button
                    data-testid="header-pdf-button"
                    className="flex items-center gap-1.5 font-mono text-[10px] tracking-widest font-bold px-2.5 py-2 border border-atlas-border hover:border-atlas-cyan hover:text-atlas-cyan text-atlas-textSecondary transition-colors"
                    title="Download trade-history PDF"
                >
                    <Download className="w-4 h-4" />
                    <span className="hidden sm:inline">PDF</span>
                </button>
            </DialogTrigger>
            <DialogContent
                className="bg-atlas-panel border border-atlas-border text-white max-w-md"
                data-testid="trade-pdf-dialog"
            >
                <DialogHeader>
                    <DialogTitle className="font-heading text-lg flex items-center gap-2">
                        <FileDown className="w-4 h-4 text-atlas-cyan" />
                        Export Trade History
                    </DialogTitle>
                    <DialogDescription className="font-mono text-[11px] text-atlas-textSecondary">
                        Chronological PDF of executed trades with win/loss rate and net P&amp;L. Pick a range or leave blank for all-time.
                    </DialogDescription>
                </DialogHeader>

                <div className="flex flex-wrap gap-2" data-testid="pdf-presets">
                    {[
                        { label: "LAST 7 DAYS", days: 7 },
                        { label: "LAST 30 DAYS", days: 30 },
                        { label: "ALL TIME", days: null },
                    ].map((p) => (
                        <button
                            key={p.label}
                            type="button"
                            data-testid={`pdf-preset-${p.days ?? "all"}`}
                            onClick={() => applyPreset(p.days)}
                            className="font-mono text-[10px] tracking-widest font-bold px-3 py-1.5 border border-atlas-border text-atlas-textSecondary hover:border-atlas-cyan hover:text-atlas-cyan transition-colors"
                        >
                            {p.label}
                        </button>
                    ))}
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <div className="label-tag mb-1">FROM</div>
                        <input
                            type="date"
                            data-testid="pdf-start-date"
                            value={start}
                            max={end || undefined}
                            onChange={(e) => setStart(e.target.value)}
                            className="w-full bg-atlas-bg border border-atlas-border text-white font-mono text-[12px] px-3 py-2 focus:border-atlas-cyan outline-none"
                        />
                    </div>
                    <div>
                        <div className="label-tag mb-1">TO</div>
                        <input
                            type="date"
                            data-testid="pdf-end-date"
                            value={end}
                            min={start || undefined}
                            onChange={(e) => setEnd(e.target.value)}
                            className="w-full bg-atlas-bg border border-atlas-border text-white font-mono text-[12px] px-3 py-2 focus:border-atlas-cyan outline-none"
                        />
                    </div>
                </div>

                <DialogFooter>
                    <button
                        type="button"
                        data-testid="pdf-export-confirm"
                        onClick={exportPdf}
                        className="w-full flex items-center justify-center gap-2 font-mono text-[11px] tracking-widest font-bold px-4 py-2.5 bg-atlas-cyan text-atlas-bg hover:bg-cyan-400 transition-colors"
                    >
                        <Download className="w-4 h-4" />
                        EXPORT PDF
                    </button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
