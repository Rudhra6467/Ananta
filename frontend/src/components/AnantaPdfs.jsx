import { useState, useEffect } from "react";
import { FileText, Loader2, Download, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { listPdfs, removePdf, downloadPdf, PDFS_EVENT } from "@/lib/pdfRegistry";

/** Shared "Ananta PDFs" registry list — used by Workspace › AI Analytics and Research › AI Analysis. */
export default function AnantaPdfs({ isOwner }) {
    const [pdfs, setPdfs] = useState(listPdfs());
    const [prog, setProg] = useState({}); // id -> pct | 'prep' | 'err' | 100
    useEffect(() => {
        const h = () => setPdfs(listPdfs());
        window.addEventListener(PDFS_EVENT, h);
        return () => window.removeEventListener(PDFS_EVENT, h);
    }, []);
    const analyse = (p) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        window.dispatchEvent(new CustomEvent("ananta:ask", { detail: { text: `Analyse my "${p.title}" report and give me the key takeaways, risks and one improvement.` } }));
        toast.success("Ask Ananta is reviewing your report");
    };
    const download = async (p) => {
        setProg((s) => ({ ...s, [p.id]: "prep" }));
        try {
            await downloadPdf(p.url, `${p.title.replace(/[^\w.-]+/g, "_")}.pdf`, (pct) => setProg((s) => ({ ...s, [p.id]: pct == null ? "prep" : pct })));
            setProg((s) => ({ ...s, [p.id]: 100 }));
            toast.success("Download complete");
            setTimeout(() => setProg((s) => { const n = { ...s }; delete n[p.id]; return n; }), 2500);
        } catch (e) {
            setProg((s) => ({ ...s, [p.id]: "err" }));
            toast.error(String(e?.message || e));
        }
    };
    const label = (v) => (v === "prep" ? "Preparing…" : v === "err" ? "Retry" : v === 100 ? "Done" : `${v}%`);
    return (
        <div className="panel border-atlas-border rounded-xl p-5" data-testid="ws-ananta-pdfs">
            {pdfs.length === 0 ? (
                <div className="py-6 text-center font-mono text-[11px] text-atlas-textTertiary" data-testid="ws-pdfs-empty">
                    No PDFs yet. Generate one from Trade or complete a Research run — it&apos;ll appear here.
                </div>
            ) : (
                <div className="rounded-lg border border-atlas-border divide-y divide-atlas-border max-h-72 overflow-y-auto atlas-scroll">
                    {pdfs.map((p) => {
                        const st = prog[p.id];
                        const busy = st !== undefined && st !== "err";
                        const pct = typeof st === "number" ? st : null;
                        return (
                            <div key={p.id} className="px-3 py-2.5 flex items-center gap-3" data-testid="ws-pdf-row">
                                <FileText className="w-4 h-4 text-atlas-cyan shrink-0" />
                                <div className="min-w-0 flex-1">
                                    <div className="font-mono text-[12px] text-atlas-text truncate">{p.title}</div>
                                    {st !== undefined ? (
                                        <div className="mt-1 flex items-center gap-2" data-testid="ws-pdf-progress">
                                            <div className="h-1 flex-1 rounded-full bg-atlas-border overflow-hidden">
                                                <div className={`h-full ${st === "err" ? "bg-atlas-negative" : "bg-atlas-cyan"} transition-all`} style={{ width: pct != null ? `${pct}%` : "35%" }} />
                                            </div>
                                            <span className={`font-mono text-[9px] ${st === "err" ? "text-atlas-negative" : "text-atlas-cyan"}`}>{label(st)}</span>
                                        </div>
                                    ) : (
                                        <div className="font-mono text-[9px] text-atlas-textTertiary">{new Date(p.ts).toLocaleString()}</div>
                                    )}
                                </div>
                                <button data-testid="ws-pdf-open" onClick={() => download(p)} disabled={busy} title="Download"
                                    className="p-1.5 rounded-lg border border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors disabled:opacity-40">
                                    {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                                </button>
                                <button data-testid="ws-pdf-analyse" onClick={() => analyse(p)} title="Ask Ananta to analyse"
                                    className="p-1.5 rounded-lg border border-atlas-cyan/40 text-atlas-cyan hover:bg-atlas-cyan/10 transition-colors"><Sparkles className="w-3.5 h-3.5" /></button>
                                <button data-testid="ws-pdf-delete" onClick={() => { removePdf(p.id); toast.success("Removed from Ananta PDFs"); }} title="Delete"
                                    className="p-1.5 rounded-lg border border-atlas-border text-atlas-textSecondary hover:text-atlas-negative hover:border-atlas-negative/40 transition-colors"><Trash2 className="w-3.5 h-3.5" /></button>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
