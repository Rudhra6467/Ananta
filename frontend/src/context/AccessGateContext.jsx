import { createContext, useCallback, useContext, useState } from "react";
import { Sparkles, Lock, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const AccessGateContext = createContext(null);

/**
 * Access gate for the launch MVP.
 * - Owner: every gated action proceeds (gate() returns true).
 * - Public visitor: surface UI stays visible, but any "deeper" action opens the
 *   Waitlist modal (Name + Email → saved to DB) and gate() returns false.
 * Auth-agnostic on purpose: swap the `isOwner` check for a real user session later
 * to upgrade from waitlist to full accounts without touching call sites.
 */
export function AccessGateProvider({ children }) {
    const { isOwner } = useAuth();
    const [feature, setFeature] = useState(null); // string when modal open

    const gate = useCallback((featureLabel) => {
        if (isOwner) return true;
        setFeature(featureLabel || "this feature");
        return false;
    }, [isOwner]);

    return (
        <AccessGateContext.Provider value={{ gate, isOwner }}>
            {children}
            <WaitlistModal feature={feature} onClose={() => setFeature(null)} />
        </AccessGateContext.Provider>
    );
}

export function useAccessGate() {
    const ctx = useContext(AccessGateContext);
    if (!ctx) throw new Error("useAccessGate must be used within AccessGateProvider");
    return ctx;
}

function WaitlistModal({ feature, onClose }) {
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState(false);

    const submit = async () => {
        if (!name.trim() || !email.trim()) { toast.error("Please enter your name and email."); return; }
        setBusy(true);
        try {
            const r = await api.accessRequest({ name: name.trim(), email: email.trim(), feature, platform: "web" });
            setDone(true);
            toast.success(r.already_on_list ? "You're already on the list — we'll be in touch!" : "You're on the waitlist!");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Could not submit. Please try again.");
        } finally { setBusy(false); }
    };

    const close = () => { onClose(); setTimeout(() => { setName(""); setEmail(""); setDone(false); }, 200); };

    return (
        <Dialog open={!!feature} onOpenChange={(o) => !o && close()}>
            <DialogContent data-testid="waitlist-modal" className="panel border-atlas-border max-w-sm">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 font-heading text-atlas-text">
                        <Lock className="w-4 h-4 text-atlas-cyan" /> Request early access
                    </DialogTitle>
                </DialogHeader>
                {done ? (
                    <div className="text-center py-4 space-y-2">
                        <Sparkles className="w-8 h-8 text-atlas-cyan mx-auto" />
                        <div className="font-heading text-lg text-atlas-text">You&apos;re on the list</div>
                        <p className="font-mono text-[12px] text-atlas-textSecondary">We&apos;ll email you when access opens up. Thanks for your interest!</p>
                        <Button data-testid="waitlist-done-btn" onClick={close} className="mt-2 bg-atlas-cyan text-black hover:brightness-110">Done</Button>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <p className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed">
                            <span className="text-atlas-text">{feature}</span> is part of the full Ananta experience. Join the waitlist and we&apos;ll notify you when access opens.
                        </p>
                        <Input data-testid="waitlist-name" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)}
                            className="bg-atlas-bg border-atlas-border text-white font-mono text-[13px]" />
                        <Input data-testid="waitlist-email" type="email" placeholder="you@email.com" value={email} onChange={(e) => setEmail(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && submit()}
                            className="bg-atlas-bg border-atlas-border text-white font-mono text-[13px]" />
                        <Button data-testid="waitlist-submit" onClick={submit} disabled={busy}
                            className="w-full bg-atlas-cyan text-black font-bold hover:brightness-110 disabled:opacity-50">
                            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Join the waitlist"}
                        </Button>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
