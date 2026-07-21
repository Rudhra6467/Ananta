// Single source of truth for describing the DEPLOYED exit configuration from the
// settings singleton. Used by the "Current Active Exit" card (Exit Engine home) AND
// the Risk Monitor "Active Exit Engine" card so every screen agrees.
//
// Precedence (most specific wins): per-coin override > per-strategy override > global.
// A per-coin/strategy entry only counts as an exit override when it carries a `method`
// field (deployed via the Exit Engine flow) — plain profile tuning is ignored.

const METHOD_NAMES = {
    fixed_pct: "Fixed-% Stop",
    atr_trailing: "ATR Trailing Stop",
    chandelier: "Chandelier Exit",
    breakeven_trail: "Breakeven Trail",
    structural_trail: "Structural Trail",
    native: "Universal Exit Engine",
};

const num = (v, fallback) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

// First { key, value } of an overrides map whose value declares an exit `method`.
function firstExitOverride(map) {
    for (const [key, value] of Object.entries(map || {})) {
        if (value && typeof value === "object" && value.method) return { key, value };
    }
    return null;
}

// Returns { method, typeLabel, scope, scopeLabel, rows: [{label, value}] }
export function describeActiveExit(s) {
    if (!s) return { method: "native", typeLabel: "—", scope: "global", scopeLabel: "Global", rows: [] };

    const coinOv = firstExitOverride(s.asset_exit_overrides);
    const stratOv = firstExitOverride(s.profile_overrides);

    // Pick the active source (most specific deployed override, else global).
    let ov = null, scope = "global", scopeLabel = "Global (all markets)", method = s.exit_method_pref || "native";
    if (coinOv) { ov = coinOv.value; method = ov.method; scope = "coin"; scopeLabel = `Per-coin · ${coinOv.key}`; }
    else if (stratOv) { ov = stratOv.value; method = ov.method; scope = "strategy"; scopeLabel = `Per-strategy · ${stratOv.key}`; }

    const typeLabel = METHOD_NAMES[method] || "Universal Exit Engine";
    // Override value first, then global setting, then hard default.
    const pick = (ovKey, globalKey, dflt) => num(ov?.[ovKey], num(s[globalKey], dflt));
    const stop = pick("stop_pct", "stop_loss_pct", 2.2);

    let rows;
    if (method === "fixed_pct") {
        rows = [
            { label: "Take-Profit target", value: `${pick("target_pct", "fixed_target_pct", 3.0)}%` },
            { label: "Stop-Loss", value: `${stop}%` },
        ];
    } else if (method === "atr_trailing" || method === "chandelier") {
        rows = [
            { label: "Trail arm", value: `${pick("trail_arm", "trail_arm_pct", 1.6)}%` },
            { label: "Trail distance", value: `${pick("trail_dist", "trail_distance_pct", 0.9)}%` },
            { label: "Hard stop-loss", value: `${stop}%` },
        ];
    } else {
        const trailMult = num(ov?.trail_atr_mult, num(s.profile_overrides?.hunter?.trail_atr_mult, 2.0));
        rows = [
            { label: "Trail multiplier", value: `${trailMult}x` },
            { label: "Breakeven arm", value: `${pick("profit_arm_pct", "trail_arm_pct", 1.6)}%` },
            { label: "Hard stop-loss", value: `${stop}%` },
        ];
    }
    return { method, typeLabel, scope, scopeLabel, rows };
}
