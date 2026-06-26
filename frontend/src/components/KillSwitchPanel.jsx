import { ShieldAlert, ShieldCheck, ShieldOff } from "lucide-react";

export default function KillSwitchPanel({ risk }) {
    if (!risk) {
        return (
            <div className="panel p-6 h-full" data-testid="kill-switch-panel">
                <div className="label-tag">RISK CONTROLS · LAYER 6</div>
                <div className="mt-2 font-mono text-sm text-atlas-textSecondary">
                    <span className="blink-cursor">LOADING</span>
                </div>
            </div>
        );
    }

    const s = risk.status || {};
    const overallSafe = s.overall_safe && !s.manual_kill;
    const switches = [
        {
            id: "spread",
            label: "SPREAD",
            triggered: s.spread_breach,
            value: `${(s.details?.spread_pct ?? 0).toFixed(3)}%`,
            threshold: `≤ ${risk.thresholds?.max_spread_pct}%`,
            description: "Bid/ask spread protection",
        },
        {
            id: "daily-loss",
            label: "DAILY LOSS",
            triggered: s.daily_loss_breach,
            value: `${(s.details?.daily_change_pct ?? 0).toFixed(2)}%`,
            threshold: `≥ -${risk.thresholds?.max_daily_loss_pct}%`,
            description: "Daily drawdown circuit breaker",
        },
        {
            id: "confidence",
            label: "AI CONFIDENCE",
            triggered: s.confidence_breach,
            value: `${(s.details?.macro_confidence ?? 0).toFixed(2)}`,
            threshold: `≥ ${risk.thresholds?.min_confidence}`,
            description: "Min LLM confidence to trade",
            soft: true,
        },
        {
            id: "manual",
            label: "MANUAL KILL",
            triggered: s.manual_kill,
            value: s.manual_kill ? "ENGAGED" : "RELEASED",
            threshold: "Operator override",
            description: "Operator-engaged hard stop",
        },
    ];

    return (
        <div className="panel h-full flex flex-col" data-testid="kill-switch-panel">
            <div className="px-5 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between">
                <div className="flex items-center gap-2">
                    {overallSafe ? (
                        <ShieldCheck className="w-3.5 h-3.5 text-atlas-positive" />
                    ) : (
                        <ShieldAlert className="w-3.5 h-3.5 text-atlas-negative" />
                    )}
                    <span className="label-tag">RISK CONTROLS · KILL-SWITCHES</span>
                </div>
                <OverallPill safe={overallSafe} />
            </div>
            <div className="p-3 grid grid-cols-2 gap-3 flex-1">
                {switches.map((sw) => (
                    <SwitchTile key={sw.id} {...sw} />
                ))}
            </div>
        </div>
    );
}

function OverallPill({ safe }) {
    return (
        <div
            data-testid="kill-switch-overall-status"
            className={`inline-flex items-center gap-2 px-3 py-1 font-mono text-[11px] font-bold tracking-widest border ${
                safe
                    ? "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/5 glow-green"
                    : "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/5 glow-red"
            }`}
        >
            <span className={`w-2 h-2 rounded-full ${safe ? "bg-atlas-positive" : "bg-atlas-negative"}`} />
            {safe ? "SAFE" : "TERMINATED"}
        </div>
    );
}

function SwitchTile({ id, label, triggered, value, threshold, description, soft }) {
    const triggeredCls = triggered
        ? soft
            ? "border-atlas-warning/50 bg-atlas-warning/5"
            : "border-atlas-negative/50 bg-atlas-negative/5 glow-red"
        : "border-atlas-border";

    return (
        <div
            data-testid={`kill-switch-tile-${id}`}
            className={`p-3 border ${triggeredCls} transition-colors`}
        >
            <div className="flex items-center justify-between">
                <div className="label-tag text-[9px]">{label}</div>
                <span
                    className={`font-mono text-[10px] font-bold ${
                        triggered ? (soft ? "text-atlas-warning" : "text-atlas-negative") : "text-atlas-positive"
                    }`}
                >
                    {triggered ? (soft ? "BLOCK" : "TRIPPED") : "OK"}
                </span>
            </div>
            <div className="mt-2 font-mono text-lg font-bold tabular-nums text-white">{value}</div>
            <div className="mt-0.5 text-[10px] font-mono text-atlas-textTertiary">{threshold}</div>
            <div className="mt-1 text-[10px] text-atlas-textSecondary">{description}</div>
        </div>
    );
}
