import { useEffect, useState } from "react";
import { ShieldCheck, Brain, ChevronDown, Rocket, Sparkles, CalendarRange, FileText, Activity } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useResearchStore } from "@/lib/researchStore";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import SavedConfigsPanel from "@/components/lab/SavedConfigsPanel";
import MonteCarloPanel from "@/components/lab/MonteCarloPanel";
import StrategyValidationPanel from "@/components/StrategyValidationPanel";
import ResearchWizard from "@/components/lab/ResearchWizard";
import StrategyHealthPanel from "@/components/lab/StrategyHealthPanel";
import AIAnalystTerminal from "@/components/lab/AIAnalystTerminal";
import TradingCoach from "@/components/lab/TradingCoach";
import ClosedTradesAnalysis from "@/components/lab/ClosedTradesAnalysis";
import HeaderActionPortal from "@/components/HeaderActionPortal";
import AnantaPdfs from "@/components/AnantaPdfs";

export default function Research() {
    const { isOwner } = useAuth();
    const [strategies, setStrategies] = useState([]);
    const [sel, setSel] = useState("");
    const [advanced, setAdvanced] = useState(false);
    const [sub, setSub] = useState(() => {
        const pending = localStorage.getItem("ananta_research_sub");
        if (pending) { localStorage.removeItem("ananta_research_sub"); return pending; }
        return "validate";
    });

    useEffect(() => {
        api.strategyRegistry().then((d) => {
            const list = d.strategies || [];
            setStrategies(list);
            if (list.length) setSel(list[0].key);
        }).catch(() => {});
        // deep-link from Workspace "Analyse" → jump to the Closed Trades sub-tab
        const onClosed = () => setSub("closed");
        window.addEventListener("ananta:research-closed", onClosed);
        // Tapping the "Research Lab" header title returns to the Validate home (Choose Strategies).
        const onHome = (e) => { if (e.detail?.id === "research") { setSub("validate"); useResearchStore.getState().reset(); } };
        window.addEventListener("ananta:tab-home", onHome);
        // consume a pending deep-link target set just before this component mounted
        const pending = localStorage.getItem("ananta_research_sub");
        if (pending) { localStorage.removeItem("ananta_research_sub"); setSub(pending); }
        return () => {
            window.removeEventListener("ananta:research-closed", onClosed);
            window.removeEventListener("ananta:tab-home", onHome);
        };
    }, []);

    const startResearch = () => {
        const store = useResearchStore.getState();
        const onValidate = sub === "validate";
        if (onValidate) {
            // Already on the Validation tab — the wizard is mounted. If the user hasn't
            // ticked any strategies yet, nudge them (with a device buzz) instead of no-op.
            if (store.strat.length === 0) {
                if (typeof navigator !== "undefined" && navigator.vibrate) navigator.vibrate([120, 60, 120]);
                toast.info("Select at least one strategy", { description: "Tick one or more engines below to research." });
            }
            store.reset(); // back to Choose Strategies (step 0)
        } else {
            // From any other sub-tab → jump to Validation home (Choose Strategies).
            setSub("validate");
            store.reset();
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
    };

    return (
        <div className="space-y-5" data-testid="research-page">
            {/* primary action lives in the scroll-through top header */}
            <HeaderActionPortal>
                <button data-testid="research-start" onClick={startResearch}
                    className="flex items-center gap-1.5 rounded-full bg-atlas-cyan text-black font-mono text-[10px] font-bold tracking-wide px-3.5 py-2 hover:brightness-110 active:scale-95 transition-all">
                    <Rocket className="w-3.5 h-3.5" /> Start Research
                </button>
            </HeaderActionPortal>

            <Tabs value={sub} onValueChange={setSub} className="atlas-tabs">
                <TabsList className="bg-transparent border-b border-atlas-border w-full justify-start gap-0 rounded-none h-auto p-0 mb-5">
                    <SubTab value="validate" label="VALIDATE" icon={ShieldCheck} />
                    <SubTab value="health" label="HEALTH" icon={Activity} />
                    <SubTab value="analyze" label="AI ANALYSIS" icon={Brain} />
                    <SubTab value="closed" label="CLOSED TRADES" icon={ShieldCheck} />
                </TabsList>

                <TabsContent value="validate" className="m-0 space-y-4">
                    <ResearchWizard />

                    <button data-testid="research-advanced-toggle" onClick={() => setAdvanced((v) => !v)}
                        className="flex items-center gap-2 font-mono text-[10px] tracking-widest text-atlas-textTertiary hover:text-atlas-text transition-colors">
                        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${advanced ? "rotate-180" : ""}`} />
                        {advanced ? "HIDE" : "SHOW"} ADVANCED TOOLS (optimization · sweeps · saved configs)
                    </button>

                    {advanced && (
                        <div className="space-y-4">
                            <div className="panel border-atlas-border rounded-2xl p-4 flex items-center gap-3 flex-wrap" data-testid="research-strategy-select-bar">
                                <span className="label-tag">STRATEGY</span>
                                <div className="relative">
                                    <select data-testid="research-strategy-select" value={sel} onChange={(e) => setSel(e.target.value)}
                                        className="appearance-none bg-atlas-panel border border-atlas-border rounded-lg pl-3 pr-8 py-2 font-mono text-sm text-atlas-text focus:border-atlas-cyan outline-none">
                                        {strategies.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
                                    </select>
                                    <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-atlas-textTertiary pointer-events-none" />
                                </div>
                            </div>
                            {sel && <SavedConfigsPanel isOwner={isOwner} only={sel} />}
                            <MonteCarloPanel />
                            <StrategyValidationPanel />
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="health" className="m-0 space-y-4">
                    <StrategyHealthPanel isOwner={isOwner} />
                </TabsContent>

                <TabsContent value="analyze" className="m-0 space-y-6">
                    <AnalysisSection icon={Sparkles} title="Ask Ananta" subtitle="About Trading/Strategy/Market">
                        <AIAnalystTerminal isOwner={isOwner} />
                    </AnalysisSection>
                    <AnalysisSection icon={CalendarRange} title="Weekly Review" subtitle="What/How did you do this week?">
                        <TradingCoach isOwner={isOwner} />
                    </AnalysisSection>
                    <AnalysisSection icon={FileText} title="Reports" subtitle="PDFs from your validation runs — open, analyse or delete.">
                        <AnantaPdfs isOwner={isOwner} />
                    </AnalysisSection>
                </TabsContent>

                <TabsContent value="closed" className="m-0 space-y-4">
                    <ClosedTradesAnalysis isOwner={isOwner} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

function AnalysisSection({ icon: Icon, title, subtitle, children }) {
    return (
        <div className="space-y-3" data-testid={`analysis-section-${title.toLowerCase().replace(/\s+/g, "-")}`}>
            <div className="flex items-center gap-2.5">
                <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Icon className="w-4 h-4 text-atlas-cyan" /></span>
                <div>
                    <div className="font-heading text-lg text-atlas-text leading-none">{title}</div>
                    <div className="label-tag mt-1 text-[9px] text-atlas-textTertiary">{subtitle}</div>
                </div>
            </div>
            {children}
        </div>
    );
}

function SubTab({ value, label, icon: Icon }) {
    return (
        <TabsTrigger value={value} data-testid={`research-subtab-${value}`}
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-atlas-cyan data-[state=active]:bg-transparent data-[state=active]:text-white text-atlas-textSecondary font-mono text-[11px] tracking-[0.2em] uppercase font-bold px-5 py-3 transition-colors duration-150 hover:text-white flex items-center gap-2">
            <Icon className="w-4 h-4" strokeWidth={2} /> {label}
        </TabsTrigger>
    );
}
