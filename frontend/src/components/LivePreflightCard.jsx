import { useEffect, useState } from "react";
import { Radio, FlaskConical, CheckCircle2, AlertTriangle, KeyRound, Gauge, ShieldAlert, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Recommended per-trade size ceiling for first real-money validation runs.
const SOFT_CAP_USD = 75;

/**
 * Live Preflight — one-glance safety readout before trading real capital:
 * mode (PAPER/LIVE) · API-key/exchange connection · position-size soft cap ·
 * one-tap kill-switch / back-to-Paper. Read-only for non-owners.
 */
export default function LivePreflightCard() {
    const { isOwner } = useAuth();
    const [env, setEnv] = useState(null);
    const [settings, setSettings] = useState(null);
    const [busy, setBusy] = useState(false);

    const refresh = () => {
        api.getEnvironment().then(setEnv).catch(() => {});
        api.settings().then(setSettings).catch(() => {});
    };
    useEffect(() => {
        refresh();
        const t = setInterval(() => api.getEnvironment().then(setEnv).catch(() => {}), 10000);
        return () => clearInterval(t);
    }, []);

    if (!env) return null;
    const isLive = !!env.is_live;
    const ready = !!env.ready_to_trade;
    const killed = !!settings?.manual_kill_switch;
    const lot = Number(settings?.normal_lot_usd ?? 0);
    const overCap = lot > SOFT_CAP_USD;

    const guard = (fn) => async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setBusy(true);
        try { await fn(); refresh(); } catch (e) { toast.error("Action failed", { description: String(e?.message || e) }); }
        finally { setBusy(false); }
    };
    const backToPaper = guard(async () => { await api.setEnvironment("PAPER"); toast.success("Switched to PAPER — simulated fills only."); });
    const toggleKill = guard(async () => {
        await api.updateSettings({ manual_kill_switch: !killed });
        toast[!killed ? "error" : "success"](!killed ? "ANANTA STOPPED — no new entries" : "ANANTA RESUMED");
    });

    return (
        <div data-testid="live-preflight-card"
            className={`panel rounded-xl p-4 border ${isLive ? "border-atlas-negative/50 bg-atlas-negative/5" : "border-atlas-cyan/40 bg-atlas-cyan/5"}`}>
            <div className="flex items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-2.5">
                    <span className={`w-8 h-8 rounded-lg grid place-items-center border ${isLive ? "border-atlas-negative/50 bg-atlas-negative/10" : "border-atlas-cyan/40 bg-atlas-cyan/10"}`}>
                        {isLive ? <Radio className="w-4 h-4 text-atlas-negative animate-pulse" /> : <FlaskConical className="w-4 h-4 text-atlas-cyan" />}
                    </span>
                    <div>
                        <div className="font-mono text-[10px] tracking-widest text-atlas-textTertiary">LIVE PREFLIGHT</div>
                        <div className={`font-heading text-lg leading-tight ${isLive ? "text-atlas-negative" : "text-atlas-text"}`} data-testid="preflight-mode">
                            {isLive ? "LIVE · real capital" : "PAPER · simulation"}
                        </div>
                    </div>
                </div>
                {isLive && (
                    <button data-testid="preflight-back-to-paper" onClick={backToPaper} disabled={busy}
                        className="flex items-center gap-1.5 rounded-lg border border-atlas-cyan text-atlas-cyan hover:bg-atlas-cyan/10 font-mono text-[10px] font-bold tracking-widest px-3 py-2 transition-colors disabled:opacity-50">
                        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5" />} BACK TO PAPER
                    </button>
                )}
            </div>

            <div className="grid sm:grid-cols-3 gap-2">
                <PreflightRow icon={ready ? CheckCircle2 : AlertTriangle} ok={ready} testid="preflight-connection"
                    label="Broker connection"
                    value={ready ? `Connected · ${env.exchange || "exchange"}` : "Keys not set"}
                    note={ready ? null : "Add API keys on the deployed backend"} muteIcon={KeyRound} />
                <PreflightRow icon={Gauge} ok={!overCap} testid="preflight-size"
                    label="Position size"
                    value={lot ? `$${lot.toFixed(0)} / trade` : "—"}
                    note={overCap ? `Above ~$${SOFT_CAP_USD} — keep small (~$50) for first live tests` : "Good for small-size live testing"} />
                <PreflightRow icon={ShieldAlert} ok={!killed} testid="preflight-kill"
                    label="Trading"
                    value={killed ? "STOPPED" : "Active"}
                    action={isOwner ? { label: killed ? "Resume" : "Kill-switch", onClick: toggleKill, danger: !killed } : null} busy={busy} />
            </div>

            {isLive && !ready && (
                <div className="mt-3 flex items-start gap-2 rounded-lg border border-atlas-warning/30 bg-atlas-warning/10 px-3 py-2 font-mono text-[10px] text-atlas-warning" data-testid="preflight-warning">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    LIVE is armed but the broker gate is CLOSED — set API keys + LIVE_TRADING_ENABLED on the deployed backend, or no real orders will fire.
                </div>
            )}
        </div>
    );
}

function PreflightRow({ icon: Icon, ok, label, value, note, action, busy, testid, muteIcon: MuteIcon }) {
    const Glyph = ok ? Icon : (MuteIcon || Icon);
    return (
        <div className="panel border border-atlas-border rounded-lg p-3" data-testid={testid}>
            <div className="flex items-center gap-1.5 mb-1">
                <Glyph className={`w-3.5 h-3.5 ${ok ? "text-atlas-positive" : "text-atlas-warning"}`} />
                <span className="font-mono text-[9px] uppercase tracking-widest text-atlas-textTertiary">{label}</span>
            </div>
            <div className={`font-heading text-sm ${ok ? "text-atlas-text" : "text-atlas-warning"}`}>{value}</div>
            {note && <div className="font-mono text-[9px] text-atlas-textTertiary mt-0.5 leading-snug">{note}</div>}
            {action && (
                <button data-testid={`${testid}-action`} onClick={action.onClick} disabled={busy}
                    className={`mt-1.5 font-mono text-[9px] font-bold tracking-widest px-2.5 py-1 rounded-md border transition-colors disabled:opacity-50 ${
                        action.danger ? "border-atlas-negative/50 text-atlas-negative hover:bg-atlas-negative/10" : "border-atlas-cyan/50 text-atlas-cyan hover:bg-atlas-cyan/10"}`}>
                    {action.label}
                </button>
            )}
        </div>
    );
}
