"""Agent contract v0.1 — per-strategy cycle observations (additive, pure)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


WAVE_A_KEYS = ("hunter", "squeeze", "bollinger-mr")
CONTRACT = "ananta.shared.v0.1"
REGIME_MAP = {
    "UP": "UP",
    "TREND_UP": "UP",
    "DOWN": "DOWN",
    "TREND_DOWN": "DOWN",
    "NORMAL": "NORMAL",
    "RANGE": "NORMAL",
    "COMPRESSION": "NORMAL",
    "NEUTRAL": "NEUTRAL",
}


def data_gap_observations(*, reason: str, regime=None) -> list[dict]:
    """When Ananta could not evaluate a symbol, never imply 'no setup'."""
    return [
        {
            "strategy": key,
            "enabled": None,
            "ran": False,
            "regime": regime,
            "setup_detected": None,
            "recommendation": None,
            "confidence": None,
            "decision": "UNKNOWN",
            "skip_reason": reason,
            "execution_state": "DATA_GAP",
            "rationale": reason,
        }
        for key in WAVE_A_KEYS
    ]


def execution_state(*, enabled: bool, ran: bool, setup, took: bool, regime_ok: bool = True) -> str:
    if not enabled:
        return "NOT_ENABLED"
    if not ran:
        return "ENABLED_NOT_RUN"
    if took:
        return "TAKE_EXECUTED"
    if setup is None:
        return "RUN_UNKNOWN"
    if setup and not regime_ok:
        return "RUN_REGIME_SKIPPED"
    if setup:
        return "RUN_SETUP_SKIPPED"
    return "RUN_NO_SETUP"


def _squeeze_triggered(squeeze_eval) -> bool | None:
    if squeeze_eval is None:
        return None
    if isinstance(squeeze_eval, dict):
        return bool(squeeze_eval.get("triggered"))
    return bool(getattr(squeeze_eval, "triggered", False))


def _squeeze_reason(squeeze_eval) -> str:
    if squeeze_eval is None:
        return ""
    if isinstance(squeeze_eval, dict):
        ev = squeeze_eval.get("evidence") or {}
        return str(squeeze_eval.get("reason") or ev.get("reason") or "")[:200]
    ev = getattr(squeeze_eval, "evidence", None) or {}
    return str(getattr(squeeze_eval, "reason", None) or ev.get("reason") or "")[:200]


def _bb_entry(bollinger_eval) -> bool | None:
    if bollinger_eval is None:
        return None
    if isinstance(bollinger_eval, dict):
        if "entry" not in bollinger_eval:
            return None
        return bool(bollinger_eval.get("entry"))
    return bool(getattr(bollinger_eval, "entry", False))


def _bb_reason(bollinger_eval) -> str:
    if bollinger_eval is None:
        return ""
    if isinstance(bollinger_eval, dict):
        return str(bollinger_eval.get("reason") or "")[:200]
    return str(getattr(bollinger_eval, "reason", "") or "")[:200]


def build_wave_a_observations(
    *,
    settings,
    strategy_signals: dict | None,
    trade_doc: dict | None,
    decision: str | None,
    blocked: list | None,
    macro,
    primary,
    hunter_triggered: bool,
    hard_killed: bool,
    bars_ok: bool,
    asset_regime,
    market_regime: str | None,
    strategy_profile_disabled,
    squeeze_eval=None,
    squeeze_regime_ok: bool | None = None,
    bollinger_eval=None,
    bollinger_regime_ok: bool | None = None,
    strategy_regime_ok=None,
) -> list[dict]:
    """Build explicit observations for hunter / squeeze / bollinger-mr.

    setup_detected is True/False only when the model actually evaluated.
    None = UNKNOWN / DATA GAP — never treated as 'no setup'.
    """
    signals = strategy_signals or {}
    trade_strategy = (trade_doc or {}).get("strategy") if isinstance(trade_doc, dict) else None
    try:
        asset_reg = getattr(asset_regime, "regime", None)
    except Exception:
        asset_reg = None
    mkt_reg = market_regime
    blocked = blocked or []
    regime = asset_reg or mkt_reg

    def _reg_ok(key: str, provided: bool | None) -> bool:
        if provided is not None:
            return bool(provided)
        if callable(strategy_regime_ok):
            try:
                return bool(strategy_regime_ok(settings, key, asset_reg))
            except Exception:
                return False
        return True

    h_en = not strategy_profile_disabled(settings, "hunter")
    h_ran = (not hard_killed) and bars_ok and getattr(settings, "level_entry_enabled", True)
    h_setup = bool(primary.triggered) if primary is not None else bool(hunter_triggered)
    h_took = trade_strategy == "hunter" or (
        decision == "BUY" and trade_doc is not None and trade_strategy in (None, "hunter")
    )
    h_reg = _reg_ok("hunter", None)
    h_codes = list(getattr(primary, "reason_codes", None) or []) if primary is not None else []
    h_profile = getattr(primary, "entry_profile", None) if primary is not None else None
    if hard_killed:
        h_skip = "hard_kill_switch"
    elif not h_en:
        h_skip = "strategy_disabled"
    elif not h_ran:
        h_skip = "not_run"
    elif h_setup and not h_took and not h_reg:
        h_skip = (blocked[0] if blocked else None) or "REGIME_FILTERED"
    elif not h_setup:
        h_skip = "no_qualifying_setup"
    elif h_setup and not h_took:
        h_skip = (blocked[0] if blocked else None) or "setup_not_taken"
    else:
        h_skip = None

    sq_en = not strategy_profile_disabled(settings, "squeeze")
    sq_ran = (not hard_killed) and bars_ok and sq_en
    sq_setup = _squeeze_triggered(squeeze_eval) if sq_ran else None
    sq_took = trade_strategy == "squeeze"
    sq_reg = _reg_ok("squeeze", squeeze_regime_ok)
    if not sq_en:
        sq_skip = "strategy_disabled"
    elif hard_killed:
        sq_skip = "hard_kill_switch"
    elif not sq_ran:
        sq_skip = "not_run"
    elif sq_setup is None:
        sq_skip = "DATA_GAP"
    elif decision == "BUY" and trade_strategy == "hunter":
        sq_skip = "hunter_took_symbol"
    elif not sq_reg:
        sq_skip = "REGIME_FILTERED"
    elif not sq_setup:
        sq_skip = "no_qualifying_setup"
    elif sq_setup and not sq_took:
        sq_skip = "setup_not_taken"
    else:
        sq_skip = None

    bb_en = not strategy_profile_disabled(settings, "bollinger-mr")
    bb_ran = (not hard_killed) and bars_ok and bb_en
    bb_setup = _bb_entry(bollinger_eval) if bb_ran else None
    bb_took = trade_strategy == "bollinger-mr"
    bb_reg = _reg_ok("bollinger-mr", bollinger_regime_ok)
    if not bb_en:
        bb_skip = "strategy_disabled"
    elif hard_killed:
        bb_skip = "hard_kill_switch"
    elif not bb_ran:
        bb_skip = "not_run"
    elif bb_setup is None:
        bb_skip = "DATA_GAP"
    elif decision == "BUY" and trade_strategy in ("hunter", "squeeze"):
        bb_skip = f"{trade_strategy}_took_symbol"
    elif not bb_reg:
        bb_skip = "REGIME_FILTERED"
    elif not bb_setup:
        bb_skip = "no_qualifying_setup"
    elif bb_setup and not bb_took:
        bb_skip = "setup_not_taken"
    else:
        bb_skip = None

    def _dec(took, setup):
        if took:
            return "TAKE"
        if setup is True:
            return "SKIP"
        if setup is None:
            return "UNKNOWN"
        return "WAIT"

    return [
        {
            "strategy": "hunter",
            "enabled": h_en,
            "ran": h_ran,
            "regime": regime,
            "setup_detected": h_setup,
            "recommendation": decision if h_setup else None,
            "confidence": getattr(macro, "confidence", None) if h_setup else 0.0,
            "decision": _dec(h_took, h_setup),
            "skip_reason": None if h_took else h_skip,
            "reason_codes": h_codes,
            "entry_profile": h_profile,
            "execution_state": execution_state(
                enabled=h_en, ran=h_ran, setup=h_setup, took=h_took, regime_ok=h_reg,
            ),
            "rationale": (
                ",".join(h_codes)
                if h_codes
                else ((getattr(macro, "reason", None) or "")[:200])
            ),
        },
        {
            "strategy": "squeeze",
            "enabled": sq_en,
            "ran": sq_ran,
            "regime": regime,
            "setup_detected": sq_setup,
            "recommendation": "BUY" if sq_setup else None,
            "confidence": None,
            "decision": _dec(sq_took, sq_setup),
            "skip_reason": None if sq_took else sq_skip,
            "execution_state": execution_state(
                enabled=sq_en, ran=sq_ran, setup=sq_setup, took=sq_took, regime_ok=sq_reg,
            ),
            "rationale": _squeeze_reason(squeeze_eval) or str((signals.get("vcp") or {}).get("evidence") or "")[:200],
        },
        {
            "strategy": "bollinger-mr",
            "enabled": bb_en,
            "ran": bb_ran,
            "regime": regime,
            "setup_detected": bb_setup,
            "recommendation": "BUY" if bb_setup else None,
            "confidence": None,
            "decision": _dec(bb_took, bb_setup),
            "skip_reason": None if bb_took else bb_skip,
            "execution_state": execution_state(
                enabled=bb_en, ran=bb_ran, setup=bb_setup, took=bb_took, regime_ok=bb_reg,
            ),
            "rationale": _bb_reason(bollinger_eval) or "declarative bollinger-mr",
        },
    ]


def map_regime(raw: Any) -> str:
    if raw is None:
        return "UNKNOWN"
    if isinstance(raw, dict):
        raw = raw.get("asset") or raw.get("market") or raw.get("regime")
    key = str(raw or "").strip().upper().replace(" ", "_")
    return REGIME_MAP.get(key, "UNKNOWN")


def map_setup(v: Any) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    return "unknown"


def map_row(obs: dict) -> dict:
    rec = str(obs.get("decision") or "").upper()
    if rec not in ("TAKE", "WAIT", "SKIP", "EXIT", "REDUCE", "HOLD", "UNKNOWN"):
        rec = "UNKNOWN"
    ran = bool(obs.get("ran"))
    setup = map_setup(obs.get("setup_detected"))
    skip = obs.get("skip_reason")
    if skip is not None:
        skip = str(skip).strip() or None
    if rec in ("WAIT", "SKIP") and not skip:
        skip = "unspecified"
    if rec in ("TAKE", "EXIT", "REDUCE"):
        skip = None
    if not ran:
        rec = "UNKNOWN"
        setup = "unknown"
        skip = skip or "did_not_run"
    return {
        "strategy_id": str(obs.get("strategy") or obs.get("strategy_id") or "unknown"),
        "ran": ran,
        "setup_detected": setup,
        "recommendation": rec,
        "skip_reason": skip,
        "regime": map_regime(obs.get("regime")),
    }


def _rank_rec(rec: str) -> int:
    order = {"TAKE": 5, "EXIT": 4, "REDUCE": 4, "SKIP": 3, "HOLD": 2, "WAIT": 1, "UNKNOWN": 0}
    return order.get(rec, 0)


def aggregate_wave_a(results: list[dict]) -> list[dict]:
    buckets = {k: [] for k in WAVE_A_KEYS}
    for item in results or []:
        rows = item.get("strategy_observations") or []
        for row in rows:
            sid = str(row.get("strategy") or "")
            if sid in buckets:
                buckets[sid].append(map_row(row))
    out = []
    for sid in WAVE_A_KEYS:
        rows = buckets[sid]
        if not rows:
            out.append({
                "strategy_id": sid,
                "ran": False,
                "setup_detected": "unknown",
                "recommendation": "UNKNOWN",
                "skip_reason": "silent_strategy",
                "regime": "UNKNOWN",
            })
            continue
        ran = any(r["ran"] for r in rows)
        setups = {r["setup_detected"] for r in rows}
        if "true" in setups:
            setup = "true"
        elif setups == {"false"}:
            setup = "false"
        else:
            setup = "unknown"
        rec = max((r["recommendation"] for r in rows), key=_rank_rec)
        skip = None
        if rec not in ("TAKE", "EXIT", "REDUCE"):
            skip = next((r["skip_reason"] for r in rows if r.get("skip_reason")), "unspecified")
        regimes = {r["regime"] for r in rows}
        regime = regimes.pop() if len(regimes) == 1 else "UNKNOWN"
        if not ran:
            rec, setup, skip, regime = "UNKNOWN", "unknown", skip or "did_not_run", "UNKNOWN"
        out.append({
            "strategy_id": sid,
            "ran": ran,
            "setup_detected": setup,
            "recommendation": rec,
            "skip_reason": skip,
            "regime": regime,
        })
    return out


def wrap_cycle_run(results: list[dict], *, ran_at: str, symbol: str | None = None, profile: str = "SAFE") -> dict:
    """Additive envelope. Existing `results` stay. No KEEP. No paper TAKE."""
    now = ran_at or datetime.now(timezone.utc).isoformat()
    cid = "cyc_" + now.replace("-", "").replace(":", "").replace(".", "")[:20]
    symbols = []
    for item in results or []:
        obs = item.get("strategy_observations") or []
        symbols.append({
            "symbol": item.get("symbol"),
            "strategies": [map_row(r) for r in obs] if obs else [
                map_row({"strategy": k, "ran": False, "setup_detected": None,
                         "decision": "UNKNOWN", "skip_reason": "missing_observations"})
                for k in WAVE_A_KEYS
            ],
        })
    return {
        "contract": CONTRACT,
        "cycle_id": cid,
        "as_of_time": now,
        "event_time": now,
        "universe": "CRYPTO_LAB_10",
        "profile": profile if profile in ("SAFE", "MODERATE", "AGGRESSIVE") else "SAFE",
        "strategies": aggregate_wave_a(results),
        "symbols": symbols,
        "ran_at": now,
        "results": results,
        "bar_tf": (results or [{}])[0].get("bar_tf") if results else None,
        "last_bar_open": (results or [{}])[0].get("last_bar_open") if results else None,
        "keep": False,
        "paper_take": False,
    }
