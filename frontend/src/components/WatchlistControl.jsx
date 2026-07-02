import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
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
            <span
                data-testid="watchlist-status-dot"
                title={info.in_sync ? `In sync · ${info.current_count}/${info.expected_count}` : `Drift · ${info.current_count}/${info.expected_count}`}
                className={`w-2.5 h-2.5 rounded-full shrink-0 ${info.in_sync ? "bg-atlas-positive glow-green" : "bg-atlas-negative glow-red"}`}
            />
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
