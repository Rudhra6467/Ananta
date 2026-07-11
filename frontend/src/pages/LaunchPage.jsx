import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Menu, UserCircle2, Play, Network, BrainCircuit, FlaskConical, ArrowRight, Sparkles, X } from "lucide-react";
import AnantaLogo from "@/components/AnantaLogo";
import { useAccessGate } from "@/context/AccessGateContext";

const TEAL = "#14E0C9";

const FEATURES = [
    {
        icon: Network,
        color: "#F43F5E",
        title: "100+ Built-in & Importable Trading Strategies",
        desc: "Start with a curated library or import your own strategies in seconds.",
    },
    {
        icon: BrainCircuit,
        color: "#FB7185",
        title: "Your 24/7 AI Trading Assistant",
        desc: "Simplifies analysis, explains decisions, and helps you trade with greater confidence.",
    },
    {
        icon: FlaskConical,
        color: "#10B981",
        title: "Research Lab with Real Market Validation",
        desc: "Backtest, optimize, and verify every strategy using historical market data before risking capital.",
    },
];

export default function LaunchPage() {
    const navigate = useNavigate();
    const { isOwner } = useAccessGate();
    const [menuOpen, setMenuOpen] = useState(false);

    // Owner → straight into the app; public → sign-up funnel (waitlist).
    const act = () => navigate(isOwner ? "/" : "/signup");
    const goHome = () => navigate("/");

    return (
        <div className="relative h-screen overflow-hidden bg-atlas-bg text-atlas-text">
            {/* subtle grid + teal glow backdrop */}
            <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.5]"
                style={{ backgroundImage: "linear-gradient(rgba(20,224,201,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(20,224,201,0.06) 1px, transparent 1px)", backgroundSize: "46px 46px", maskImage: "radial-gradient(ellipse 80% 60% at 50% 40%, #000 40%, transparent 100%)" }} />
            <div aria-hidden className="pointer-events-none absolute -top-40 left-1/2 h-[420px] w-[620px] -translate-x-1/2 rounded-full blur-[120px]" style={{ background: "radial-gradient(circle, rgba(20,224,201,0.18), transparent 70%)" }} />

            <div className="relative z-10 mx-auto flex h-full max-w-3xl flex-col px-5">
                {/* ---------- Header ---------- */}
                <header className="flex shrink-0 items-center justify-between gap-3 pt-4">
                    <div className="relative">
                        <button data-testid="launch-menu-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="Menu"
                            className="grid h-10 w-10 place-items-center rounded-xl border border-atlas-border bg-atlas-panel/60 text-atlas-textSecondary transition-colors hover:text-atlas-text hover:border-atlas-textTertiary">
                            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                        </button>
                        {menuOpen && (
                            <div data-testid="launch-menu" className="absolute left-0 top-full z-20 mt-2 w-52 rounded-xl border border-atlas-border bg-atlas-panel p-1.5 shadow-2xl">
                                {[
                                    { label: "Start Free Trial", fn: act },
                                    { label: "Watch Demo", fn: act },
                                    { label: "Owner Login", fn: goHome },
                                    { label: "Skip to Homepage", fn: goHome },
                                ].map((m) => (
                                    <button key={m.label} data-testid={`launch-menu-${m.label.toLowerCase().replace(/\s+/g, "-")}`}
                                        onClick={() => { setMenuOpen(false); m.fn(); }}
                                        className="flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left font-mono text-[12px] text-atlas-textSecondary transition-colors hover:bg-atlas-panelHover hover:text-atlas-text">
                                        {m.label} <ArrowRight className="h-3.5 w-3.5 opacity-50" />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Brand */}
                    <button data-testid="launch-brand" onClick={goHome} className="group flex items-center gap-3">
                        <span className="grid place-items-center rounded-full border border-atlas-border bg-atlas-panel/50 p-1.5 transition-transform group-hover:scale-105" style={{ boxShadow: `0 0 24px -6px ${TEAL}55` }}>
                            <AnantaLogo className="h-11 w-11 md:h-14 md:w-14" />
                        </span>
                        <span className="font-heading text-3xl font-semibold tracking-tight md:text-5xl">Ananta</span>
                    </button>

                    <button data-testid="launch-profile" onClick={act} aria-label="Account"
                        className="grid h-10 w-10 place-items-center rounded-full border border-atlas-border bg-atlas-panel/60 text-atlas-textSecondary transition-colors hover:text-atlas-text hover:border-atlas-textTertiary">
                        <UserCircle2 className="h-6 w-6" />
                    </button>
                </header>

                {/* ---------- Hero ---------- */}
                <main className="flex flex-1 flex-col items-center justify-center text-center">
                    <h1 className="font-heading text-4xl font-bold leading-[1.05] tracking-tight sm:text-5xl">
                        Your 24/7 AI<br />Trading Assistant
                    </h1>
                    <p className="mt-3 max-w-md text-sm text-atlas-textSecondary sm:text-base">
                        Automate strategies and find alpha effortlessly.
                    </p>

                    <div className="mt-6 flex w-full max-w-md flex-col items-center justify-center gap-3 sm:flex-row">
                        <button data-testid="cta-start-free-trial" onClick={act}
                            className="w-full rounded-full py-3.5 font-heading text-base font-bold text-black transition-all hover:brightness-110 active:scale-[0.98] sm:w-auto sm:px-10"
                            style={{ backgroundColor: TEAL, boxShadow: `0 10px 30px -8px ${TEAL}80` }}>
                            Start Free Trial
                        </button>
                        <button data-testid="cta-watch-video" onClick={act}
                            className="flex w-full items-center justify-center gap-3 rounded-full border border-atlas-border py-3.5 text-atlas-text transition-colors hover:border-atlas-textTertiary sm:w-auto sm:px-8">
                            <span className="grid h-8 w-8 place-items-center rounded-full border border-atlas-border">
                                <Play className="h-4 w-4" style={{ color: TEAL }} />
                            </span>
                            <span className="text-left leading-tight">
                                <span className="block font-heading text-sm font-semibold">Watch Video</span>
                                <span className="block font-mono text-[11px] text-atlas-textTertiary">3min</span>
                            </span>
                        </button>
                    </div>

                    {/* ---------- Feature cards ---------- */}
                    <div className="mt-7 w-full space-y-2.5">
                        {FEATURES.map((f) => (
                            <button key={f.title} data-testid={`feature-card-${f.title.split(" ")[0].toLowerCase()}`}
                                onClick={act}
                                className="group flex w-full items-start gap-4 rounded-2xl border border-atlas-border bg-atlas-panel/50 p-4 text-left transition-all hover:border-atlas-textTertiary hover:bg-atlas-panelHover/60">
                                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border" style={{ borderColor: `${f.color}44`, backgroundColor: `${f.color}18` }}>
                                    <f.icon className="h-5 w-5" style={{ color: f.color }} />
                                </span>
                                <span className="flex-1">
                                    <span className="block font-heading text-sm font-semibold text-atlas-text sm:text-base">{f.title}</span>
                                    <span className="mt-0.5 block text-xs leading-relaxed text-atlas-textSecondary sm:text-sm">{f.desc}</span>
                                </span>
                                <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-atlas-textTertiary transition-transform group-hover:translate-x-1" />
                            </button>
                        ))}
                    </div>

                    <div className="mt-6 flex items-center gap-2 font-mono text-[11px] text-atlas-textTertiary">
                        <Sparkles className="h-3.5 w-3.5" style={{ color: TEAL }} />
                        Institutional-grade algorithmic trading, made approachable.
                    </div>
                </main>
            </div>

            {/* Skip to homepage — bottom right */}
            <button data-testid="skip-to-homepage" onClick={goHome}
                className="fixed bottom-5 right-5 z-20 inline-flex items-center gap-1.5 rounded-full border border-atlas-border bg-atlas-panel/60 px-4 py-2 font-mono text-[11px] text-atlas-textSecondary backdrop-blur transition-colors hover:border-atlas-textTertiary hover:text-atlas-text">
                Skip to homepage <ArrowRight className="h-3.5 w-3.5" />
            </button>
        </div>
    );
}
