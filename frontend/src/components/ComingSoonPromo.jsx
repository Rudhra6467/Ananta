import { useEffect, useState } from "react";
import { X, Trophy, Store, FileBarChart2, Sparkles, Loader2, Check } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import api from "@/lib/api";

// "Coming Soon to Ananta" promo. Two variants:
//  - "banner"  : dismissible, shows only on the first 3 sessions (client-tracked), used at top of Account.
//  - "section" : permanent "What's Coming" card inside Account (always visible).
// Waitlist opt-in is persisted server-side; view-count/dismiss are a per-device UX nudge.

const KEY = "ananta_promo_coming_soon_v1";
const MAX_VIEWS = 3;

const FEATURES = [
    { icon: Trophy, title: "Weekly AI Trading Championship", desc: "Compete on a level field with a virtual balance. Climb risk-adjusted leaderboards and win real trading credits every week." },
    { icon: Store, title: "Strategy Marketplace", desc: "Discover, follow and paper-trade community strategies with verified track records before you deploy a cent." },
    { icon: FileBarChart2, title: "Advanced AI Strategy Reports", desc: "Automated deep-dives — regime analysis, MFE capture, exit-module performance and What-If comparisons — so you always know what to fix." },
];

function readState() {
    try { return JSON.parse(localStorage.getItem(KEY)) || { views: 0, dismissed: false }; }
    catch { return { views: 0, dismissed: false }; }
}
function writeState(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ } }

export default function ComingSoonPromo({ variant = "section", onClose }) {
    const [showBanner, setShowBanner] = useState(false);
    const [learnOpen, setLearnOpen] = useState(false);
    const [joined, setJoined] = useState(false);
    const [joining, setJoining] = useState(false);

    useEffect(() => { api.promoStatus().then((s) => setJoined(!!s.waitlist_joined)).catch(() => {}); }, []);

    useEffect(() => {
        if (variant !== "banner") return;
        const st = readState();
        if (st.dismissed || st.views >= MAX_VIEWS) { setShowBanner(false); return; }
        setShowBanner(true);
        if (!sessionStorage.getItem("ananta_promo_counted")) {
            sessionStorage.setItem("ananta_promo_counted", "1");
            writeState({ ...st, views: st.views + 1 });
        }
    }, [variant]);

    const dismiss = () => { writeState({ ...readState(), dismissed: true }); setShowBanner(false); onClose?.(); };
    const join = async () => {
        setJoining(true);
        try { await api.promoJoinWaitlist(); setJoined(true); toast.success("You're on the waitlist — we'll be in touch!"); }
        catch { toast.error("Could not join the waitlist. Please try again."); }
        finally { setJoining(false); }
    };

    if (variant === "banner" && !showBanner) return null;

    const Buttons = (
        <div className="flex items-center gap-2">
            <button
                type="button" data-testid="promo-join-waitlist" onClick={join} disabled={joining || joined}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-atlas-cyan text-atlas-bg font-body text-sm font-semibold hover:bg-atlas-cyan/90 transition-colors disabled:opacity-70"
            >
                {joining ? <Loader2 className="w-4 h-4 animate-spin" /> : joined ? <Check className="w-4 h-4" /> : null}
                {joined ? "On the waitlist" : "Join Waitlist"}
            </button>
            <button
                type="button" data-testid="promo-learn-more" onClick={() => setLearnOpen(true)}
                className="flex-1 py-2.5 rounded-lg border border-atlas-cyan/40 text-atlas-cyan font-body text-sm font-semibold hover:bg-atlas-cyan/10 transition-colors"
            >
                Learn More
            </button>
        </div>
    );

    const Hero = (
        <div className="relative rounded-lg overflow-hidden border border-atlas-cyan/20">
            <img src="/promo/coming-soon.jpg" alt="Coming soon to Ananta" className="w-full block" loading="lazy" />
            <div className="absolute inset-0 bg-gradient-to-t from-atlas-bg/70 via-transparent to-transparent pointer-events-none" />
        </div>
    );

    return (
        <div data-testid={`promo-${variant}`}>
            {variant === "banner" ? (
                <div className="relative rounded-xl border border-atlas-cyan/25 bg-atlas-bg p-3 space-y-3">
                    <button
                        type="button" data-testid="promo-dismiss" onClick={dismiss} aria-label="Dismiss"
                        className="absolute top-2 right-2 z-10 w-7 h-7 rounded-full bg-atlas-panel/80 border border-atlas-border flex items-center justify-center text-atlas-textTertiary hover:text-atlas-text transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                    {Hero}
                    {Buttons}
                </div>
            ) : (
                <div>
                    <div className="flex items-center gap-2 mb-2">
                        <Sparkles className="w-3.5 h-3.5 text-atlas-cyan" />
                        <div className="label-tag">WHAT&apos;S COMING</div>
                    </div>
                    <div className="rounded-xl border border-atlas-border bg-atlas-bg p-3 space-y-3">
                        {Hero}
                        {Buttons}
                    </div>
                </div>
            )}

            <Dialog open={learnOpen} onOpenChange={setLearnOpen}>
                <DialogContent className="bg-atlas-panel border-atlas-border max-w-md" data-testid="promo-learn-modal">
                    <DialogHeader>
                        <DialogTitle className="font-heading tracking-wide text-atlas-text">Coming Soon to Ananta</DialogTitle>
                        <DialogDescription className="font-mono text-[11px] text-atlas-textTertiary">
                            Three big upgrades on the roadmap — join the waitlist for early access.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        {FEATURES.map(({ icon: Icon, title, desc }) => (
                            <div key={title} className="flex gap-3 p-3 rounded-lg border border-atlas-border bg-atlas-bg">
                                <span className="w-9 h-9 rounded-full bg-atlas-cyan/15 flex items-center justify-center shrink-0">
                                    <Icon className="w-4.5 h-4.5 text-atlas-cyan" />
                                </span>
                                <div className="min-w-0">
                                    <div className="font-heading font-medium text-atlas-text text-sm">{title}</div>
                                    <div className="font-body text-xs text-atlas-textSecondary mt-0.5 leading-relaxed">{desc}</div>
                                </div>
                            </div>
                        ))}
                        <button
                            type="button" data-testid="promo-modal-join" onClick={join} disabled={joining || joined}
                            className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-atlas-cyan text-atlas-bg font-body text-sm font-semibold hover:bg-atlas-cyan/90 transition-colors disabled:opacity-70"
                        >
                            {joining ? <Loader2 className="w-4 h-4 animate-spin" /> : joined ? <Check className="w-4 h-4" /> : null}
                            {joined ? "On the waitlist" : "Join Waitlist"}
                        </button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}
