import { useState } from "react";
import { ShieldX } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
    AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

/** Owner-only Manual Emergency Exit. Hidden entirely for the public read-only view. */
export const ManualExitButton = ({ symbol, onDone, compact = false }) => {
    const { isOwner } = useAuth();
    const [busy, setBusy] = useState(false);
    if (!isOwner) return null;
    const base = symbol.split("/")[0];

    const doExit = async () => {
        setBusy(true);
        try {
            await api.closePosition(base);
            toast.success(`EMERGENCY EXIT FILLED · ${base}`);
            onDone && onDone();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Exit failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <AlertDialog>
            <AlertDialogTrigger asChild>
                <button
                    data-testid={`manual-exit-${base}`}
                    disabled={busy}
                    className={`inline-flex items-center gap-1.5 font-mono font-bold tracking-wider border border-atlas-negative/50 text-atlas-negative hover:bg-atlas-negative/10 transition-colors rounded-md disabled:opacity-40 ${
                        compact ? "text-[10px] px-2.5 py-1.5" : "text-xs px-3 py-2"
                    }`}
                >
                    <ShieldX className={compact ? "w-3 h-3" : "w-3.5 h-3.5"} />
                    {busy ? "EXITING…" : "EXIT"}
                </button>
            </AlertDialogTrigger>
            <AlertDialogContent className="bg-atlas-panel border-atlas-border" data-testid={`exit-confirm-${base}`}>
                <AlertDialogHeader>
                    <AlertDialogTitle className="font-heading text-atlas-text">Emergency Exit · {base}</AlertDialogTitle>
                    <AlertDialogDescription className="font-mono text-xs text-atlas-textSecondary">
                        Immediately market-close the entire {base} position to preserve capital. This routes a real
                        sell in LIVE mode (simulated fill in PAPER) and locks the symbol on cooldown. Cannot be undone.
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel data-testid={`exit-cancel-${base}`} className="font-mono text-xs border-atlas-border text-atlas-textSecondary">CANCEL</AlertDialogCancel>
                    <AlertDialogAction data-testid={`exit-confirm-action-${base}`} onClick={doExit}
                        className="font-mono text-xs bg-atlas-negative text-white hover:bg-atlas-negative/80">
                        CONFIRM EXIT
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
};

export default ManualExitButton;
