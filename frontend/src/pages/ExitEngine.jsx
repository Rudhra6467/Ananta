import { useEffect, useState } from "react";
import { SlidersHorizontal, Sparkles, Archive, FileText, Power, Shield, Loader2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useAppData } from "@/context/AppDataContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import SettingsPage from "@/pages/Settings";
import HeaderActionPortal from "@/components/HeaderActionPortal";
import AnantaPdfs from "@/components/AnantaPdfs";
import ExitEngineWorkflow from "@/components/ExitEngineWorkflow";

export default function ExitEngine() {
    const { isOwner } = useAuth();
    const { trades } = useAppData();
    const [tab, setTab] = useState("engine");
    const [killed, setKilled] = useState(false);

    useEffect(() => {
        const onHome = (e) => { if (e.detail?.id === "workspace") { setTab("engine"); window.scrollTo({ top: 0, behavior: "smooth" }); } };
        window.addEventListener("ananta:tab-home", onHome);
        return () => window.removeEventListener("ananta:tab-home", onHome);
    }, []);
    useEffect(() => { api.settings().then((s) => setKilled(!!s.manual_kill_switch)).catch(() => {}); }, []);

    const toggleKill = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        try {
            await api.updateSettings({ manual_kill_switch: !killed });
            setKilled(!killed);
            toast[!killed ? "error" : "success"](!killed ? "ANANTA STOPPED" : "ANANTA RESUMED");
        } catch (e) { toast.error("Update failed", { description: String(e?.message || e) }); }
    };

    return (
        <div className="space-y-5 pb-24" data-testid="exit-engine-page">
            <HeaderActionPortal>
                <button data-testid="workspace-stop-ananta" onClick={toggleKill}
                    className={`flex items-center gap-1.5 rounded-full border px-3.5 py-2 font-mono text-[10px] font-bold tracking-widest transition-all ${
                        killed ? "border-atlas-negative bg-atlas-negative/15 text-atlas-negative animate-pulse"
                            : "border-atlas-negative/40 text-atlas-negative hover:bg-atlas-negative/10"}`}>
                    <Power className="w-3.5 h-3.5" strokeWidth={2.5} />{killed ? "Resume" : "Stop Ananta"}
                </button>
            </HeaderActionPortal>

            <Tabs value={tab} onValueChange={setTab} className="atlas-tabs">
                <div className="flex items-center justify-between gap-2 border-b border-atlas-border mb-5 flex-wrap">
                    <TabsList className="bg-transparent w-auto justify-start gap-0 rounded-none h-auto p-0">
                        <ETab value="engine" label="EXIT ENGINE" icon={SlidersHorizontal} />
                        <ETab value="risk" label="RISK MONITOR" icon={Shield} />
                        <ETab value="ai" label="AI ANALYSIS" icon={Sparkles} />
                    </TabsList>
                </div>

                <TabsContent value="engine" className="m-0">
                    <ExitEngineWorkflow />
                </TabsContent>

                <TabsContent value="risk" className="m-0">
                    <SettingsPage onGotoExitEngine={() => { setTab("engine"); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
                </TabsContent>

                <TabsContent value="ai" className="m-0 space-y-6">
                    <Section icon={Wand2} title="Explain Exit Performance" subtitle="AI reads your closed trades and explains how your exits behaved">
                        <ExplainExit isOwner={isOwner} />
                    </Section>
                    <Section icon={Archive} title="Closed Trades History" subtitle="Which exit module actually closed each trade">
                        <ClosedTrades trades={trades} />
                    </Section>
                    <Section icon={FileText} title="Exit Reports (PDFs)" subtitle="Downloaded exit / trade reports — open, analyse or delete">
                        <AnantaPdfs isOwner={isOwner} />
                    </Section>
                </TabsContent>
            </Tabs>
        </div>
    );
}

function ETab({ value, label, icon: Icon }) {
    return (
        <TabsTrigger value={value} data-testid={`ee-subtab-${value}`}
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-atlas-cyan data-[state=active]:bg-transparent data-[state=active]:text-white text-atlas-textSecondary font-mono text-[11px] tracking-[0.2em] uppercase font-bold px-5 py-3 transition-colors hover:text-white flex items-center gap-2">
            <Icon className="w-4 h-4" strokeWidth={2} /> {label}
        </TabsTrigger>
    );
}

function ExplainExit({ isOwner }) {
    const [loading, setLoading] = useState(false);
    const [ans, setAns] = useState("");
    const run = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setLoading(true); setAns("");
        try {
            const r = await api.analyticsAiQuery(
                "Analyse ONLY my exit performance from closed trades: which exit modules closed trades, win rate and average P&L per exit type, and how much of the favourable move (MFE) my exits captured. Give 3 concrete suggestions to improve exits.",
                `exit-explain-${Date.now()}`);
            setAns(r?.answer || r?.response || "No analysis returned.");
        } catch (e) { toast.error("AI analysis failed", { description: String(e?.response?.data?.detail || e?.message) }); }
        finally { setLoading(false); }
    };
    return (
        <div className="panel border-atlas-border rounded-xl p-5">
            <button data-testid="ee-explain-run" onClick={run} disabled={loading}
                className="flex items-center gap-2 rounded-lg bg-atlas-cyan text-atlas-bg font-mono text-[11px] font-bold tracking-widest px-4 py-2.5 hover:brightness-110 transition-all disabled:opacity-50">
                {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />} EXPLAIN MY EXITS
            </button>
            {ans && <p className="mt-4 font-mono text-[12px] text-atlas-textSecondary leading-relaxed whitespace-pre-wrap" data-testid="ee-explain-answer">{ans}</p>}
        </div>
    );
}

