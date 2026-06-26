import { useEffect, useState } from "react";
import { RefreshCw, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/* Watchlist sync health + manual sync controls. Anchored on the Cockpit beside the
   Watchlist so the operator can verify production token sync without leaving Home. */
export default function WatchlistControl() {
    const { isOwner } = useAuth();
    const [info, setInfo] = useState(null);
    const [busy, setBusy] = useState(false);

    const validate = () => api.watchlistValidate().then(setInfo).catch(() => {});
    useEffect(() => { validate(); }, []);

    const sync = async () => {
        setBusy(true);
        try {
            const r = await api.watchlistSync();
            toast.success(`Watchlist synced · ${r.count} assets`);
            validate();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Sync failed");
        } finally { setBusy(false); }
    };

    if (!info) return null;
    return (
        <div className="flex items-center gap-2 font-mono flex-wrap" data-testid="watchlist-control">
            <div className={`flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded border ${info.in_sync ? "border-atlas-positive/40 text-atlas-positive" : "border-atlas-negative/50 text-atlas-negative"}`} data-testid="watchlist-status">
                {info.in_sync ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                <span>Watchlist {info.current_count}/{info.expected_count}{info.in_sync ? " · in sync" : " · DRIFT"}</span>
            </div>
            <button onClick={validate} data-testid="watchlist-validate-btn"
                className="text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text border border-atlas-border rounded px-2.5 py-1.5 flex items-center gap-1.5 transition-colors">
                <RefreshCw className="w-3 h-3" /> VALIDATE
            </button>
            {isOwner && (
                <button onClick={sync} disabled={busy || info.in_sync} data-testid="watchlist-sync-btn"
                    className="text-[10px] tracking-widest font-bold text-atlas-cyan border border-atlas-cyan/40 hover:bg-atlas-cyan/10 rounded px-2.5 py-1.5 transition-colors disabled:opacity-40">
                    {busy ? "SYNCING…" : "SYNC 10"}
                </button>
            )}
        </div>
    );
}
