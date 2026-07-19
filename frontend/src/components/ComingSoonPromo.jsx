import { useEffect, useState } from "react";
import { Trophy, Store, FileBarChart2, TrendingUp, Loader2, Check } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import api from "@/lib/api";

// "Coming Soon to Ananta" promo — pure HTML/CSS (no baked image), crisp text.
//  - variant "sheet"  : first-login welcome modal on the Cockpit. Non-owner: first 3 sessions.
//                       Owner: every login (per-session, reset on login in AuthContext).
//  - variant "inline" : embeddable card (default) — reusable if needed elsewhere.
// Waitlist opt-in (+ email) is persisted server-side.

const KEY = "ananta_promo_coming_soon_v1";
const SESSION_KEY = "ananta_welcome_shown";
const MAX_VIEWS = 3;

const FEATURES = [
    { icon: Trophy, title: "Weekly AI Trading Championship", bullets: ["$100k virtual balance", "Real prizes in trading credits", "Risk-adjusted leaderboards"] },
    { icon: Store, title: "Strategy Marketplace", bullets: ["Discover & follow community strategies", "Paper-trade before you deploy", "Verified badges — battle-tested"] },
    { icon: FileBarChart2, title: "Advanced AI Strategy Reports", bullets: ["Deep performance breakdown", "MFE capture & regime analysis", "What-If comparisons"] },
];

function readState() {
    try { return JSON.parse(localStorage.getItem(KEY)) || { views: 0, dismissed: false }; }
    catch { return { views: 0, dismissed: false }; }
}
function writeState(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ } }

function PromoCard() {
    return (
        <div className="rounded-2xl border border-atlas-cyan/25 bg-gradient-to-b from-atlas-panel to-atlas-bg p-5 space-y-5" data-testid="promo-card">
            <div className="text-center space-y-1.5">
                <div className="mx-auto w-11 h-11 rounded-xl bg-atlas-cyan/15 grid place-items-center"><TrendingUp className="w-5 h-5 text-atlas-cyan" strokeWidth={2.5} /></div>
                <h3 className="font-heading font-light text-2xl text-atlas-text leading-tight">Coming Soon to Ananta</h3>
                <p className="font-mono text-[11px] text-atlas-textTertiary">Three big upgrades on the roadmap</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {FEATURES.map(({ icon: Icon, title, bullets }) => (
                    <div key={title} className="rounded-xl border border-atlas-border bg-atlas-bg/60 p-3.5 space-y-2.5">
                        <span className="w-9 h-9 rounded-lg bg-atlas-cyan/15 grid place-items-center"><Icon className="w-4 h-4 text-atlas-cyan" /></span>
                        <div className="font-heading font-medium text-atlas-text text-sm leading-tight">{title}</div>
                        <ul className="space-y-1.5">
                            {bullets.map((b) => (
                                <li key={b} className="flex gap-1.5 font-body text-[11px] text-atlas-textSecondary leading-snug">
                                    <span className="text-atlas-cyan shrink-0">•</span><span>{b}</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                ))}
            </div>
            <div className="rounded-xl border border-atlas-cyan/20 bg-atlas-cyan/5 py-2.5 text-center font-mono text-xs font-bold tracking-wide text-atlas-cyan">
                Stay Tuned — Major Updates Coming Soon
            </div>
        </div>
    );
}

function Waitlist() {
    const [joined, setJoined] = useState(false);
    const [joining, setJoining] = useState(false);
    const [email, setEmail] = useState("");

    useEffect(() => { api.promoStatus().then((s) => setJoined(!!s.waitlist_joined)).catch(() => {}); }, []);

    const join = async () => {
        const value = email.trim();
        if (!value || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) { toast.error("Enter a valid email to join the waitlist."); return; }
        setJoining(true);
        try { await api.promoJoinWaitlist(value); setJoined(true); toast.success("You're on the waitlist — we'll be in touch!"); }
        catch { toast.error("Could not join the waitlist. Please try again."); }
        finally { setJoining(false); }
    };

    if (joined) {
        return (
            <div data-testid="promo-joined" className="flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-atlas-cyan/10 border border-atlas-cyan/30 text-atlas-cyan font-body text-sm font-semibold">
                <Check className="w-4 h-4" /> You&apos;re on the early-access waitlist
            </div>
        );
    }
    return (
        <div className="flex flex-col sm:flex-row gap-2">
            <input
                data-testid="promo-email-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") join(); }} placeholder="you@email.com"
                className="flex-1 rounded-lg bg-atlas-bg border border-atlas-border px-3 py-2.5 font-mono text-sm text-atlas-text outline-none focus:border-atlas-cyan transition-colors placeholder:text-atlas-textTertiary"
            />
            <button
                type="button" data-testid="promo-join-waitlist" onClick={join} disabled={joining}
                className="flex items-center justify-center gap-1.5 px-5 py-2.5 rounded-lg bg-atlas-cyan text-atlas-bg font-body text-sm font-semibold hover:bg-atlas-cyan/90 transition-colors disabled:opacity-70"
            >
                {joining ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Join Waitlist
            </button>
        </div>
    );
}

export default function ComingSoonPromo({ variant = "inline", isOwner = false }) {
    const [sheetOpen, setSheetOpen] = useState(false);

    useEffect(() => {
        if (variant !== "sheet") return;
        if (sessionStorage.getItem(SESSION_KEY)) return;
        const st = readState();
        const show = isOwner ? true : (!st.dismissed && st.views < MAX_VIEWS);
        if (!show) return;
        sessionStorage.setItem(SESSION_KEY, "1");
        if (!isOwner) writeState({ ...st, views: st.views + 1 });
        setSheetOpen(true);
    }, [variant, isOwner]);

    if (variant === "sheet") {
        return (
            <Dialog open={sheetOpen} onOpenChange={setSheetOpen}>
                <DialogContent className="bg-atlas-panel border-atlas-border max-w-lg p-0 gap-0 overflow-hidden" data-testid="cockpit-welcome-sheet">
                    <DialogHeader className="sr-only">
                        <DialogTitle>Coming Soon to Ananta</DialogTitle>
                        <DialogDescription>Upcoming Ananta features and early-access waitlist.</DialogDescription>
                    </DialogHeader>
                    <div className="max-h-[82vh] overflow-y-auto atlas-scroll p-4 space-y-4">
                        <PromoCard />
                        <Waitlist />
                        <button
                            type="button" data-testid="welcome-sheet-continue" onClick={() => setSheetOpen(false)}
                            className="w-full py-2.5 rounded-lg border border-atlas-border text-atlas-textSecondary font-body text-sm font-medium hover:text-atlas-text hover:border-atlas-textTertiary transition-colors"
                        >
                            Continue to Cockpit
                        </button>
                    </div>
                </DialogContent>
            </Dialog>
        );
    }

    return (
        <div data-testid="promo-inline" className="space-y-4">
            <PromoCard />
            <Waitlist />
        </div>
    );
}
