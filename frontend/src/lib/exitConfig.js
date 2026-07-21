// Single source of truth for describing the DEPLOYED exit configuration from the
// settings singleton. Used by both the "Current Active Exit" card (Exit Engine home)
// and the Risk Monitor "Active Exit Engine" card so every screen agrees.

const METHOD_NAMES = {
    fixed_pct: "Fixed-% Stop",
    atr_trailing: "ATR Trailing Stop",
    chandelier: "Chandelier Exit",
    breakeven_trail: "Breakeven Trail",
    structural_trail: "Structural Trail",
    native: "Universal Exit Engine",
};

const num = (v, fallback) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

// Returns { method, typeLabel, scope, scopeLabel, rows: [{label, value}] }
export function describeActiveExit(s) {
    if (!s) return { method: "native", typeLabel: "—", scope: "global", scopeLabel: "Global", rows: [] };
    const method = s.exit_method_pref || "native";
    const typeLabel = METHOD_NAMES[method] || "Universal Exit Engine";
    const stop = num(s.stop_loss_pct, 2.2);

    // Active scope — global preference, plus any narrower overrides deployed.
    const coins = Object.keys(s.asset_exit_overrides || {});
    const strats = Object.keys(s.profile_overrides || {});
    let scope = "global", scopeLabel = "Global (all markets)";
    if (coins.length) { scope = "coin"; scopeLabel = `Per-coin · ${coins.join(", ")}`; }
    else if (strats.length) { scope = "strategy"; scopeLabel = `Per-strategy · ${strats.join(", ")}`; }

    let rows;
    if (method === "fixed_pct") {
        rows = [
            { label: "Take-Profit target", value: `${num(s.fixed_target_pct, 3.0)}%` },
            { label: "Stop-Loss", value: `${stop}%` },
        ];
    } else if (method === "atr_trailing" || method === "chandelier") {
        rows = [
            { label: "Trail arm", value: `${num(s.trail_arm_pct, 1.6)}%` },
            { label: "Trail distance", value: `${num(s.trail_distance_pct, 0.9)}%` },
            { label: "Hard stop-loss", value: `${stop}%` },
        ];
    } else {
        const trailMult = num(s.profile_overrides?.hunter?.trail_atr_mult, 2.0);
        rows = [
            { label: "Trail multiplier", value: `${trailMult}x` },
            { label: "Breakeven arm", value: `${num(s.trail_arm_pct, 1.6)}%` },
            { label: "Hard stop-loss", value: `${stop}%` },
        ];
    }
    return { method, typeLabel, scope, scopeLabel, rows };
}
