import { useEffect, useState } from "react";
import { Activity, Briefcase, Database, Settings as SettingsIcon, ShieldHalf } from "lucide-react";
import { Toaster } from "sonner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import Dashboard from "@/pages/Dashboard";
import Portfolio from "@/pages/Portfolio";
import Reports from "@/pages/Reports";
import SettingsPage from "@/pages/Settings";
import EnvironmentToggle from "@/components/EnvironmentToggle";
import TradeHistoryPdfDialog from "@/components/TradeHistoryPdfDialog";
import OwnerAuthControl from "@/components/OwnerAuthControl";
import anantaEmblem from "@/assets/ananta-emblem.png";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";

const NAV = [
    { id: "dashboard", label: "COCKPIT", icon: Activity },
    { id: "portfolio", label: "PORTFOLIO", icon: Briefcase },
    { id: "reports", label: "DATALOGS / REPORTS", icon: Database },
    { id: "settings", label: "SETTINGS", icon: SettingsIcon },
];

export default function AppShell() {
    const [tab, setTab] = useState("dashboard");
    const [health, setHealth] = useState(null);
    const [now, setNow] = useState(new Date());
    const { isOwner, ready } = useAuth();

    useEffect(() => {
        api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
        const t = setInterval(() => setNow(new Date()), 1000);
        return () => clearInterval(t);
    }, []);

    return (
        <div className="min-h-screen bg-atlas-bg text-white font-body grid-bg" data-testid="app-shell">
            {/* Top bar */}
            <header
                className="sticky top-0 z-30 backdrop-blur-xl bg-atlas-bg/70 border-b border-atlas-border"
                data-testid="app-header"
            >
                <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-3 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <img
                            src={anantaEmblem}
                            alt="Ananta"
                            data-testid="ananta-emblem"
                            className="h-10 w-10 md:h-11 md:w-11 object-contain select-none"
                            draggable={false}
                        />
                        <div>
                            <div className="font-heading font-semibold tracking-tight text-base md:text-lg leading-none text-atlas-text">
                                Ananta
                            </div>
                            <div className="label-tag mt-1 text-[9px] text-atlas-textSecondary">
                                ALGORITHMIC EXECUTION COCKPIT
                            </div>
                        </div>
                    </div>
                    {/* Master environment switch — always visible */}
                    <div className="flex items-center gap-3">
                        <EnvironmentToggle />
                        <TradeHistoryPdfDialog />
                        <OwnerAuthControl />
                        <div className="hidden md:flex items-center gap-3">
                            <StatusPill
                                label="ENGINE"
                                ok={health && health.status === "running"}
                                data-testid="engine-status-pill"
                            />
                            <div className="font-mono text-xs text-atlas-textSecondary">
                                {now.toISOString().replace("T", " ").slice(0, 19)} UTC
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            {ready && !isOwner && (
                <div
                    className="bg-atlas-cyan/10 border-b border-atlas-cyan/30 text-atlas-cyan"
                    data-testid="readonly-banner"
                >
                    <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-1.5 font-mono text-[10px] uppercase tracking-[0.15em] text-center">
                        Public read-only view · log in as owner to configure & control
                    </div>
                </div>
            )}

            {/* Tabs */}
            <main className="max-w-[1600px] mx-auto px-4 md:px-6 py-6">
                <Tabs value={tab} onValueChange={setTab} className="atlas-tabs">
                    <TabsList className="bg-transparent border-b border-atlas-border w-full justify-start gap-0 rounded-none h-auto p-0 mb-6 overflow-x-auto atlas-scroll flex-nowrap">
                        {NAV.map((n) => {
                            const Icon = n.icon;
                            return (
                                <TabsTrigger
                                    key={n.id}
                                    value={n.id}
                                    data-testid={`nav-tab-${n.id}`}
                                    className="shrink-0 rounded-none border-b-2 border-transparent data-[state=active]:border-atlas-cyan data-[state=active]:bg-transparent data-[state=active]:text-white text-atlas-textSecondary font-mono text-[10px] md:text-[11px] tracking-[0.15em] md:tracking-[0.2em] uppercase font-bold px-3.5 md:px-5 py-3 transition-colors duration-150 hover:text-white"
                                >
                                    <Icon className="w-4 h-4 mr-1.5 md:mr-2" strokeWidth={2} />
                                    {n.label}
                                </TabsTrigger>
                            );
                        })}
                    </TabsList>

                    <TabsContent value="dashboard" className="m-0">
                        <Dashboard />
                    </TabsContent>
                    <TabsContent value="portfolio" className="m-0">
                        <Portfolio />
                    </TabsContent>
                    <TabsContent value="reports" className="m-0">
                        <Reports />
                    </TabsContent>
                    <TabsContent value="settings" className="m-0">
                        <SettingsPage />
                    </TabsContent>
                </Tabs>
            </main>

            <footer className="border-t border-atlas-border mt-12">
                <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-4 flex items-center justify-between text-[10px] font-mono text-atlas-textTertiary">
                    <div>ANANTA · ALGORITHMIC SWING EXECUTION · PAPER VALIDATION · CAPITAL PRESERVATION FIRST</div>
                    <div className="flex items-center gap-2">
                        <ShieldHalf className="w-3 h-3" />
                        <span>TECHNICAL-FIRST · EXPLAINABLE · DEFENSIVE ARCHITECTURE</span>
                    </div>
                </div>
            </footer>
            <Toaster
                position="top-right"
                theme="dark"
                toastOptions={{
                    style: {
                        background: "#121418",
                        border: "1px solid #2A2D35",
                        color: "#E2E4E9",
                        borderRadius: 6,
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 12,
                    },
                }}
            />
        </div>
    );
}

function StatusPill({ label, ok }) {
    return (
        <div className="flex items-center gap-2" data-testid="engine-status-pill">
            <span className="label-tag text-[9px]">{label}</span>
            <span
                className={`inline-flex items-center gap-1.5 font-mono text-[11px] font-bold px-2 py-0.5 ${
                    ok ? "text-atlas-positive" : "text-atlas-negative"
                }`}
            >
                <span
                    className={`w-1.5 h-1.5 rounded-full ${
                        ok ? "bg-atlas-positive glow-green" : "bg-atlas-negative glow-red"
                    }`}
                />
                {ok ? "ONLINE" : "OFFLINE"}
            </span>
        </div>
    );
}
