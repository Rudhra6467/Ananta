"""Per-strategy Strategy Profile — the single identity a strategy carries across LIVE, PAPER
and the Research Lab: allowed market regimes + default exit method (+ room to grow: risk,
timeframe, confidence, cooldown…).

SOURCE OF TRUTH: RiskSettings.profile_overrides[<engine_key>] so the live engine, exit engine
and Lab all read one place (no schema migration needed to add fields later).

Strategies SHIP recommended defaults (RECOMMENDED) — the "Apply Recommended" action copies a
strategy's recommendation into the user's profile; the user can then customise or reset. This
keeps the matrix in the backend (research-owned), not hard-coded in the frontend, so it can
evolve (per-market defaults, marketplace strategies shipping their own config, etc.).
"""
from __future__ import annotations

# All market regimes the classifier can emit (regime.py). Exposed to the UI as-is so new
# strategies can use REVERSAL / NEUTRAL without a frontend change.
REGIMES = ["TREND_UP", "TREND_DOWN", "COMPRESSION", "RANGE", "REVERSAL", "NEUTRAL"]

# Exit methods a profile can request + their tunable params (defaults shown).
EXIT_METHODS = {
    "atr":    {"label": "ATR Trailing", "params": {"atr_multiplier": 2.5}},
    "fixed":  {"label": "Fixed TP / SL", "params": {"target_profit": 5.0, "target_loss": 4.0}},
    "native": {"label": "Native (engine default)", "params": {}},
}

# Shippable validation matrix (recommended defaults per strategy engine key), derived from the
# 1-year multi-symbol validation (run 63579490) + regime-conditional edge analysis.
#   allowed_regimes · exit {method + params} · enabled · note
# Exit default is Fixed TP/SL 5% / 3.5% — the only exit that consistently banked winners in the
# validation. Trend/breakout strategies keep the same fixed exit for parity until ATR-trail is re-audited.
#
# Tiers:
#   Tier 1 (enabled=True)  — proven positive edge in their regimes → ship ON for new accounts.
#   Tier 2 (enabled=False, regimes set) — regime edge exists but needs more work → configured but OFF.
#   Tier 3 (enabled=False, regimes []) — no statistical edge → fully OFF.
_FIXED = {"method": "fixed", "target_profit": 5.0, "target_loss": 3.5}

RECOMMENDED: dict[str, dict] = {
    # ---- Tier 1: enabled by default (paper-ready) ----
    "ema-cross":            {"allowed_regimes": ["COMPRESSION", "RANGE"], "exit": dict(_FIXED), "enabled": True,  "priority": "highest", "note": "Only clean overall winner; strong in compression + range."},
    "time-series-momentum": {"allowed_regimes": ["COMPRESSION"],          "exit": dict(_FIXED), "enabled": True,  "priority": "high",    "note": "Solid compression profit; restricted to kill trend-down losses."},
    "stochastic-momentum":  {"allowed_regimes": ["COMPRESSION", "RANGE"], "exit": dict(_FIXED), "enabled": True,  "priority": "high",    "note": "Positive in both regimes that matter."},
    # ---- Tier 2: disabled by default, regime edge exists, needs tuning ----
    "supertrend":           {"allowed_regimes": ["COMPRESSION"],          "exit": dict(_FIXED), "enabled": False, "priority": "medium",  "note": "Surprising compression edge; re-enable after regime-lock test."},
    "donchian-breakout":    {"allowed_regimes": ["COMPRESSION"],          "exit": dict(_FIXED), "enabled": False, "priority": "medium",  "note": "Compression edge; TREND_UP destroys it."},
    "keltner-breakout":     {"allowed_regimes": ["RANGE"],                "exit": dict(_FIXED), "enabled": False, "priority": "low",     "note": "Tiny range profit; toxic elsewhere."},
    "continuation":         {"allowed_regimes": ["TREND_UP"],             "exit": dict(_FIXED), "enabled": False, "priority": "medium",  "note": "Only traded in trend-up; still slightly negative → tighten entries."},
    "atr-breakout":         {"allowed_regimes": ["TREND_DOWN"],           "exit": dict(_FIXED), "enabled": False, "priority": "low",     "note": "Very few trades; needs a different breakout threshold."},
    # ---- Tier 3: fully OFF (no statistical edge in the validation window) ----
    "rsi-momentum":         {"allowed_regimes": [], "exit": dict(_FIXED), "enabled": False, "priority": "hold", "note": "Worst performer (-$2,109). Disabled until redesigned."},
    "bollinger-mr":         {"allowed_regimes": [], "exit": dict(_FIXED), "enabled": False, "priority": "hold", "note": "Negative in every regime."},
    "vwap-mr":              {"allowed_regimes": [], "exit": dict(_FIXED), "enabled": False, "priority": "hold", "note": "Negative everywhere."},
    "macd-trend":           {"allowed_regimes": [], "exit": dict(_FIXED), "enabled": False, "priority": "hold", "note": "Negative everywhere."},
    "squeeze":              {"allowed_regimes": [], "exit": dict(_FIXED), "enabled": False, "priority": "hold", "note": "0% win rate in window. Disabled until redesigned."},
    "turtle":               {"allowed_regimes": [], "exit": dict(_FIXED), "enabled": False, "priority": "hold", "note": "No meaningful contribution; re-evaluate later."},
    "hunter":               {"allowed_regimes": [], "exit": dict(_FIXED), "enabled": False, "priority": "hold", "note": "No material trades in this window; re-enable after per-strategy filter re-validation."},
}

