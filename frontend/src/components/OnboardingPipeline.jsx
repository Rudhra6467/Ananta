import { useEffect, useRef, useState } from "react";
import {
    UserCheck, Link2, ShieldCheck, Wallet, Brain, FlaskConical, Sparkles, LineChart, Rocket,
    CheckCircle2, Loader2, X, PartyPopper,
} from "lucide-react";
import AnantaLogo from "@/components/AnantaLogo";

const STEPS = [
    { key: "account", icon: UserCheck, label: "Create Account", detail: "Owner identity verified" },
    { key: "exchange", icon: Link2, label: "Connect Exchange", detail: "Kraken · CCXT" },
    { key: "verify", icon: ShieldCheck, label: "API Verified", detail: "Read-only market access confirmed" },
    { key: "import", icon: Wallet, label: "Import Portfolio", detail: "$1,200 paper book initialized" },
    { key: "strategy", icon: Brain, label: "Choose Strategy", detail: "Hunter · Squeeze · Continuation" },
    { key: "validate", icon: FlaskConical, label: "Run Historical Validation", detail: "Walk-Forward + Monte Carlo" },
    { key: "ai", icon: Sparkles, label: "AI Review", detail: "Strategy Architect sign-off" },
    { key: "paper", icon: LineChart, label: "Paper Trading", detail: "Live simulation engaged" },
    { key: "live", icon: Rocket, label: "Ready For Live Trading", detail: "Gate armed — you decide when" },
];

/**
 * CI/CD-style animated onboarding pipeline. Steps light up in sequence like a
 * GitHub Actions run, ending with a "trading OS is ready" finale.
 */
export default function OnboardingPipeline({ open, onClose }) {
    const [active, setActive] = useState(-1);
    const [done, setDone] = useState(false);
    const timers = useRef([]);

    useEffect(() => {
        if (!open) return;
        setActive(-1); setDone(false);
        timers.current.forEach(clearTimeout);
        timers.current = [];
        STEPS.forEach((_, i) => {
            timers.current.push(setTimeout(() => setActive(i), 500 + i * 650));
        });
        timers.current.push(setTimeout(() => { setActive(STEPS.length); setDone(true); }, 500 + STEPS.length * 650));
        return () => timers.current.forEach(clearTimeout);
    }, [open]);

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-[60] bg-atlas-bg/95 backdrop-blur-xl flex items-center justify-center p-4 overflow-y-auto" data-testid="onboarding-pipeline">
            <button data-testid="onboarding-skip" onClick={onClose}
                className="absolute top-5 right-5 flex items-center gap-1.5 font-mono text-[10px] tracking-widest text-atlas-textTertiary hover:text-atlas-text transition-colors">
                {done ? "CLOSE" : "SKIP"} <X className="w-3.5 h-3.5" />
            </button>

            <div className="w-full max-w-lg my-10">
                <div className="flex flex-col items-center text-center mb-8">
                    <AnantaLogo className="h-12 w-12 mb-3" />
                    <h1 className="font-heading font-light text-3xl text-atlas-text">Welcome to Ananta</h1>
                    <p className="label-tag mt-2 text-atlas-textTertiary">Provisioning your trading operating system</p>
                </div>

                {/* pipeline */}
                <div className="relative pl-8">
                    <div className="absolute left-[13px] top-2 bottom-2 w-px bg-atlas-border" />
                    <div className="absolute left-[13px] top-2 w-px bg-atlas-cyan transition-all duration-500"
                        style={{ height: `${Math.max(0, Math.min(1, (active + 1) / STEPS.length)) * 100}%` }} />
                    {STEPS.map((s, i) => {
                        const state = i < active ? "done" : i === active ? "run" : "idle";
                        const Icon = state === "done" ? CheckCircle2 : state === "run" ? Loader2 : s.icon;
                        return (
                            <div key={s.key} className="relative pb-5 last:pb-0 transition-opacity duration-500"
                                style={{ opacity: state === "idle" ? 0.4 : 1 }} data-testid={`onboarding-step-${s.key}`}>
                                <span className={`absolute -left-[31px] top-0 grid place-items-center w-[27px] h-[27px] rounded-full border bg-atlas-bg ${
                                    state === "done" ? "text-atlas-cyan border-atlas-cyan/50"
                                        : state === "run" ? "text-atlas-cyan border-atlas-cyan" : "text-atlas-textTertiary border-atlas-border"}`}>
                                    <Icon className={`w-[15px] h-[15px] ${state === "run" ? "animate-spin" : ""}`}
                                        fill={state === "done" ? "currentColor" : "none"} fillOpacity={state === "done" ? 0.15 : 0} />
                                </span>
                                <div className="flex items-center justify-between gap-2">
                                    <span className={`font-heading text-sm ${state === "idle" ? "text-atlas-textTertiary" : "text-atlas-text"}`}>{s.label}</span>
                                    {state === "done" && <span className="font-mono text-[9px] text-atlas-cyan">DONE</span>}
                                    {state === "run" && <span className="font-mono text-[9px] text-atlas-cyan blink-cursor">RUNNING</span>}
                                </div>
                                <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">{s.detail}</div>
                            </div>
                        );
                    })}
                </div>

                {/* finale */}
                {done && (
                    <div className="mt-6 panel border-atlas-cyan/40 bg-atlas-cyan/5 rounded-2xl p-6 text-center animate-[fadeIn_0.4s_ease]" data-testid="onboarding-finale">
                        <PartyPopper className="w-7 h-7 text-atlas-cyan mx-auto mb-2" />
                        <div className="font-heading text-xl text-atlas-text">Your trading operating system is ready.</div>
                        <div className="font-mono text-[11px] text-atlas-textSecondary mt-2">Estimated setup time: <span className="text-atlas-cyan font-bold">4 minutes</span></div>
                        <button data-testid="onboarding-enter" onClick={onClose}
                            className="mt-5 w-full rounded-xl bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-xs tracking-widest font-bold py-3 transition-colors">
                            ENTER ANANTA
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
