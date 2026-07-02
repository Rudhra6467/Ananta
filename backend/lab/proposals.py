"""
lab/proposals.py — manual approval gate: translate a completed Lab run's best params
into a production settings proposal (diff), and apply it on owner approval.

Safety: lab values NEVER auto-write to production. A proposal is created (PROPOSED),
the owner reviews the current→proposed diff, then explicitly applies it.

Param keys: "set:<field>" -> RiskSettings field; "prof:<strategy>:<field>" -> exit profile
override (stored in RiskSettings.profile_overrides so the live engine reads it).
"""
from __future__ import annotations

from collections import Counter

from exit_engine import get_profile

# clamps for direct RiskSettings fields (mirror the /settings validation)
_SET_CLAMP = {
    "stop_loss_pct": (0.1, 50.0), "trail_arm_pct": (0.1, 50.0), "trail_distance_pct": (0.1, 50.0),
    "rsi_reset_max": (0.0, 100.0), "level_proximity_pct": (0.1, 10.0),
    "max_concurrent_positions": (1, 20), "normal_lot_usd": (1.0, 1000.0),
}
_PROF_CLAMP = {
    "trail_atr_mult": (0.5, 6.0), "profit_arm_pct": (0.5, 30.0), "time_exit_hours": (1.0, 1000.0),
}

_LABELS = {
    "prof:squeeze:trail_atr_mult": "Squeeze · ATR Trail Multiple",
    "prof:hunter:trail_atr_mult": "Hunter · ATR Trail Multiple",
    "prof:hunter:profit_arm_pct": "Hunter · Profit-Lock %",
    "prof:squeeze:profit_arm_pct": "Squeeze · Profit-Lock %",
    "set:stop_loss_pct": "Global · Stop-Loss %",
    "set:trail_arm_pct": "Global · Trail Arm %",
}


def _label(key: str) -> str:
    return _LABELS.get(key, key)


def best_params_from_run(run: dict) -> dict:
    """Extract the recommended params {prefixed_key: value} from a DONE run."""
    kind = run.get("kind")
    res = run.get("result") or {}
    if kind == "grid_search":
        best = res.get("best")
        return dict(best["params"]) if best and best.get("params") else {}
    if kind == "sensitivity":
        curve = [c for c in res.get("curve", []) if c.get("metric") is not None]
        if not curve:
            return {}
        top = max(curve, key=lambda c: c["metric"])
        return {res.get("target"): top["value"]}
    if kind == "walk_forward":
        folds = [f for f in res.get("fold_reports", []) if f.get("best_params")]
        scored = [f for f in folds if f.get("oos_metric") is not None] or folds
        if not scored:
            return {}
        best_fold = max(scored, key=lambda f: f.get("oos_metric") if f.get("oos_metric") is not None else -1e9)
        keys = list(scored[0]["best_params"].keys())
        out = {}
        for k in keys:
            vals = [f["best_params"].get(k) for f in scored if k in f["best_params"]]
            counts = Counter(vals)
            top_val, top_n = counts.most_common(1)[0]
            # unique majority wins; otherwise defer to the highest-OOS fold's value
            out[k] = top_val if list(counts.values()).count(top_n) == 1 else best_fold["best_params"][k]
        return out
    return {}  # backtest has no params to promote


def _current_value(key: str, settings):
    if key.startswith("set:"):
        return getattr(settings, key[4:], None)
    if key.startswith("prof:"):
        _, strat, field = key.split(":", 2)
        prof = get_profile(strat)
        ov = getattr(settings, "profile_overrides", {}) or {}
        return (ov.get(strat) or {}).get(field, getattr(prof, field, None))
    return None


def _clamp(val, lo, hi):
    try:
        return max(lo, min(hi, val))
    except TypeError:
        return val


def build_diff(params: dict, settings) -> list[dict]:
    return [{"key": k, "target": _label(k), "current": _current_value(k, settings), "proposed": v}
            for k, v in params.items()]


def apply_to_settings(settings, params: dict) -> list[dict]:
    """Mutate `settings` in place with the proposal. Returns the list of applied changes."""
    changed = []
    ov = {k: dict(v) for k, v in (getattr(settings, "profile_overrides", {}) or {}).items()}
    for k, v in params.items():
        if k.startswith("set:"):
            field = k[4:]
            if hasattr(settings, field):
                lo, hi = _SET_CLAMP.get(field, (None, None))
                val = _clamp(v, lo, hi) if lo is not None else v
                setattr(settings, field, val)
                changed.append({"target": _label(k), "value": val})
        elif k.startswith("prof:"):
            _, strat, field = k.split(":", 2)
            lo, hi = _PROF_CLAMP.get(field, (None, None))
            val = _clamp(v, lo, hi) if lo is not None else v
            ov.setdefault(strat, {})[field] = val
            changed.append({"target": _label(k), "value": val})
    settings.profile_overrides = ov
    return changed
