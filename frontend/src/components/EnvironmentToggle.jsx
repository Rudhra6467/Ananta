import { useEffect, useState } from "react";
import { FlaskConical, Radio, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";

/**
 * Master LIVE / PAPER environment switch (drives the single source-of-truth
 * `trading_mode`). PAPER is one-click instant; switching to LIVE requires a
 * one-tap confirmation because it routes REAL orders to Kraken.
 */
export default function EnvironmentToggle() {
    const [env, setEnv] = useState(null);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const { isOwner } = useAuth();

    const refresh = () => api.getEnvironment().then(setEnv).catch(() => {});

    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 10000);
        return () => clearInterval(t);
    }, []);

    const apply = async (mode) => {
        setBusy(true);
        try {
            const next = await api.setEnvironment(mode);
            setEnv(next);
            if (mode === "LIVE") {
                if (next.ready_to_trade) {
                    toast.warning("LIVE TRADING ARMED", {
                        description: "Real orders will route to Kraken on the next signal.",
                    });
                } else {
                    toast.error("LIVE set, but gate is CLOSED", {
                        description: "Missing API keys / LIVE_TRADING_ENABLED — no real orders will fire.",
                    });
                }
            } else {
                toast.success("PAPER MODE", { description: "Simulated fills only. No real orders." });
            }
        } catch (e) {
            toast.error("Switch failed", { description: String(e?.message || e) });
        } finally {
            setBusy(false);
        }
    };

    const isLive = env?.is_live;
    const mode = env?.trading_mode || "PAPER";

    const handleClick = (target) => {
        if (busy || target === mode) return;
        if (!isOwner) {
            toast.error("Owner login required", { description: "Public view is read-only." });
            return;
        }
        if (target === "LIVE") {
            setConfirmOpen(true);
        } else {
            apply("PAPER");
        }
    };

    return (
        <>
            <div
                className={`flex items-center gap-0 border border-atlas-border rounded-sm overflow-hidden select-none ${
                    isOwner ? "" : "opacity-50 cursor-not-allowed"
                }`}
                data-testid="environment-toggle"
                title={isOwner ? (isLive ? `LIVE · gate ${env?.live_gate_open ? "OPEN" : "CLOSED"}` : "PAPER simulation") : "Owner login required"}
            >
                <button
                    type="button"
                    data-testid="env-toggle-paper"
                    onClick={() => handleClick("PAPER")}
                    className={`flex items-center gap-1.5 font-mono text-[10px] tracking-widest font-bold px-3 py-1.5 transition-colors ${
                        !isLive
                            ? "bg-atlas-cyan text-atlas-bg"
                            : "text-atlas-textSecondary hover:text-white"
                    }`}
                >
                    <FlaskConical className="w-3 h-3" />
                    PAPER
                </button>
                <button
                    type="button"
                    data-testid="env-toggle-live"
                    onClick={() => handleClick("LIVE")}
                    className={`flex items-center gap-1.5 font-mono text-[10px] tracking-widest font-bold px-3 py-1.5 transition-colors ${
                        isLive
                            ? "bg-atlas-negative text-white"
                            : "text-atlas-textSecondary hover:text-white"
                    }`}
                >
                    <Radio className={`w-3 h-3 ${isLive ? "animate-pulse" : ""}`} />
                    LIVE
                </button>
            </div>

            <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <AlertDialogContent
                    className="bg-atlas-panel border border-atlas-negative/50 text-white"
                    data-testid="env-live-confirm-dialog"
                >
                    <AlertDialogHeader>
                        <AlertDialogTitle className="flex items-center gap-2 font-heading text-atlas-negative">
                            <AlertTriangle className="w-5 h-5" />
                            Arm LIVE Trading?
                        </AlertDialogTitle>
                        <AlertDialogDescription className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed">
                            This routes <span className="text-white font-bold">REAL orders to Kraken</span> with
                            actual capital. Normal/Strong signals go out as Post-Only limit orders; breakouts as
                            market orders. Simulation is fully bypassed.
                            {env && !env.live_gate_open && (
                                <span className="block mt-2 text-atlas-warning">
                                    Note: the server live-gate is currently CLOSED, so no orders will actually fire
                                    until API keys + LIVE_TRADING_ENABLED are configured.
                                </span>
                            )}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel
                            data-testid="env-live-cancel"
                            className="bg-transparent border-atlas-border text-atlas-textSecondary hover:bg-atlas-border/30 hover:text-white"
                        >
                            Stay on PAPER
                        </AlertDialogCancel>
                        <AlertDialogAction
                            data-testid="env-live-confirm"
                            onClick={() => apply("LIVE")}
                            className="bg-atlas-negative text-white hover:bg-atlas-negative/85"
                        >
                            Yes, go LIVE
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    );
}
