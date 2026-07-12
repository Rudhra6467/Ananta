import { useEffect, useRef, useState } from "react";
import { LayoutDashboard, CandlestickChart, Brain, FlaskConical, SlidersHorizontal } from "lucide-react";
import { Toaster } from "sonner";
import Dashboard from "@/pages/Dashboard";
import Trade from "@/pages/Trade";
import StrategyCenter from "@/pages/StrategyCenter";
import Research from "@/pages/Research";
import Workspace from "@/pages/Workspace";
import EnvironmentToggle from "@/components/EnvironmentToggle";
import TradeHistoryPdfDialog from "@/components/TradeHistoryPdfDialog";
import OwnerAuthControl from "@/components/OwnerAuthControl";
import AccountOverlay from "@/components/AccountOverlay";
import AnantaLogo from "@/components/AnantaLogo";
import OnboardingPipeline from "@/components/OnboardingPipeline";
import AskAnanta from "@/components/AskAnanta";
import SystemHealthChip from "@/components/SystemHealthChip";
import { useAuth } from "@/context/AuthContext";
import { useAccessGate } from "@/context/AccessGateContext";
import { AppDataProvider, useAppData } from "@/context/AppDataContext";

const TABS = [
    { id: "dashboard", label: "Cockpit", icon: LayoutDashboard, Component: Dashboard },
    { id: "trade", label: "Trade", icon: CandlestickChart, Component: Trade },
    { id: "strategies", label: "Strategy", icon: Brain, Component: StrategyCenter },
    { id: "research", label: "Research", icon: FlaskConical, Component: Research },
    { id: "workspace", label: "Workspace", icon: SlidersHorizontal, Component: Workspace },
];