# Bump when RECOMMENDED changes so accounts get re-seeded once (see server startup + provisioning).
MATRIX_VERSION = "2026-07-26.v1"


def _split_exit(exit_block: dict | None) -> tuple[str, dict]:
    ex = dict(exit_block or {})
    method = ex.pop("method", "native")
    if method not in EXIT_METHODS:
        method = "native"
    params = {k: v for k, v in ex.items() if k in ("atr_multiplier", "target_profit", "target_loss")}
    return method, params


def recommended_profile(key: str) -> dict | None:
    """The shipped recommendation for a strategy, as a normalized profile (source=recommended)."""
    r = RECOMMENDED.get(key)
    if not r:
        return None
    method, params = _split_exit(r.get("exit"))
    return {
        "enabled": bool(r.get("enabled", True)),
        "allowed_regimes": [x for x in (r.get("allowed_regimes") or []) if x in REGIMES],
        "exit_method": method,
        "exit_params": params,
        "source": "recommended",
        "note": r.get("note"),
        "priority": r.get("priority"),
    }


def normalize_profile(raw: dict | None) -> dict:
    """Coerce arbitrary input into a clean, self-contained profile."""
    raw = raw or {}
    # Accept a nested {"exit": {...}} too (frontend/marketplace convenience).
    if "exit" in raw and "exit_method" not in raw:
        method, params = _split_exit(raw.get("exit"))
    else:
        method = raw.get("exit_method") if raw.get("exit_method") in EXIT_METHODS else "native"
        params = {k: v for k, v in (raw.get("exit_params") or {}).items()
                  if k in ("atr_multiplier", "target_profit", "target_loss")}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "allowed_regimes": [x for x in (raw.get("allowed_regimes") or []) if x in REGIMES],
        "exit_method": method,
        "exit_params": params,
        "source": raw.get("source") or "custom",
    }


def is_disabled(profile: dict | None) -> bool:
    return bool(profile) and profile.get("enabled") is False


def regime_allowed(profile: dict | None, regime: str | None) -> bool:
    """True if a strategy may OPEN an entry in this regime given its profile.
      * no profile / no regimes configured  -> DISABLED (empty allowed_regimes == benched)
      * profile disabled (enabled == False)  -> never
      * regimes configured                   -> only those regimes
    NOTE (2026-07-26): empty/absent allowed_regimes now means DISABLED (was "trade all").
    Every catalog strategy is seeded with the Recommended Matrix, so "no regimes" is an
    explicit OFF, never an accidental trade-everything.
    """
    if not profile:
        return False
    if profile.get("enabled") is False:
        return False
    regimes = profile.get("allowed_regimes")
    if not regimes:
        return False
    return regime in regimes


def profile_status(profile: dict | None) -> dict:
    """Human-facing status for the UI."""
    if not profile or profile.get("enabled") is False:
        return {"state": "disabled", "label": "Disabled",
                "reason": "Strategy benched — no entries evaluated."}
    regimes = (profile or {}).get("allowed_regimes") or []
    if not regimes:
        return {"state": "disabled", "label": "Disabled — no active regimes",
                "reason": "No regime selected; strategy will not open entries. Pick at least one regime."}
    return {"state": "enabled", "label": "Enabled",
            "reason": f"Trades only in: {', '.join(regimes)}."}


def recommended_matrix() -> dict[str, dict]:
    """The full Recommended Matrix as normalized profiles keyed by engine key — used to SEED a
    fresh account (and the owner/house book) so the validated regime + exit defaults are enforced
    out of the box."""
    out: dict[str, dict] = {}
    for key in RECOMMENDED:
        prof = recommended_profile(key)
        if prof:
            out[key] = prof
    return out


def apply_matrix(existing: dict | None) -> dict:
    """Merge the Recommended Matrix into a profile_overrides dict: overwrite each strategy's
    enabled / allowed_regimes / exit while PRESERVING any extra per-strategy exit-engine field
    patches already stored (structural_stop_enabled, trail_arm_r, …)."""
    ov = dict(existing or {})
    for key, prof in recommended_matrix().items():
        entry = dict(ov.get(key) or ov.get(key.lower()) or {})
        entry.update(prof)
        ov.pop(key.lower(), None)
        ov[key] = entry
    return ov
