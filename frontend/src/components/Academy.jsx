import { useState } from "react";
import {
    GraduationCap, Rocket, BookOpen, Shield, Crosshair, Zap, Brain,
    GitBranch, Dices, LineChart, HelpCircle, ChevronDown,
} from "lucide-react";
import LabModal from "@/components/lab/LabModal";

const LESSONS = [
    { id: "start", icon: Rocket, title: "Getting Started", body: [
        "Ananta is an operating system for algorithmic trading. Your journey flows through five workspaces: Cockpit (what's happening now), Trade (paper/live execution), Strategy (what you own), Research (does it work), and Workspace (setup).",
        "The recommended path: pick a strategy → validate it in Research → let it paper-trade → review the AI Coach → only then arm live trading.",
    ] },
    { id: "basics", icon: BookOpen, title: "Trading Basics", body: [
        "A strategy defines WHEN to enter and exit a position. Ananta trades spot crypto only — it buys an asset and later sells it; it never uses leverage.",
        "Every closed trade has a P&L (profit/loss), a return %, and an exit reason (why the engine sold). These build the performance history you see across the app.",
    ] },
    { id: "risk", icon: Shield, title: "Risk Management", body: [
        "Capital preservation comes first. Ananta enforces a daily loss cap, a max number of open positions, a minimum-confidence floor, and a hard account drawdown 'ruin line'.",
        "The Emergency Stop (kill switch) in Trade instantly blocks all new entries. Open positions keep their protective stops.",
    ] },
    { id: "hunter", icon: Crosshair, title: "How Hunter Works", body: [
        "Hunter is the flagship entry engine. It hunts high-conviction setups where price tests a proven support zone after a momentum reset (oversold RSI), with a volatility-contraction base and confirming higher-timeframe trend.",
        "It exits via an ATR trailing stop, profit floors and structural stops — riding trends while cutting failures quickly.",
    ] },
    { id: "squeeze", icon: Zap, title: "How Squeeze Works", body: [
        "Volatility Squeeze looks for periods where price coils into a tight range (low volatility). When volume expands and price breaks out, it enters in the breakout direction.",
        "Squeeze thrives in compression→expansion regimes and is gated off in choppy conditions.",
    ] },
    { id: "ai", icon: Brain, title: "How AI Thinks", body: [
        "Ananta's AI features (Strategy Architect, AI Analyst, Trading Coach) are grounded — they only reason over the real data snapshot the app assembles, so they cite actual numbers instead of hallucinating.",
        "AI never places trades on its own. It suggests; you decide. Every AI surface has a visible credits switch.",
    ] },
    { id: "wfa", icon: GitBranch, title: "Walk-Forward Testing", body: [
        "Walk-forward analysis optimizes a strategy on one slice of history (in-sample), then tests it on the next unseen slice (out-of-sample), rolling forward repeatedly.",
        "A 'robust' verdict means the edge held up out-of-sample — strong evidence it isn't just curve-fit to the past.",
    ] },
    { id: "mc", icon: Dices, title: "Monte Carlo", body: [
        "Monte Carlo reshuffles your trade sequence thousands of times to estimate the RANGE of outcomes — including worst-case drawdown and risk-of-ruin.",
        "A good strategy stays survivable even in unlucky orderings. It answers: 'how bad could a rough streak get?'",
    ] },
    { id: "paperlive", icon: LineChart, title: "Paper vs Live", body: [
        "Paper trading runs the full engine against live prices with simulated money — zero risk, real behavior. Live trading places real orders on your connected exchange.",
        "Always graduate a strategy through paper first. Switch modes in the Trade workspace; the Live gate is armed only when you choose.",
    ] },
    { id: "faq", icon: HelpCircle, title: "FAQ & Best Practices", body: [
        "Start small, validate rigorously, and let the AI Coach guide incremental tuning rather than large manual changes.",
        "Don't chase more indicators — chase a coherent, validated edge. Review weekly, keep risk caps conservative, and only go live once paper results and validation agree.",
    ] },
];

export function AcademyModal({ open, onOpenChange }) {
    const [expanded, setExpanded] = useState("start");
    return (
        <LabModal open={open} onOpenChange={onOpenChange} testid="academy-modal" icon={GraduationCap} accent="cyan"
            title="Academy" subtitle="Learn Ananta — education, not documentation">
            <div className="space-y-2" data-testid="academy-lessons">
                {LESSONS.map((l) => {
                    const isOpen = expanded === l.id;
                    const Icon = l.icon;
                    return (
                        <div key={l.id} className="panel border-atlas-border rounded-xl overflow-hidden" data-testid={`academy-lesson-${l.id}`}>
                            <button onClick={() => setExpanded(isOpen ? "" : l.id)} data-testid={`academy-toggle-${l.id}`}
                                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-atlas-panelHover/40 transition-colors">
                                <span className="w-8 h-8 rounded-lg grid place-items-center border border-atlas-border bg-atlas-cyan/5 shrink-0"><Icon className="w-4 h-4 text-atlas-cyan" /></span>
                                <span className="flex-1 font-heading text-sm text-atlas-text">{l.title}</span>
                                <ChevronDown className={`w-4 h-4 text-atlas-textTertiary transition-transform ${isOpen ? "rotate-180" : ""}`} />
                            </button>
                            {isOpen && (
                                <div className="px-4 pb-4 pl-15 space-y-2">
                                    {l.body.map((p, i) => (
                                        <p key={i} className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">{p}</p>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </LabModal>
    );
}
