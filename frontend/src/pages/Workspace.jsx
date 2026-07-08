import { useEffect, useState } from "react";
import {
    SlidersHorizontal, GraduationCap, Trophy, Activity, Info, LogOut, CheckCircle2, XCircle, ChevronRight,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import SettingsPage from "@/pages/Settings";

export default function Workspace() {
    const { isOwner, owner, logout } = useAuth();
    const [health, setHealth] = useState(null);

    useEffect(() => {
        const load = async () => {
            const h = {};
            try { await api.riskStatus(); h.backend = true; } catch { h.backend = false; }
            try { const e = await api.getEnvironment(); h.mode = e.mode; h.gate = e.ready_to_trade; } catch { h.mode = "—"; }
            setHealth(h);
        };
        load();
        const t = setInterval(load, 15000);
        return () => clearInterval(t);
    }, []);

    return (
        <div className="space-y-6 pb-24" data-testid="workspace-page">
            {/* Engine & Risk config */}
            <Section icon={SlidersHorizontal} title="Engine & Risk" subtitle="Exit engine, sizing, guardrails & exchange credentials">
                <SettingsPage />
            </Section>

            {/* Learn & Compete */}
            <Section icon={GraduationCap} title="Learn & Compete" subtitle="Education and the judge-ready demo experience">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:gap-4">
                    <ComingSoonCard testid="ws-academy" icon={GraduationCap} title="Academy"
                        desc="Guided lessons — Trading Basics, Risk Management, How Hunter/Squeeze work, Walk-Forward, Monte Carlo, Paper vs Live." />
                    <ComingSoonCard testid="ws-demo" icon={Trophy} title="Competition Demo"
                        desc="One-click preloaded workspace — 5 strategies, historical data, backtests and AI explanations, ready for judges." />
                </div>
            </Section>

            {/* System Health */}
            <Section icon={Activity} title="System Health" subtitle="Live platform status">
                <div className="panel border-atlas-border rounded-xl p-5 grid grid-cols-1 sm:grid-cols-3 gap-4" data-testid="ws-system-health">
                    <HealthRow label="Backend API" ok={health?.backend} okText="Online" badText="Unreachable" />
                    <HealthRow label="Trading Mode" ok={health?.mode ? true : null} okText={health?.mode || "—"} neutral />
                    <HealthRow label="Live Gate" ok={health?.gate} okText="Armed" badText="Closed" />
                </div>
            </Section>

            {/* About + account */}
            <Section icon={Info} title="About" subtitle="Ananta.AI">
                <div className="panel border-atlas-border rounded-xl p-5 space-y-4">
                    <p className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed">
                        <b className="text-atlas-text">Ananta.AI</b> — an AI-native operating system for algorithmic trading.
                        It guides you from strategy design → validation → deployment → monitoring → continuous improvement
                        through a unified, AI-assisted workflow. Spot-only, capital-preservation first.
                    </p>
                    <div className="flex items-center justify-between flex-wrap gap-3 border-t border-atlas-border pt-4">
                        <div className="font-mono text-[10px] text-atlas-textTertiary">
                            {isOwner ? <>Signed in as <span className="text-atlas-text">{owner?.email}</span></> : "Public read-only view"}
                        </div>
                        {isOwner && (
                            <button data-testid="ws-logout-btn"
                                onClick={() => { logout(); toast.success("Signed out"); }}
                                className="flex items-center gap-2 rounded-lg border border-atlas-border px-4 py-2 font-mono text-[11px] tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors">
                                <LogOut className="w-3.5 h-3.5" /> LOG OUT
                            </button>
                        )}
                    </div>
                </div>
            </Section>
        </div>
    );
}

function Section({ icon: Icon, title, subtitle, children }) {
    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2.5">
                <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Icon className="w-4.5 h-4.5 text-atlas-cyan" /></span>
                <div>
                    <div className="font-heading text-lg text-atlas-text leading-none">{title}</div>
                    <div className="label-tag mt-1 text-[9px] text-atlas-textTertiary">{subtitle}</div>
                </div>
            </div>
            {children}
        </div>
    );
}

function ComingSoonCard({ testid, icon: Icon, title, desc }) {
    return (
        <div data-testid={testid} className="panel border-atlas-border rounded-xl p-5 relative overflow-hidden group">
            <span className="absolute top-3 right-3 font-mono text-[8px] uppercase tracking-widest text-atlas-warning border border-atlas-warning/40 bg-atlas-warning/10 rounded-full px-2 py-0.5">Coming soon</span>
            <div className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5 mb-3"><Icon className="w-5 h-5 text-atlas-cyan" /></div>
            <div className="flex items-center gap-1.5 font-heading text-base text-atlas-text mb-1">{title}<ChevronRight className="w-4 h-4 text-atlas-textTertiary" /></div>
            <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">{desc}</p>
        </div>
    );
}

function HealthRow({ label, ok, okText, badText, neutral }) {
    const Icon = neutral ? Activity : ok ? CheckCircle2 : XCircle;
    const cls = neutral ? "text-atlas-cyan" : ok ? "text-atlas-positive" : ok === false ? "text-atlas-negative" : "text-atlas-textTertiary";
    return (
        <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[11px] text-atlas-textSecondary">{label}</span>
            <span className={`flex items-center gap-1.5 font-mono text-[11px] font-bold ${cls}`}>
                <Icon className="w-3.5 h-3.5" />{ok === false ? badText : okText}
            </span>
        </div>
    );
}
