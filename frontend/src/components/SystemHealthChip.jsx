import { useEffect, useState } from "react";
import { Activity, CheckCircle2, XCircle, Loader2, ChevronDown } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Compact first-run / ongoing health self-check. Renders as a small pill that
// expands into a popover with per-system detail — deliberately low-footprint so
// it never eats Cockpit vertical space.
export default function SystemHealthChip() {
    const { isOwner } = useAuth();
    const [data, setData] = useState(null);
    const [err, setErr] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let active = true;
        const load = async () => {
            try {
                const d = await api.healthSelfcheck();
                if (active) { setData(d); setErr(false); }
            } catch {
                if (active) setErr(true);
            } finally {
                if (active) setLoading(false);
            }
        };
        load();
        const t = setInterval(load, 30000);
        return () => { active = false; clearInterval(t); };
    }, []);

    const rows = [
        { key: "backend", label: "Backend API", ok: !err && !!data?.backend?.ok, note: err ? "Unreachable" : "Online" },
        { key: "database", label: "Database", ok: !!data?.database?.ok, note: data?.database?.latency_ms != null ? `${data.database.latency_ms} ms` : (data?.database?.ok ? "OK" : "Down") },
        { key: "market", label: "Market Data", ok: !!data?.market_data?.ok, note: data?.market_data?.freshest_age_s != null ? `${data.market_data.cached_symbols} feeds · ${data.market_data.freshest_age_s}s` : "No feed" },
        { key: "engine", label: "Trading Engine", ok: !!data?.engine?.running, note: data?.engine?.running ? (data?.engine?.last_activity_age_s != null ? `active · ${Math.round(data.engine.last_activity_age_s)}s ago` : "running") : "stopped" },
        { key: "session", label: "Session", ok: isOwner, note: isOwner ? "Owner" : "Read-only", neutral: !isOwner },
    ];

    const allOk = !err && !loading && rows.filter((r) => !r.neutral).every((r) => r.ok);
    const dot = loading ? "bg-atlas-textTertiary" : err || !allOk ? "bg-atlas-negative" : "bg-atlas-positive";
    const label = loading ? "Checking…" : err ? "Systems degraded" : allOk ? "All systems OK" : "Attention needed";

    return (
        <Popover>
            <PopoverTrigger asChild>
                <button data-testid="system-health-chip"
                    className="flex items-center gap-2 rounded-full border border-atlas-border bg-atlas-panel px-3 py-1.5 font-mono text-[10px] tracking-wide text-atlas-textSecondary hover:border-atlas-textTertiary hover:text-atlas-text transition-colors">
                    {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <span className={`w-2 h-2 rounded-full ${dot}`} />}
                    <Activity className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">{label}</span>
                    <ChevronDown className="w-3 h-3 opacity-60" />
                </button>
            </PopoverTrigger>
            <PopoverContent align="end" data-testid="system-health-popover"
                className="w-64 panel border-atlas-border p-3 space-y-1.5">
                <div className="font-heading text-sm text-atlas-text mb-1 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-atlas-cyan" /> System Health
                </div>
                {rows.map((r) => (
                    <div key={r.key} data-testid={`health-row-${r.key}`} className="flex items-center justify-between rounded-lg border border-atlas-border px-3 py-2">
                        <span className="font-mono text-[11px] text-atlas-textSecondary">{r.label}</span>
                        <span className={`flex items-center gap-1.5 font-mono text-[10px] ${r.neutral ? "text-atlas-textTertiary" : r.ok ? "text-atlas-positive" : "text-atlas-negative"}`}>
                            {r.neutral ? <span className="w-2 h-2 rounded-full bg-atlas-textTertiary" /> : r.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                            {r.note}
                        </span>
                    </div>
                ))}
            </PopoverContent>
        </Popover>
    );
}
