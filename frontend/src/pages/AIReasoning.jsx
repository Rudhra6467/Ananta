import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import api, { API } from "@/lib/api";
import ReasoningTimeline from "@/components/ReasoningTimeline";

export default function AIReasoning() {
    const [items, setItems] = useState([]);
    const [filter, setFilter] = useState("");
    const [executedOnly, setExecutedOnly] = useState(true);

    const refresh = async () => {
        const d = await api.reasoning(15, filter || undefined, executedOnly).catch(() => ({ items: [] }));
        setItems(d.items || []);
    };

    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 15000);
        return () => clearInterval(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filter, executedOnly]);

    const downloadPdf = () => {
        window.open(`${API}/report/reasoning.pdf?limit=200`, "_blank");
        toast.success("PDF DOWNLOAD STARTED", { description: "Reasoning-only competition report." });
    };

    return (
        <div className="space-y-4" data-testid="ai-reasoning-page">
            <div className="flex items-end justify-between flex-wrap gap-3">
                <div>
                    <div className="label-tag">LAYER 4 · EXPLAINABLE AI</div>
                    <h2 className="font-heading font-black text-2xl md:text-3xl tracking-tight mt-1">AI Reasoning Log</h2>
                    <p className="text-atlas-textSecondary text-xs mt-1 max-w-2xl">
                        Every macro evaluation produces a structured BIAS / CONFIDENCE / REASON from Gemini 3 Pro. Drill into any
                        cycle to see the inputs, microstructure evidence, and fusion outcome the engine acted on.
                    </p>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                    <button
                        data-testid="reasoning-executed-only-toggle"
                        onClick={() => setExecutedOnly((v) => !v)}
                        className={`font-mono text-[10px] tracking-widest font-bold px-3 py-2 border transition-colors ${
                            executedOnly
                                ? "bg-atlas-cyan text-atlas-bg border-atlas-cyan"
                                : "text-atlas-textSecondary border-atlas-border hover:text-white"
                        }`}
                    >
                        {executedOnly ? "EXECUTED ONLY ✓" : "EXECUTED ONLY"}
                    </button>
                    <FilterPills value={filter} onChange={setFilter} />
                    <button
                        data-testid="reasoning-download-pdf"
                        onClick={downloadPdf}
                        className="flex items-center gap-2 font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-border hover:border-atlas-cyan hover:text-atlas-cyan transition-colors text-atlas-textSecondary"
                    >
                        <Download className="w-3 h-3" />
                        DOWNLOAD PDF
                    </button>
                    <button
                        data-testid="reasoning-refresh-button"
                        onClick={refresh}
                        className="font-mono text-[10px] text-atlas-textSecondary hover:text-white flex items-center gap-2 transition-colors"
                    >
                        <RefreshCw className="w-3 h-3" />
                        REFRESH
                    </button>
                </div>
            </div>

            <p className="text-[10px] font-mono text-atlas-textTertiary">
                Showing the latest 15 evaluations · scroll within the panel for older records.
            </p>
            <div
                className="max-h-[70vh] overflow-y-scroll pr-2 atlas-scroll"
                data-testid="reasoning-scroll-container"
            >
                <ReasoningTimeline items={items} />
            </div>
        </div>
    );
}

function FilterPills({ value, onChange }) {
    const symbols = ["", "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD"];
    return (
        <div className="flex items-center gap-0 border border-atlas-border" data-testid="reasoning-filter-pills">
            {symbols.map((s) => {
                const label = s || "ALL";
                const active = value === s;
                return (
                    <button
                        key={label}
                        type="button"
                        onClick={() => onChange(s)}
                        data-testid={`reasoning-filter-${label.replace("/", "-")}`}
                        className={`px-3 py-1.5 font-mono text-[10px] tracking-widest font-bold border-r border-atlas-border last:border-r-0 transition-colors ${
                            active ? "bg-atlas-cyan text-atlas-bg" : "text-atlas-textSecondary hover:text-white"
                        }`}
                    >
                        {label}
                    </button>
                );
            })}
        </div>
    );
}
