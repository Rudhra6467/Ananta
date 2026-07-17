import { useEffect, useState } from "react";
import { GraduationCap, Trophy, Rocket, Play, RotateCcw, Loader2, FileText, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AcademyModal } from "@/components/Academy";

// Learning Hub — migrated out of the old Workspace tab into the Account overlay.
// Bundles: Competition Demo (load/reset), Guided Tour replay, and the Academy.
export default function LearningHub({ onClose }) {
    const { isOwner } = useAuth();
    const [academyOpen, setAcademyOpen] = useState(false);
    const tour = () => { onClose?.(); window.dispatchEvent(new Event("ananta:tour")); };

    return (
        <div data-testid="account-learning-hub">
            <div className="label-tag mb-2">LEARNING &amp; DEMO</div>
            <div className="space-y-3">
                <CompetitionDemo isOwner={isOwner} />
                <div className="grid grid-cols-2 gap-3">
                    <button data-testid="account-tour-replay" onClick={tour}
                        className="panel border-atlas-border rounded-xl p-4 text-left hover:border-atlas-cyan/40 transition-colors">
                        <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5 mb-2"><Rocket className="w-4.5 h-4.5 text-atlas-cyan" /></span>
                        <div className="font-heading text-sm text-atlas-text">Guided Tour</div>
                        <p className="font-mono text-[10px] text-atlas-textSecondary mt-0.5">Replay the onboarding pipeline.</p>
                    </button>
                    <button data-testid="account-academy" onClick={() => setAcademyOpen(true)}
                        className="panel border-atlas-border rounded-xl p-4 text-left hover:border-atlas-cyan/40 transition-colors group">
                        <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5 mb-2"><GraduationCap className="w-4.5 h-4.5 text-atlas-cyan" /></span>
                        <div className="flex items-center gap-1 font-heading text-sm text-atlas-text">Academy<ChevronRight className="w-3.5 h-3.5 text-atlas-textTertiary group-hover:translate-x-0.5 transition-transform" /></div>
                        <p className="font-mono text-[10px] text-atlas-textSecondary mt-0.5">Guided lessons on the engine.</p>
                    </button>
                </div>
            </div>
            <AcademyModal open={academyOpen} onOpenChange={setAcademyOpen} />
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
            } else { await api.demoReset(); toast.success("Reset to a clean $1,200 paper book"); }
            await refresh();
        } catch (e) { toast.error("Action failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setBusy(""); }
    };

    const loaded = status?.loaded;
    return (
        <div data-testid="account-demo" className="panel border-atlas-cyan/30 bg-atlas-cyan/5 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
                <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-cyan/40 bg-atlas-cyan/10"><Trophy className="w-4.5 h-4.5 text-atlas-cyan" /></span>
                <span className={`font-mono text-[8px] uppercase tracking-widest rounded-full px-2 py-0.5 border ${loaded ? "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10" : "text-atlas-textTertiary border-atlas-border"}`} data-testid="account-demo-status">
                    {loaded ? `Loaded · ${status.demo_trades} trades` : "Not loaded"}
                </span>
            </div>
            <div className="font-heading text-sm text-atlas-text mb-1">Competition Demo</div>
            <p className="font-mono text-[10px] text-atlas-textSecondary leading-relaxed">
                Preloads a curated workspace across the 3 real strategies — ~40 trades, saved configs and a completed
                walk-forward run. Overwrites preview data (preview only).
            </p>
            <div className="flex items-center gap-2 mt-3">
                <button data-testid="account-demo-load" onClick={() => run("load")} disabled={!!busy || !isOwner}
                    className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-atlas-cyan hover:brightness-110 text-atlas-bg font-mono text-[10px] tracking-widest font-bold py-2.5 transition-all disabled:opacity-50">
                    {busy === "load" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />} LOAD DEMO
                </button>
                <button data-testid="account-demo-reset" onClick={() => run("reset")} disabled={!!busy || !isOwner}
                    className="flex items-center justify-center gap-2 rounded-lg border border-atlas-border text-atlas-textSecondary hover:text-atlas-text font-mono text-[10px] tracking-widest px-3 py-2.5 transition-colors disabled:opacity-50">
                    {busy === "reset" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />} RESET
                </button>
            </div>
        </div>
    );
}
