import { useState, useEffect } from "react";
import { Link2, UserPlus, Gift, BarChart3, FileText, CreditCard, Bell, ShieldCheck, LogOut, ChevronRight, Activity, LifeBuoy, RotateCcw, Sparkles } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import ComingSoonPromo from "@/components/ComingSoonPromo";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import LearningHub from "@/components/LearningHub";

// Account overlay (web) — opened by the Ananta logo button. Mirrors the mobile Account
// layout (Profile header · Features · Settings) and serves the in-app privacy info.
// Only real data this sprint: the user's email + auth status; feature/settings rows are
// visual placeholders ("Soon") to be wired in a later sprint.

function Row({ icon: Icon, label, pill, pillTone = "muted", testid }) {
    return (
        <button
            type="button"
            data-testid={testid}
            className="w-full flex items-center justify-between gap-3 px-3 py-3 hover:bg-atlas-panelHover transition-colors group"
        >
            <span className="flex items-center gap-3 min-w-0">
                <span className="w-8 h-8 rounded-full bg-atlas-panelHover flex items-center justify-center shrink-0">
                    <Icon className="w-4 h-4 text-atlas-textSecondary" />
                </span>
                <span className="font-body text-sm text-atlas-text truncate">{label}</span>
            </span>
            <span className="flex items-center gap-2 shrink-0">
                {pill && (
                    <span className={`px-2 py-0.5 rounded-full font-mono text-[10px] ${pillTone === "accent" ? "bg-atlas-cyan/15 text-atlas-cyan" : "bg-atlas-panelHover text-atlas-textTertiary"}`}>
                        {pill}
                    </span>
                )}
                <ChevronRight className="w-4 h-4 text-atlas-textTertiary group-hover:text-atlas-textSecondary" />
            </span>
        </button>
    );
}