/* Native-feed header physics: hides on scroll-down, glides back on scroll-up. */
function useHideOnScroll(threshold = 60) {
    const [hidden, setHidden] = useState(false);
    useEffect(() => {
        let lastY = window.scrollY;
        let ticking = false;
        const onScroll = () => {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(() => {
                const y = window.scrollY;
                if (y > lastY + 4 && y > threshold) setHidden(true);
                else if (y < lastY - 4) setHidden(false);
                lastY = y;
                ticking = false;
            });
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        return () => window.removeEventListener("scroll", onScroll);
    }, [threshold]);
    return hidden;
}

export default function AppShell() {
    return (
        <AppDataProvider>
            <Shell />
        </AppDataProvider>
    );
}

function Shell() {
    const { ready, isOwner } = useAuth();
    const { gate } = useAccessGate();
    const [active, setActive] = useState(0);
    const [dir, setDir] = useState(1);
    const touch = useRef(null);
    const hidden = useHideOnScroll(60);
    const [tourOpen, setTourOpen] = useState(false);

    // Onboarding tour. Owner: auto-open once per browser session, always re-launchable,
    // never permanently dismissed (no "don't show again"). Public: gated to the waitlist.
    useEffect(() => {
        if (isOwner && !sessionStorage.getItem("ananta_tour_seen")) setTourOpen(true);
        const onTour = () => { if (isOwner) setTourOpen(true); else gate("Guided onboarding tour"); };
        window.addEventListener("ananta:tour", onTour);
        return () => window.removeEventListener("ananta:tour", onTour);
    }, [isOwner, gate]);
    const closeTour = () => { sessionStorage.setItem("ananta_tour_seen", "1"); setTourOpen(false); };

    const go = (i) => {
        if (i < 0 || i >= TABS.length || i === active) return;
        setDir(i > active ? 1 : -1);
        setActive(i);
        window.scrollTo({ top: 0, behavior: "smooth" });
    };

    // Cross-page navigation bus (e.g. Workspace "Analyse" → Research tab).
    useEffect(() => {
        const onNav = (e) => {
            const idx = TABS.findIndex((t) => t.id === e.detail?.tabId);
            if (idx >= 0) go(idx);
        };
        window.addEventListener("ananta:navigate", onNav);
        return () => window.removeEventListener("ananta:navigate", onNav);
    }, [active]);

    const onTouchStart = (e) => {
        const t = e.touches[0];
        touch.current = { x: t.clientX, y: t.clientY };
    };
    const onTouchEnd = (e) => {
        if (!touch.current) return;
        const t = e.changedTouches[0];
        const dx = t.clientX - touch.current.x;
        const dy = t.clientY - touch.current.y;
        if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.4) {
            go(active + (dx < 0 ? 1 : -1));
        }
        touch.current = null;
    };

    const Active = TABS[active].Component;

    return (
        <div className="min-h-screen bg-atlas-bg text-white font-body grid-bg pb-24" data-testid="app-shell">
            <TopHeader active={active} ready={ready} isOwner={isOwner} hidden={hidden} />

            <main
                className="max-w-[1600px] mx-auto px-4 md:px-6 py-6 overflow-x-hidden"
                onTouchStart={onTouchStart}
                onTouchEnd={onTouchEnd}
                data-testid="swipe-container"
            >
                <div key={active} className={dir > 0 ? "page-enter-right" : "page-enter-left"}>
                    <Active />
                </div>
            </main>

            <BottomNav active={active} onSelect={go} />

            <OnboardingPipeline open={tourOpen} onClose={closeTour} />
            {["dashboard", "workspace"].includes(TABS[active].id) && <AskAnanta tab={TABS[active].id} />}


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

/* ---------------- Dynamic context top header (hide-on-scroll) ---------------- */
function TopHeader({ active, ready, isOwner, hidden }) {
    const { portfolio } = useAppData();
    const [accountOpen, setAccountOpen] = useState(false);

    return (
        <header
            className={`sticky top-0 z-30 backdrop-blur-xl bg-atlas-bg/90 border-b border-atlas-border transition-transform duration-300 will-change-transform ${
                hidden ? "-translate-y-full" : "translate-y-0"
            }`}
            data-testid="app-header"
        >
            <div className="max-w-[1600px] mx-auto px-4 md:px-6 pt-3">
                {/* Row 1 — brand + master controls (compact so the wordmark never clips) */}
                <div className="flex items-center justify-between gap-2">
                    <button
                        type="button"
                        data-testid="ananta-logo-btn"
                        onClick={() => setAccountOpen(true)}
                        title="Account & privacy"
                        className="flex items-center gap-2 shrink-0 -ml-1.5 pl-1.5 pr-2.5 py-1 rounded-lg border border-transparent hover:border-atlas-border hover:bg-atlas-panelHover active:scale-95 transition-all group"
                    >
                        <span className="text-atlas-text" data-testid="ananta-emblem">
                            <AnantaLogo className="h-7 w-7 md:h-9 md:w-9 select-none transition-transform group-hover:scale-105" />
                        </span>
                        <span className="font-heading font-semibold tracking-tight text-sm md:text-base leading-none text-atlas-text">Ananta</span>
                    </button>
                    <div className="flex items-center gap-1.5 shrink-0">
                        <EnvironmentToggle />
                        <TradeHistoryPdfDialog />
                        <OwnerAuthControl />
                    </div>
                </div>

                {/* Row 2 — per-tab context */}
                <div className="py-3" data-testid="context-header">
                    <ContextInfo active={active} portfolio={portfolio} />
                </div>
            </div>

            {ready && !isOwner && (
                <div className="bg-atlas-cyan/10 border-t border-atlas-cyan/30 text-atlas-cyan" data-testid="readonly-banner">
                    <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-1 font-mono text-[9px] uppercase tracking-[0.15em] text-center">
                        Public read-only view · log in as owner to configure & control
                    </div>
                </div>
            )}

            <AccountOverlay open={accountOpen} onOpenChange={setAccountOpen} />
        </header>
    );
}

function ContextInfo({ active, portfolio }) {
    const id = TABS[active].id;
    const QUESTION = {
        dashboard: "What is happening right now?",
        trade: "What am I trading right now?",
        strategies: "What strategies do I own?",
        research: "Does my strategy actually work?",
        workspace: "How is Ananta set up?",
    };

    if (id === "dashboard") {
        const equity = portfolio?.equity ?? 0;
        const deployed = portfolio?.positions_value ?? 0;
        const slots = portfolio?.slots_used ?? 0;
        const dailyPct = portfolio?.daily_pnl_pct ?? 0;
        return (
            <div data-testid="context-cockpit">
                <div className="label-tag text-[9px] text-atlas-cyan/70 mb-1.5" data-testid="page-question">{QUESTION.dashboard}</div>
                <div className="flex items-center gap-5 md:gap-8 overflow-x-auto atlas-scroll">
                    <Metric label="ACCOUNT VALUE" value={`$${equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} big />
                    <Metric label="DEPLOYED" value={`$${deployed.toFixed(2)}`} sub={`(${slots})`} />
                    <Metric label="DAILY P&L"
                        value={`${dailyPct > 0 ? "+" : ""}${dailyPct.toFixed(2)}%`}
                        cls={dailyPct > 0.005 ? "text-atlas-positive" : dailyPct < -0.005 ? "text-atlas-negative" : "text-atlas-text"} />
                    <div className="ml-auto shrink-0 self-center"><SystemHealthChip /></div>
                </div>
            </div>
        );
    }

    if (id === "trade") {
        const positions = (portfolio?.positions || []).filter((p) => p.quantity > 0);
        const invested = positions.reduce((a, p) => a + (p.avg_cost || 0) * (p.quantity || 0), 0);
        const current = positions.reduce((a, p) => a + (p.market_value || (p.last_price || 0) * (p.quantity || 0)), 0);
        const pnl = current - invested;
        const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0;
        const cls = pnl > 0 ? "text-atlas-positive" : pnl < 0 ? "text-atlas-negative" : "text-atlas-text";
        return (
            <div data-testid="context-trade">
                <div className="label-tag text-[9px] text-atlas-cyan/70 mb-1.5" data-testid="page-question">{QUESTION.trade}</div>
                <div className="flex items-center gap-5 md:gap-8 overflow-x-auto atlas-scroll">
                    <Metric label="INVESTED" value={invested.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} big />
                    <Metric label="CURRENT" value={current.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} />
                    <Metric label="P&L" value={`${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`} sub={`${pnl >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`} cls={cls} />
                </div>
            </div>
        );
    }

    const title = id === "strategies" ? "Strategy Center" : id === "research" ? "Research Lab" : "Workspace";
    return (
        <div data-testid={`context-${id}`}>
            <div className="label-tag text-[9px] text-atlas-cyan/70 mb-1" data-testid="page-question">{QUESTION[id]}</div>
            <h1 className="font-heading font-light text-2xl md:text-3xl tracking-tight text-atlas-text leading-none">{title}</h1>
        </div>
    );
}

function Metric({ label, value, sub, cls = "text-atlas-text", big = false }) {
    return (
        <div className="shrink-0">
            <div className="label-tag text-[9px]">{label}</div>
            <div className={`font-mono tabular-nums font-medium mt-0.5 ${big ? "text-xl md:text-2xl font-light" : "text-base md:text-lg"} ${cls}`}>
                {value} {sub && <span className="text-atlas-textTertiary text-xs">{sub}</span>}
            </div>
        </div>
    );
}

/* ---------------- Sticky bottom tab bar — prominent active state ---------------- */
function BottomNav({ active, onSelect }) {
    return (
        <nav className="fixed bottom-0 left-0 right-0 z-40 bg-atlas-bg/95 backdrop-blur-xl border-t border-atlas-border shadow-[0_-8px_24px_-12px_rgba(0,0,0,0.9)]" data-testid="bottom-nav">
            <div className="max-w-[1600px] mx-auto grid grid-cols-5">
                {TABS.map((t, i) => {
                    const Icon = t.icon;
                    const on = active === i;
                    return (
                        <button
                            key={t.id}
                            data-testid={`bottom-nav-${t.id}`}
                            aria-current={on ? "page" : undefined}
                            onClick={() => onSelect(i)}
                            className="relative flex flex-col items-center justify-center gap-1 pt-2 pb-2.5 transition-colors"
                        >
                            {on && <span className="absolute top-0 left-1/2 -translate-x-1/2 w-10 h-0.5 rounded-full bg-atlas-cyan" />}
                            <span className={`flex items-center justify-center rounded-full transition-all duration-200 ${on ? "bg-atlas-cyan/20 px-3.5 py-1.5" : "px-3.5 py-1.5"}`}>
                                <Icon
                                    className={`transition-all ${on ? "w-[22px] h-[22px] text-atlas-cyan" : "w-5 h-5 text-atlas-textTertiary"}`}
                                    strokeWidth={on ? 2.4 : 1.8}
                                    fill={on ? "currentColor" : "none"}
                                    fillOpacity={on ? 0.18 : 0}
                                />
                            </span>
                            <span className={`font-mono text-[9px] tracking-wide uppercase transition-colors ${on ? "text-atlas-cyan font-bold" : "text-atlas-textTertiary font-medium"}`}>
                                {t.label}
                            </span>
                        </button>
                    );
                })}
            </div>
        </nav>
    );
}
