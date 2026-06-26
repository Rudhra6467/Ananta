/**
 * Judge View - read-only public-link dashboard.
 *
 * Renders the same Dashboard + AI Reasoning Log as the operator view but with:
 *  - a "JUDGE VIEW · READ ONLY" banner
 *  - no Settings tab
 *  - no Reset Portfolio button, no Manual Kill toggle, no Run Cycle button
 *  - no API keys ever fetched (uses /api/public/snapshot which strips them)
 */
import { useEffect, useState } from "react";
import { Activity, Cpu, Eye, ShieldHalf, Terminal, Download } from "lucide-react";
import { toast, Toaster } from "sonner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import PortfolioCardRO from "@/components/PortfolioCardRO";
import KillSwitchPanel from "@/components/KillSwitchPanel";
import PriceTicker from "@/components/PriceTicker";
import TradeHistory from "@/components/TradeHistory";
import ReasoningTimeline from "@/components/ReasoningTimeline";
import { API } from "@/lib/api";
import axios from "axios";

const NAV = [
    { id: "dashboard", label: "DASHBOARD", icon: Activity },
    { id: "reasoning", label: "AI REASONING LOG", icon: Cpu },
];

export default function JudgeView() {
    const [tab, setTab] = useState("dashboard");
    const [data, setData] = useState(null);
    const [now, setNow] = useState(new Date());

    const fetchAll = async () => {
        try {
            const r = await axios.get(`${API}/public/snapshot`);
            setData(r.data);
        } catch (e) {
            // Non-fatal: the Judge view is read-only and polls every 15s.
            // Log so prod issues are visible in browser devtools without
            // spamming toasts for every transient network blip.
            console.warn("[JudgeView] snapshot fetch failed:", e?.message || e);
        }
    };

    useEffect(() => {
        fetchAll();
        const t = setInterval(fetchAll, 15000);
        const t2 = setInterval(() => setNow(new Date()), 1000);
        return () => {
            clearInterval(t);
            clearInterval(t2);
        };
    }, []);

    const downloadPdf = (kind = "full") => {
        const url = `${API}/report/${kind === "reasoning" ? "reasoning" : "full"}.pdf`;
        window.open(url, "_blank");
        toast.success("PDF DOWNLOAD STARTED", {
            description: `${kind === "reasoning" ? "Reasoning-only" : "Full competition"} report.`,
        });
    };

    return (
        <div className="min-h-screen bg-atlas-bg text-white font-body grid-bg" data-testid="judge-view">
            <header
                className="sticky top-0 z-30 backdrop-blur-xl bg-atlas-bg/70 border-b border-atlas-border"
                data-testid="judge-header"
            >
                <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-3 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-atlas-cyan flex items-center justify-center">
                            <Terminal className="w-4 h-4 text-atlas-bg" strokeWidth={2.5} />
                        </div>
                        <div>
                            <div className="font-heading font-black tracking-tight text-base md:text-lg leading-none">
                                CRYPTOATLAS<span className="text-atlas-cyan">.AI</span>
                            </div>
                            <div className="label-tag mt-1 text-[9px] text-atlas-textSecondary">
                                ONTARIO-COMPLIANT SPOT TRADER
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <div
                            data-testid="judge-readonly-banner"
                            className="hidden md:inline-flex items-center gap-2 px-3 py-1 border border-atlas-cyan/50 bg-atlas-cyan/5 glow-cyan font-mono text-[10px] tracking-widest font-bold text-atlas-cyan"
                        >
                            <Eye className="w-3 h-3" />
                            JUDGE VIEW · READ ONLY
                        </div>
                        <div className="hidden md:block font-mono text-xs text-atlas-textSecondary">
                            {now.toISOString().replace("T", " ").slice(0, 19)} UTC
                        </div>
                    </div>
                </div>
            </header>

            <main className="max-w-[1600px] mx-auto px-4 md:px-6 py-6">
                <Tabs value={tab} onValueChange={setTab} className="atlas-tabs">
                    <div className="flex items-center justify-between border-b border-atlas-border mb-6">
                        <TabsList className="bg-transparent w-auto justify-start gap-0 rounded-none h-auto p-0">
                            {NAV.map((n) => {
                                const Icon = n.icon;
                                return (
                                    <TabsTrigger
                                        key={n.id}
                                        value={n.id}
                                        data-testid={`judge-nav-tab-${n.id}`}
                                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-atlas-cyan data-[state=active]:bg-transparent data-[state=active]:text-white text-atlas-textSecondary font-mono text-[11px] tracking-[0.2em] uppercase font-bold px-5 py-3 transition-colors duration-150 hover:text-white"
                                    >
                                        <Icon className="w-4 h-4 mr-2" strokeWidth={2} />
                                        {n.label}
                                    </TabsTrigger>
                                );
                            })}
                        </TabsList>
                        <div className="flex items-center gap-0 pb-2">
                            <button
                                data-testid="download-full-pdf"
                                onClick={() => downloadPdf("full")}
                                className="flex items-center gap-2 font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-border hover:border-atlas-cyan hover:text-atlas-cyan transition-colors text-atlas-textSecondary"
                            >
                                <Download className="w-3 h-3" />
                                DOWNLOAD PDF
                            </button>
                        </div>
                    </div>

                    <TabsContent value="dashboard" className="m-0">
                        {data ? (
                            <DashboardRO data={data} />
                        ) : (
                            <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary">
                                <span className="blink-cursor">LOADING LIVE SNAPSHOT</span>
                            </div>
                        )}
                    </TabsContent>
                    <TabsContent value="reasoning" className="m-0">
                        {data ? (
                            <div className="space-y-4">
                                <div className="flex items-end justify-between flex-wrap gap-3">
                                    <div>
                                        <div className="label-tag">LAYER 4 · EXPLAINABLE AI</div>
                                        <h2 className="font-heading font-black text-2xl md:text-3xl tracking-tight mt-1">
                                            AI Reasoning Log
                                        </h2>
                                        <p className="text-atlas-textSecondary text-xs mt-1 max-w-2xl">
                                            Every macro evaluation produces a structured BIAS / CONFIDENCE / REASON from Gemini 3
                                            Pro. Expand any cycle to see the full evidence the engine acted on.
                                        </p>
                                    </div>
                                    <button
                                        data-testid="download-reasoning-pdf"
                                        onClick={() => downloadPdf("reasoning")}
                                        className="flex items-center gap-2 font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-border hover:border-atlas-cyan hover:text-atlas-cyan transition-colors text-atlas-textSecondary"
                                    >
                                        <Download className="w-3 h-3" />
                                        REASONING-ONLY PDF
                                    </button>
                                </div>
                                <ReasoningTimeline items={data.reasoning || []} />
                            </div>
                        ) : null}
                    </TabsContent>
                </Tabs>
            </main>

            <footer className="border-t border-atlas-border mt-12">
                <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-4 flex items-center justify-between text-[10px] font-mono text-atlas-textTertiary">
                    <div>READ-ONLY PUBLIC VIEW · SPOT ONLY · NO LEVERAGE · CAPITAL PRESERVATION FIRST</div>
                    <div className="flex items-center gap-2">
                        <ShieldHalf className="w-3 h-3" />
                        <span>EXPLAINABLE AI · DEFENSIVE ARCHITECTURE</span>
                    </div>
                </div>
            </footer>
            <Toaster
                position="bottom-right"
                theme="dark"
                toastOptions={{
                    style: {
                        background: "#111317",
                        border: "1px solid #262B33",
                        color: "#fff",
                        borderRadius: 0,
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 12,
                    },
                }}
            />
        </div>
    );
}

