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

# Shippable validation matrix (recommended defaults per strategy engine key).
#   allowed_regimes · exit {method + params} · enabled · note
RECOMMENDED: dict[str, dict] = {
    "ema-cross":            {"allowed_regimes": ["TREND_UP", "COMPRESSION"], "exit": {"method": "atr", "atr_multiplier": 2.5, "target_profit": 8.0}, "enabled": True, "priority": "highest", "note": "Trend + compression breakouts; let winners run."},
    "supertrend":           {"allowed_regimes": ["TREND_UP", "TREND_DOWN"], "exit": {"method": "atr", "atr_multiplier": 2.5}, "enabled": True, "priority": "high", "note": "Bi-directional trend rider."},
    "macd-trend":           {"allowed_regimes": ["TREND_UP"], "exit": {"method": "atr", "atr_multiplier": 2.5}, "enabled": True, "priority": "high", "note": "Trend confirmation."},
    "atr-breakout":         {"allowed_regimes": ["COMPRESSION"], "exit": {"method": "atr", "atr_multiplier": 2.5}, "enabled": True, "priority": "high", "note": "Compression breakout only."},
    "keltner-breakout":     {"allowed_regimes": ["COMPRESSION"], "exit": {"method": "atr", "atr_multiplier": 2.5}, "enabled": True, "priority": "medium", "note": "Compression breakout."},
    "donchian-breakout":    {"allowed_regimes": ["COMPRESSION", "TREND_UP"], "exit": {"method": "atr", "atr_multiplier": 2.5}, "enabled": True, "priority": "medium", "note": "Channel breakout."},
    "time-series-momentum": {"allowed_regimes": ["COMPRESSION"], "exit": {"method": "fixed", "target_profit": 5.0, "target_loss": 4.0}, "enabled": True, "priority": "high", "note": "Fixed TP/SL first; ATR trail once data supports it."},
    "stochastic-momentum":  {"allowed_regimes": ["COMPRESSION"], "exit": {"method": "fixed", "target_profit": 5.0, "target_loss": 4.0}, "enabled": True, "priority": "high", "note": "Fixed TP/SL."},
    "turtle":               {"allowed_regimes": ["TREND_UP"], "exit": {"method": "atr", "atr_multiplier": 2.5}, "enabled": True, "priority": "medium", "note": "Strong uptrend only."},
    "continuation":         {"allowed_regimes": ["TREND_UP"], "exit": {"method": "atr", "atr_multiplier": 2.5}, "enabled": True, "priority": "medium", "note": "Trend pullback continuation."},
    "bollinger-mr":         {"allowed_regimes": ["RANGE"], "exit": {"method": "fixed", "target_profit": 3.0, "target_loss": 2.0}, "enabled": True, "priority": "medium", "note": "Range mean reversion; tight SL, no trailing."},
    "vwap-mr":              {"allowed_regimes": ["RANGE"], "exit": {"method": "fixed", "target_profit": 3.0, "target_loss": 2.5}, "enabled": True, "priority": "low", "note": "Range mean reversion."},
    "rsi-momentum":         {"allowed_regimes": [], "exit": {"method": "fixed"}, "enabled": False, "priority": "hold", "note": "Disabled — needs redesign."},
    "hunter":               {"allowed_regimes": ["TREND_UP", "REVERSAL"], "exit": {"method": "native"}, "enabled": True, "priority": "high", "note": "Buy fear at structural support."},
    "squeeze":              {"allowed_regimes": ["COMPRESSION"], "exit": {"method": "native"}, "enabled": True, "priority": "high", "note": "Volatility squeeze breakout."},
}


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
      * no profile / no regimes configured  -> allowed (unconfigured == trade all, backward compatible)
      * profile disabled (enabled == False)  -> never
      * regimes configured                   -> only those regimes
    """
    if not profile:
        return True
    if profile.get("enabled") is False:
        return False
    regimes = profile.get("allowed_regimes")
    if not regimes:
        return True
    return regime in regimes


def profile_status(profile: dict | None) -> dict:
    """Human-facing status for the UI."""
    if is_disabled(profile):
        return {"state": "disabled", "label": "Disabled", "reason": "Strategy benched — no entries evaluated."}
    regimes = (profile or {}).get("allowed_regimes") or []
    if not regimes:
        return {"state": "all", "label": "Enabled — all regimes",
                "reason": "No regime filter set; trades in every market condition."}
    return {"state": "enabled", "label": "Enabled",
            "reason": f"Trades only in: {', '.join(regimes)}."}
