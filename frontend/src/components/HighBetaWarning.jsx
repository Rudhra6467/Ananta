import { AlertTriangle } from "lucide-react";

/**
 * Prominent "High Beta Exposure Warning" banner.
 * Fires when >= 3 open positions share the Layer-1 High Beta sector.
 */
export default function HighBetaWarning({ exposure }) {
    if (!exposure || !exposure.high_beta_warning) return null;

    const { high_beta_count, high_beta_sector, high_beta_threshold } = exposure;

    return (
        <div
            data-testid="high-beta-exposure-warning"
            className="relative overflow-hidden border border-atlas-warning/60 bg-atlas-warning/10 rounded-sm"
        >
            <div className="absolute inset-y-0 left-0 w-1 bg-atlas-warning animate-pulse" />
            <div className="flex items-start gap-3 px-5 py-4 pl-6">
                <AlertTriangle className="w-5 h-5 text-atlas-warning shrink-0 mt-0.5" />
                <div>
                    <div className="font-heading font-bold text-atlas-warning text-base tracking-tight">
                        HIGH BETA EXPOSURE WARNING
                    </div>
                    <div className="font-mono text-[11px] text-atlas-textSecondary mt-1 leading-relaxed">
                        {high_beta_count} active positions in{" "}
                        <span className="text-white font-bold">{high_beta_sector}</span>{" "}
                        (threshold {high_beta_threshold}). Portfolio carries concentrated correlated
                        risk — a single macro shock could hit all of them at once. Consider
                        diversifying sectors or trimming exposure.
                    </div>
                </div>
            </div>
        </div>
    );
}
