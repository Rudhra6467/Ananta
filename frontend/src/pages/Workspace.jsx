import { useEffect, useState } from "react";
import {
    SlidersHorizontal, GraduationCap, Trophy, Activity, Info, LogOut, CheckCircle2, XCircle, ChevronRight,
    Play, RotateCcw, Loader2, Rocket, Archive, Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useAppData } from "@/context/AppDataContext";
import SettingsPage from "@/pages/Settings";
import { AcademyModal } from "@/components/Academy";

export default function Workspace() {
    const { isOwner, owner, logout } = useAuth();
    const { trades } = useAppData();
    const [health, setHealth] = useState(null);
    const [academyOpen, setAcademyOpen] = useState(false);

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
                    <CompetitionDemo isOwner={isOwner} />
                    <GuidedTourCard />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:gap-4">
                    <button data-testid="ws-academy" onClick={() => setAcademyOpen(true)}
                        className="panel border-atlas-border rounded-xl p-5 text-left hover:border-atlas-cyan/40 transition-colors group">
                        <div className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5 mb-3"><GraduationCap className="w-5 h-5 text-atlas-cyan" /></div>
                        <div className="flex items-center gap-1.5 font-heading text-base text-atlas-text mb-1">Academy<ChevronRight className="w-4 h-4 text-atlas-textTertiary group-hover:translate-x-0.5 transition-transform" /></div>
                        <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">Guided lessons — Trading Basics, Risk Management, How Hunter/Squeeze work, Walk-Forward, Monte Carlo, Paper vs Live.</p>
                    </button>
                </div>
            </Section>
            <AcademyModal open={academyOpen} onOpenChange={setAcademyOpen} />

            {/* Closed Trades History */}
            <Section icon={Archive} title="Closed Trades History" subtitle="Your completed round-trips">
                <ClosedTradesHistory trades={trades} />
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

function ClosedTradesHistory({ trades }) {
    const closed = (trades || []).filter((t) => t.side === "SELL" && (t.status || "FILLED") === "FILLED" && t.pnl != null).slice(0, 12);
    const goAnalyse = () => {
        localStorage.setItem("ananta_research_sub", "closed");
        window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "research" } }));
        window.dispatchEvent(new Event("ananta:research-closed"));
    };
    return (
        <div className="panel border-atlas-border rounded-xl p-5" data-testid="ws-closed-history">
            {closed.length === 0 ? (
                <div className="py-6 text-center font-mono text-[11px] text-atlas-textTertiary">No closed trades yet.</div>
            ) : (
                <div className="rounded-lg border border-atlas-border divide-y divide-atlas-border max-h-64 overflow-y-auto atlas-scroll">
                    {closed.map((t) => (
                        <div key={t.id} className="px-3 py-2 flex items-center justify-between font-mono text-[11px]" data-testid="ws-closed-row">
                            <span className="text-atlas-text font-bold w-14">{(t.symbol || "").split("/")[0]}</span>
                            <span className="text-atlas-textTertiary text-[9px] uppercase">{["PAPER", "DRY_RUN"].includes(t.mode) ? "paper" : "live"}</span>
                            <span className="text-atlas-textTertiary truncate mx-2 flex-1 text-right">{t.exit_reason || "-"}</span>
                            <span className={`tabular-nums font-bold w-20 text-right ${t.pnl > 0 ? "text-atlas-positive" : t.pnl < 0 ? "text-atlas-negative" : "text-atlas-textSecondary"}`}>{t.pnl >= 0 ? "+" : ""}${(t.pnl || 0).toFixed(2)}</span>
                        </div>
                    ))}
                </div>
            )}
            <div className="flex justify-end mt-3">
                <button data-testid="ws-analyse-btn" onClick={goAnalyse}
                    className="flex items-center gap-2 rounded-lg bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-4 py-2.5 transition-colors">
                    <Sparkles className="w-3.5 h-3.5" /> ANALYSE
                </button>
            </div>
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

function CompetitionDemo({ isOwner }) {
    const [status, setStatus] = useState(null);
    const [busy, setBusy] = useState("");

    const refresh = () => api.demoStatus().then(setStatus).catch(() => {});
    useEffect(() => { refresh(); }, []);

    const run = async (kind) => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setBusy(kind);
        try {
            if (kind === "load") {
                const r = await api.demoLoad();
                toast.success("Competition Demo loaded", { description: `${r.trades} trades · ${r.configs} configs across ${r.strategies.length} strategies` });
            } else {
                await api.demoReset();
                toast.success("Reset to a clean $1,200 paper book");
            }
            await refresh();
        } catch (e) { toast.error("Action failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setBusy(""); }
    };

    const loaded = status?.loaded;
    return (
        <div data-testid="ws-demo" className="panel border-atlas-cyan/30 bg-atlas-cyan/5 rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
                <div className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-cyan/40 bg-atlas-cyan/10"><Trophy className="w-5 h-5 text-atlas-cyan" /></div>
                <span className={`font-mono text-[8px] uppercase tracking-widest rounded-full px-2 py-0.5 border ${loaded ? "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10" : "text-atlas-textTertiary border-atlas-border"}`} data-testid="ws-demo-status">
                    {loaded ? `Loaded · ${status.demo_trades} trades` : "Not loaded"}
                </span>
            </div>
            <div className="font-heading text-base text-atlas-text mb-1">Competition Demo</div>
            <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">
                One click preloads a curated workspace across the 3 real strategies — ~40 trades, saved configs,
                a completed walk-forward run and varied LIVE/PAPER/DISABLED statuses. Every screen goes live instantly.
            </p>
            <div className="mt-2 font-mono text-[9px] text-atlas-warning">Overwrites current preview data. Preview only — not production.</div>
            <div className="flex items-center gap-2 mt-4">
                <button data-testid="ws-demo-load" onClick={() => run("load")} disabled={!!busy || !isOwner}
                    className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold py-2.5 transition-colors disabled:opacity-50">
                    {busy === "load" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />} LOAD DEMO
                </button>
                <button data-testid="ws-demo-reset" onClick={() => run("reset")} disabled={!!busy || !isOwner}
                    className="flex items-center justify-center gap-2 rounded-lg border border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary font-mono text-[11px] tracking-widest px-3 py-2.5 transition-colors disabled:opacity-50">
                    {busy === "reset" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />} RESET
                </button>
            </div>
        </div>
    );
}

function GuidedTourCard() {
    return (
        <div data-testid="ws-tour" className="panel border-atlas-border rounded-xl p-5 flex flex-col">
            <div className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5 mb-3"><Rocket className="w-5 h-5 text-atlas-cyan" /></div>
            <div className="font-heading text-base text-atlas-text mb-1">Guided Tour</div>
            <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed flex-1">
                Replay the animated onboarding pipeline — the idea → validation → deployment journey judges see on first login.
            </p>
            <button data-testid="ws-tour-replay" onClick={() => window.dispatchEvent(new Event("ananta:tour"))}
                className="mt-4 flex items-center justify-center gap-2 rounded-lg border border-atlas-cyan/40 text-atlas-cyan hover:bg-atlas-cyan/10 font-mono text-[11px] tracking-widest py-2.5 transition-colors">
                <Play className="w-3.5 h-3.5" /> REPLAY TOUR
            </button>
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