function ClosedTrades({ trades }) {
    const closed = (trades || []).filter((t) => t.side === "SELL" && (t.status || "FILLED") === "FILLED" && t.pnl != null).slice(0, 15);
    return (
        <div className="panel border-atlas-border rounded-xl p-5" data-testid="ee-closed-history">
            {closed.length === 0 ? (
                <div className="py-6 text-center font-mono text-[11px] text-atlas-textTertiary">No closed trades yet.</div>
            ) : (
                <div className="rounded-lg border border-atlas-border divide-y divide-atlas-border max-h-72 overflow-y-auto atlas-scroll">
                    {closed.map((t) => (
                        <div key={t.id} className="px-3 py-2 flex items-center justify-between font-mono text-[11px]" data-testid="ee-closed-row">
                            <span className="text-atlas-text font-bold w-14">{(t.symbol || "").split("/")[0]}</span>
                            <span className="text-atlas-cyan text-[9px] uppercase w-24 truncate">{t.exit_module ? `mod ${t.exit_module}` : (t.exit_reason || "-")}</span>
                            <span className="text-atlas-textTertiary truncate mx-2 flex-1 text-right">{t.exit_reason || "-"}</span>
                            <span className={`tabular-nums font-bold w-20 text-right ${t.pnl > 0 ? "text-atlas-positive" : t.pnl < 0 ? "text-atlas-negative" : "text-atlas-textSecondary"}`}>{t.pnl >= 0 ? "+" : ""}${(t.pnl || 0).toFixed(2)}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function Section({ icon: Icon, title, subtitle, children }) {
    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2.5">
                <span className="w-9 h-9 rounded-xl grid place-items-center border border-atlas-border bg-atlas-cyan/5"><Icon className="w-4.5 h-4.5 text-atlas-cyan" /></span>
                <div><div className="font-heading text-lg text-atlas-text leading-none">{title}</div>
                    <div className="label-tag mt-1 text-[9px] text-atlas-textTertiary">{subtitle}</div></div>
            </div>
            {children}
        </div>
    );
}