function DashboardRO({ data }) {
    const portfolio = data.portfolio;
    const risk = data.risk;
    const snapshots = data.snapshots || [];
    const trades = data.trades || [];

    return (
        <div className="space-y-6" data-testid="judge-dashboard">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                <div className="lg:col-span-7">
                    <PortfolioCardRO portfolio={portfolio} />
                </div>
                <div className="lg:col-span-5">
                    <KillSwitchPanel risk={risk} />
                </div>
            </div>

            <section>
                <div className="mb-3">
                    <div className="label-tag">LAYER 1 · MARKET AGGREGATION</div>
                    <h2 className="font-heading font-bold text-2xl tracking-tight mt-1">Live Spot Markets</h2>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-0 border border-atlas-border">
                    {snapshots.length === 0 ? (
                        <div className="col-span-full p-8 text-center text-atlas-textSecondary font-mono text-xs">
                            <span className="blink-cursor">FETCHING LIVE MARKET DATA</span>
                        </div>
                    ) : (
                        snapshots.map((s) => <PriceTicker key={s.symbol} snapshot={s} />)
                    )}
                </div>
            </section>

            <section>
                <div className="mb-3">
                    <div className="label-tag">LAYER 6 · TRADE EXECUTION LOG</div>
                    <h2 className="font-heading font-bold text-2xl tracking-tight mt-1">Recent Activity</h2>
                </div>
                <TradeHistory trades={trades.slice(0, 15)} />
            </section>
        </div>
    );
}
