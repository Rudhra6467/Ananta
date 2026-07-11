import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, ArrowRight, Sparkles, Mail, User } from "lucide-react";
import { toast } from "sonner";
import AnantaLogo from "@/components/AnantaLogo";
import { useAccessGate } from "@/context/AccessGateContext";
import api from "@/lib/api";

const TEAL = "#14E0C9";

export default function SignUp() {
    const navigate = useNavigate();
    const { isOwner } = useAccessGate();
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [busy, setBusy] = useState(false);

    const goHome = () => navigate("/");

    const submit = async () => {
        // Owner never needs to join the waitlist — straight into the app.
        if (isOwner) { goHome(); return; }
        if (!name.trim() || !email.trim()) { toast.error("Please enter your name and email."); return; }
        setBusy(true);
        try {
            const r = await api.accessRequest({ name: name.trim(), email: email.trim(), feature: "Sign Up", platform: "web" });
            toast.success(r.already_on_list ? "You're already on the list — welcome back!" : "You're on the waitlist!");
            goHome();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Could not submit. Please try again.");
            setBusy(false);
        }
    };

    return (
        <div className="relative h-screen overflow-hidden bg-atlas-bg text-atlas-text" data-testid="signup-page">
            {/* backdrop */}
            <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.5]"
                style={{ backgroundImage: "linear-gradient(rgba(20,224,201,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(20,224,201,0.06) 1px, transparent 1px)", backgroundSize: "46px 46px", maskImage: "radial-gradient(ellipse 80% 60% at 50% 40%, #000 40%, transparent 100%)" }} />
            <div aria-hidden className="pointer-events-none absolute -top-40 left-1/2 h-[420px] w-[620px] -translate-x-1/2 rounded-full blur-[120px]" style={{ background: "radial-gradient(circle, rgba(20,224,201,0.18), transparent 70%)" }} />

            <div className="relative z-10 mx-auto flex h-full max-w-md flex-col items-center justify-center px-5">
                {/* Brand */}
                <button data-testid="signup-brand" onClick={goHome} className="group mb-8 flex items-center gap-3">
                    <span className="grid place-items-center rounded-full border border-atlas-border bg-atlas-panel/50 p-1.5 transition-transform group-hover:scale-105" style={{ boxShadow: `0 0 24px -6px ${TEAL}55` }}>
                        <AnantaLogo className="h-12 w-12" />
                    </span>
                    <span className="font-heading text-4xl font-semibold tracking-tight">Ananta</span>
                </button>

                <h1 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl">Create your account</h1>
                <p className="mt-3 text-center text-sm text-atlas-textSecondary sm:text-base">
                    Join the waitlist and start your 24/7 AI trading journey.
                </p>

                <div className="mt-8 w-full space-y-3">
                    <div className="flex items-center gap-3 rounded-xl border border-atlas-border bg-atlas-panel/60 px-4 py-3.5 focus-within:border-atlas-cyan transition-colors">
                        <User className="h-4 w-4 text-atlas-textTertiary" />
                        <input data-testid="signup-name" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)}
                            className="flex-1 bg-transparent font-mono text-sm text-white outline-none placeholder:text-atlas-textTertiary" />
                    </div>
                    <div className="flex items-center gap-3 rounded-xl border border-atlas-border bg-atlas-panel/60 px-4 py-3.5 focus-within:border-atlas-cyan transition-colors">
                        <Mail className="h-4 w-4 text-atlas-textTertiary" />
                        <input data-testid="signup-email" type="email" placeholder="you@email.com" value={email} onChange={(e) => setEmail(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && submit()}
                            className="flex-1 bg-transparent font-mono text-sm text-white outline-none placeholder:text-atlas-textTertiary" />
                    </div>
                    <button data-testid="signup-submit" onClick={submit} disabled={busy}
                        className="flex w-full items-center justify-center gap-2 rounded-full py-4 font-heading text-base font-bold text-black transition-all hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
                        style={{ backgroundColor: TEAL, boxShadow: `0 10px 30px -8px ${TEAL}80` }}>
                        {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <>Get Started <ArrowRight className="h-4 w-4" /></>}
                    </button>
                </div>

                <div className="mt-6 flex items-center gap-2 font-mono text-[11px] text-atlas-textTertiary">
                    <Sparkles className="h-3.5 w-3.5" style={{ color: TEAL }} />
                    Institutional-grade algorithmic trading, made approachable.
                </div>
            </div>

            {/* Skip to homepage — bottom right */}
            <button data-testid="signup-skip-to-homepage" onClick={goHome}
                className="fixed bottom-5 right-5 z-20 inline-flex items-center gap-1.5 rounded-full border border-atlas-border bg-atlas-panel/60 px-4 py-2 font-mono text-[11px] text-atlas-textSecondary backdrop-blur transition-colors hover:border-atlas-textTertiary hover:text-atlas-text">
                Skip to homepage <ArrowRight className="h-3.5 w-3.5" />
            </button>
        </div>
    );
}