function HealthRow({ label, ok, okText, badText, neutral }) {
    const tone = neutral || ok == null ? "text-atlas-textTertiary" : ok ? "text-atlas-positive" : "text-atlas-negative";
    const dot = neutral || ok == null ? "bg-atlas-textTertiary" : ok ? "bg-atlas-positive" : "bg-atlas-negative";
    return (
        <div className="flex items-center justify-between px-3 py-3" data-testid={`account-health-${label.toLowerCase().replace(/\s+/g, "-")}`}>
            <span className="flex items-center gap-2 font-body text-sm text-atlas-textSecondary"><Activity className="w-3.5 h-3.5 text-atlas-textTertiary" />{label}</span>
            <span className={`flex items-center gap-1.5 font-mono text-xs ${tone}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />{ok == null && !neutral ? "…" : okText || badText}
            </span>
        </div>
    );
}

export default function AccountOverlay({ open, onOpenChange }) {
    const { owner, isOwner, logout } = useAuth();
    const email = owner?.email || "Not signed in";
    const initials = (owner?.email?.split("@")[0] || "AN").slice(0, 2).toUpperCase();
    const [health, setHealth] = useState(null);
    const [resetting, setResetting] = useState(false);
    const [promoOpen, setPromoOpen] = useState(false);

    const onResetPaper = async () => {
        if (!isOwner) return;
        if (!window.confirm("Reset Paper Trading?\n\nThis permanently clears all open positions, closed trades, P&L and cached performance. Ananta starts fresh on the current logic. This cannot be undone.")) return;
        setResetting(true);
        try {
            await api.resetPortfolio();
            toast.success("Paper trading state reset", { description: "Ananta starts fresh with zero trades." });
        } catch (e) {
            toast.error("Reset failed", { description: String(e?.response?.data?.detail || e?.message || e) });
        } finally {
            setResetting(false);
        }
    };

    // Live platform status (moved here from Workspace › Engine & Risk). Loads while open.
    useEffect(() => {
        if (!open) return;
        let active = true;
        const load = async () => {
            const h = {};
            try { await api.riskStatus(); h.backend = true; } catch { h.backend = false; }
            try { const e = await api.getEnvironment(); h.mode = e.mode; h.gate = e.ready_to_trade; } catch { h.mode = "—"; }
            if (active) setHealth(h);
        };
        load();
        const t = setInterval(load, 15000);
        return () => { active = false; clearInterval(t); };
    }, [open]);

    return (
        <>
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-atlas-panel border-atlas-border max-w-md p-0 gap-0 overflow-hidden" data-testid="account-overlay">
                <DialogHeader className="px-5 pt-5 pb-3 border-b border-atlas-border">
                    <DialogTitle className="font-heading tracking-wide text-atlas-text">Account</DialogTitle>
                    <DialogDescription className="font-mono text-[11px] text-atlas-textTertiary">
                        Account &amp; privacy · your login details and app info
                    </DialogDescription>
                </DialogHeader>

                <div className="max-h-[70vh] overflow-y-auto atlas-scroll px-5 py-4 space-y-5">
                    {/* profile header */}
                    <div className="flex items-center gap-3 p-3 rounded-lg border border-atlas-border bg-atlas-bg" data-testid="account-profile-header">
                        <div className="w-12 h-12 rounded-full bg-atlas-panelHover border border-atlas-border flex items-center justify-center shrink-0">
                            <span className="font-heading font-bold text-atlas-text tracking-wide">{initials}</span>
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="font-heading font-medium text-atlas-text leading-tight">Ananta Owner</div>
                            <div data-testid="account-email" className="font-mono text-xs text-atlas-textSecondary truncate">{email}</div>
                        </div>
                        <span className={`px-2 py-0.5 rounded-full font-mono text-[10px] ${isOwner ? "bg-atlas-positive/15 text-atlas-positive" : "bg-atlas-panelHover text-atlas-textTertiary"}`} data-testid="account-auth-status">
                            {isOwner ? "AUTHENTICATED" : "READ-ONLY"}
                        </span>
                    </div>

                    {/* login / auth (only real data this sprint) */}
                    <div>
                        <div className="label-tag mb-2">LOGIN &amp; AUTH</div>
                        <div className="rounded-lg border border-atlas-border overflow-hidden">
                            <div className="flex items-center justify-between px-3 py-3">
                                <span className="font-body text-sm text-atlas-textSecondary">Email</span>
                                <span data-testid="account-cred-email" className="font-mono text-xs text-atlas-text truncate ml-3">{email}</span>
                            </div>
                            <div className="h-px bg-atlas-border" />
                            <div className="flex items-center justify-between px-3 py-3">
                                <span className="font-body text-sm text-atlas-textSecondary">Password</span>
                                <span data-testid="account-cred-password" className="font-mono text-xs text-atlas-text">{"\u2022".repeat(10)}</span>
                            </div>
                            <div className="h-px bg-atlas-border" />
                            <div className="flex items-center justify-between px-3 py-3">
                                <span className="font-body text-sm text-atlas-textSecondary">Authentication</span>
                                <span className="font-mono text-xs text-atlas-text">Secure token (JWT)</span>
                            </div>
                        </div>
                    </div>

                    {/* invite / promo placeholder */}
                    <div className="flex items-center gap-3 p-4 rounded-lg border border-atlas-border bg-atlas-bg" data-testid="account-invite-banner">
                        <div className="flex-1">
                            <div className="font-heading font-medium text-atlas-text">Invite friends</div>
                            <div className="font-mono text-[11px] text-atlas-textTertiary mt-0.5">Earn a bonus once they sign up and trade.</div>
                        </div>
                        <span className="w-10 h-10 rounded-full bg-atlas-panelHover flex items-center justify-center">
                            <Gift className="w-5 h-5 text-atlas-warning" />
                        </span>
                    </div>

                    {/* features */}
                    <div>
                        <div className="label-tag mb-2">FEATURES</div>
                        <div className="rounded-lg border border-atlas-border overflow-hidden divide-y divide-atlas-border">
                            <Row icon={Link2} label="Exchange Connection" pill="Kraken" testid="account-feature-exchange" />
                            <Row icon={UserPlus} label="Referrals" pill="Soon" pillTone="accent" testid="account-feature-referrals" />
                            <Row icon={Gift} label="Offers" pill="Soon" testid="account-feature-offers" />
                            <Row icon={BarChart3} label="Earn" pill="Soon" testid="account-feature-earn" />
                            <Row icon={FileText} label="Tax reporting" pill="Soon" testid="account-feature-tax" />
                        </div>
                    </div>

                    {/* learning hub (migrated from Workspace) */}
                    <LearningHub onClose={() => onOpenChange(false)} />

                    {/* system health (moved from Workspace › Engine & Risk) */}
                    <div data-testid="account-system-health">
                        <div className="label-tag mb-2">SYSTEM HEALTH</div>
                        <div className="rounded-lg border border-atlas-border overflow-hidden divide-y divide-atlas-border">
                            <HealthRow label="Backend API" ok={health?.backend} okText="Online" badText="Unreachable" />
                            <HealthRow label="Trading Mode" ok={health?.mode ? true : null} okText={(health?.mode || "—").toUpperCase()} neutral />
                            <HealthRow label="Live Gate" ok={health?.gate} okText="Armed" badText="Closed" />
                        </div>
                    </div>

                    {/* settings */}
                    <div>
                        <div className="label-tag mb-2">SETTINGS</div>
                        <div className="rounded-lg border border-atlas-border overflow-hidden divide-y divide-atlas-border">
                            <button type="button" data-testid="account-coming-up" onClick={() => setPromoOpen(true)}
                                className="w-full flex items-center justify-between px-3 py-3 hover:bg-atlas-panelHover transition-colors group">
                                <span className="flex items-center gap-2.5 font-body text-sm text-atlas-textSecondary group-hover:text-atlas-text"><Sparkles className="w-4 h-4 text-atlas-cyan" /> Coming Up</span>
                                <span className="flex items-center gap-2">
                                    <span className="px-2 py-0.5 rounded-full font-mono text-[10px] bg-atlas-cyan/15 text-atlas-cyan">New</span>
                                    <ChevronRight className="w-4 h-4 text-atlas-textTertiary group-hover:text-atlas-textSecondary" />
                                </span>
                            </button>
                            <Row icon={CreditCard} label="Payment methods" pill="Soon" testid="account-setting-payments" />
                            <Row icon={Bell} label="Notifications" pill="Soon" testid="account-setting-notifications" />
                            <a href="/privacy" target="_blank" rel="noopener noreferrer" data-testid="account-setting-privacy"
                                onClick={() => onOpenChange(false)}
                                className="flex items-center justify-between px-3 py-3 hover:bg-atlas-panelHover transition-colors">
                                <span className="flex items-center gap-2.5 font-body text-sm text-atlas-textSecondary"><ShieldCheck className="w-4 h-4 text-atlas-textTertiary" /> Privacy &amp; Security</span>
                                <span className="flex items-center gap-1 font-mono text-[10px] text-atlas-cyan">Policy <ChevronRight className="w-3.5 h-3.5" /></span>
                            </a>
                            <a href="/support" target="_blank" rel="noopener noreferrer" data-testid="account-contact-us"
                                onClick={() => onOpenChange(false)}
                                className="flex items-center justify-between px-3 py-3 hover:bg-atlas-panelHover transition-colors">
                                <span className="flex items-center gap-2.5 font-body text-sm text-atlas-textSecondary"><LifeBuoy className="w-4 h-4 text-atlas-textTertiary" /> Contact Us</span>
                                <span className="flex items-center gap-1 font-mono text-[10px] text-atlas-cyan">Support <ChevronRight className="w-3.5 h-3.5" /></span>
                            </a>
                        </div>
                    </div>

                    {/* privacy statement (in-app privacy info) */}
                    <p className="font-mono text-[10px] leading-relaxed text-atlas-textTertiary" data-testid="account-privacy-note">
                        Ananta stores only your account email and an encrypted authentication token to keep you
                        signed in. We do not sell personal data. Trading is executed via your own exchange keys,
                        which are stored securely and never shared.
                    </p>

                    {isOwner && (
                        <div data-testid="account-paper-trading">
                            <div className="label-tag mb-2">PAPER TRADING</div>
                            <button
                                type="button"
                                data-testid="account-reset-paper"
                                onClick={onResetPaper}
                                disabled={resetting}
                                className="w-full flex items-center justify-between gap-3 px-3 py-3 rounded-lg border border-atlas-negative/40 text-atlas-negative hover:bg-atlas-negative/10 transition-colors disabled:opacity-50"
                            >
                                <span className="flex items-center gap-2.5 min-w-0">
                                    <RotateCcw className="w-4 h-4 shrink-0" />
                                    <span className="flex flex-col items-start min-w-0">
                                        <span className="font-body text-sm font-medium">{resetting ? "Resetting…" : "Reset Paper Trading State"}</span>
                                        <span className="font-mono text-[10px] text-atlas-textTertiary truncate">Clears positions, trades, P&amp;L &amp; cached performance</span>
                                    </span>
                                </span>
                                <ChevronRight className="w-4 h-4 shrink-0" />
                            </button>
                        </div>
                    )}

                    {isOwner && (
                        <button
                            type="button"
                            data-testid="account-logout-btn"
                            onClick={() => { logout(); onOpenChange(false); }}
                            className="w-full flex items-center justify-center gap-2 py-3 rounded-lg border border-atlas-border text-atlas-negative hover:bg-atlas-negative/10 transition-colors font-body text-sm font-medium"
                        >
                            <LogOut className="w-4 h-4" /> Log out
                        </button>
                    )}

                    <div className="font-mono text-[10px] text-atlas-textTertiary text-center pt-1">Ananta.AI · Account &amp; Privacy</div>
                </div>
            </DialogContent>
        </Dialog>

        <Dialog open={promoOpen} onOpenChange={setPromoOpen}>
            <DialogContent className="max-w-lg max-h-[88vh] overflow-y-auto p-0" data-testid="account-coming-up-dialog">
                <DialogHeader className="px-5 pt-5">
                    <DialogTitle className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-atlas-cyan" /> Coming Up</DialogTitle>
                    <DialogDescription>A look at what&apos;s next for Ananta — join the waitlist to get early access.</DialogDescription>
                </DialogHeader>
                <div className="px-5 pb-5">
                    <ComingSoonPromo variant="inline" />
                </div>
            </DialogContent>
        </Dialog>
        </>
    );
}
