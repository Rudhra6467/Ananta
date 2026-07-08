import { useEffect, useState } from "react";
import { ShieldCheck, Brain, ChevronDown } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import SavedConfigsPanel from "@/components/lab/SavedConfigsPanel";
import MonteCarloPanel from "@/components/lab/MonteCarloPanel";
import StrategyValidationPanel from "@/components/StrategyValidationPanel";
import ResearchWizard from "@/components/lab/ResearchWizard";
import AIAnalystTerminal from "@/components/lab/AIAnalystTerminal";
import TradingCoach from "@/components/lab/TradingCoach";
import Reports from "@/pages/Reports";

export default function Research() {
    const { isOwner } = useAuth();
    const [strategies, setStrategies] = useState([]);
    const [sel, setSel] = useState("");
    const [advanced, setAdvanced] = useState(false);

    useEffect(() => {
        api.strategyRegistry().then((d) => {
            const list = d.strategies || [];
            setStrategies(list);
            if (list.length) setSel(list[0].key);
        }).catch(() => {});
    }, []);

    return (
        <div className="space-y-5" data-testid="research-page">
            <Tabs defaultValue="validate" className="atlas-tabs">
                <TabsList className="bg-transparent border-b border-atlas-border w-full justify-start gap-0 rounded-none h-auto p-0 mb-5">
                    <SubTab value="validate" label="VALIDATE" icon={ShieldCheck} />
                    <SubTab value="analyze" label="AI ANALYSIS" icon={Brain} />
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

                <TabsContent value="analyze" className="m-0 space-y-4">
                    <TradingCoach isOwner={isOwner} />
                    <AIAnalystTerminal isOwner={isOwner} strategy={sel} />
                    <Reports />
                </TabsContent>
            </Tabs>
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
