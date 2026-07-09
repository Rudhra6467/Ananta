"""
settings_spec.py — the SINGLE authoritative registry for tunable `RiskSettings`
fields and their hard validation bounds.

WHY THIS EXISTS
---------------
`RiskSettings` (the `settings` singleton document) is the one and only source of
truth the live trading/exit/risk engines read. Three write-paths mutate it:

  1. PUT /api/settings          — direct owner edits (server.update_settings)
  2. Lab promotion             — apply an approved research proposal
                                  (lab.proposals.apply_to_settings)
  3. AI Coach "apply"          — apply one whitelisted Coach recommendation
                                  (coach.validate_apply)

Historically each path carried its own copy of the numeric clamp tables, which
drifted and was confusing. This module centralises the HARD bounds so paths (1)
and (2) share one definition. Path (3) intentionally layers *narrower advisory*
bounds on top (see coach.APPLYABLE) but still stays within these hard bounds.

OWNERSHIP MAP (read CONFIG_ARCHITECTURE.md for the full story):
  - RiskSettings.<field>            -> FLOAT_CLAMPS / INT_CLAMPS below
  - RiskSettings.profile_overrides  -> PROFILE_CLAMPS below (per-strategy exit tweaks)

These are HARD limits (sanity guards). They are deliberately wide; product-level
"safe" bands live with each feature (e.g. the Coach whitelist).
"""
from __future__ import annotations

# Hard bounds for float-valued RiskSettings fields.
FLOAT_CLAMPS: dict[str, tuple[float, float]] = {
    "max_spread_pct": (0.001, 5.0),
    "max_daily_loss_pct": (0.1, 50.0),
    "min_confidence": (0.0, 1.0),
    "position_size_pct_min": (0.1, 10.0),
    "position_size_pct_max": (0.1, 20.0),
    "normal_lot_usd": (1.0, 1000.0),
    "strong_lot_usd": (1.0, 1000.0),
    "strong_min_confidence": (0.0, 1.0),
    "strong_min_atr_percentile": (0.0, 100.0),
    "strong_min_adx": (0.0, 100.0),
    "stop_loss_pct": (0.1, 50.0),
    "trail_arm_pct": (0.1, 50.0),
    "trail_distance_pct": (0.1, 50.0),
    "vault_max_override_usd": (1.0, 1000000.0),
    "taker_fee_pct": (0.0, 5.0),
    "maker_fee_pct": (0.0, 5.0),
    "breakout_paper_slippage_pct": (0.0, 5.0),
    "breakout_lot_usd": (1.0, 10000.0),
    "breakout_min_confidence": (0.0, 1.0),
    "breakout_volume_percentile": (0.0, 100.0),
    "breakout_max_spread_pct": (0.0, 5.0),
    "breakout_trail_arm_pct": (0.1, 50.0),
    "breakout_trail_distance_pct": (0.1, 50.0),
    # promotable technical gates (previously clamped only in lab.proposals):
    "rsi_reset_max": (0.0, 100.0),
    "level_proximity_pct": (0.1, 10.0),
    "squeeze_vol_expansion_min": (1.0, 5.0),
}

# Hard bounds for int-valued RiskSettings fields.
INT_CLAMPS: dict[str, tuple[int, int]] = {
    "sl_cooldown_seconds": (0, 86400),
    "trail_cooldown_seconds": (0, 86400),
    "max_concurrent_positions": (1, 20),
    "position_watcher_interval_seconds": (5, 300),
}

# Hard bounds for per-strategy exit-profile overrides (RiskSettings.profile_overrides).
PROFILE_CLAMPS: dict[str, tuple[float, float]] = {
    "trail_atr_mult": (0.5, 6.0),
    "profit_arm_pct": (0.5, 30.0),
    "time_exit_hours": (1.0, 1000.0),
}


def clamp_value(key: str, val):
    """Clamp a single RiskSettings field to its hard bounds. Unknown keys pass through."""
    if val is None:
        return val
    if key in FLOAT_CLAMPS:
        lo, hi = FLOAT_CLAMPS[key]
        return max(lo, min(hi, float(val)))
    if key in INT_CLAMPS:
        lo, hi = INT_CLAMPS[key]
        return max(lo, min(hi, int(val)))
    return val


def clamp_profile_value(field: str, val):
    """Clamp a single profile-override field to its hard bounds. Unknown fields pass through."""
    if val is None or field not in PROFILE_CLAMPS:
        return val
    lo, hi = PROFILE_CLAMPS[field]
    return max(lo, min(hi, val))


def clamp_settings_dict(data: dict) -> dict:
    """Clamp every recognised field in an update payload, in place. Returns the same dict."""
    for k in list(data.keys()):
        if data[k] is None:
            continue
        if k in FLOAT_CLAMPS or k in INT_CLAMPS:
            data[k] = clamp_value(k, data[k])
    return data
