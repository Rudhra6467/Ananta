"""Agent contract v0.1 — per-strategy cycle observations (additive, pure)."""
from __future__ import annotations


def execution_state(*, enabled: bool, ran: bool, setup: bool, took: bool) -> str:
    if not enabled:
        return "NOT_ENABLED"
    if not ran:
        return "ENABLED_NOT_RUN"
    if took:
        return "TAKE_EXECUTED"
    if setup:
        return "RUN_SETUP_SKIPPED"
    return "RUN_NO_SETUP"


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
) -> list[dict]:
    """Build explicit observations for hunter / squeeze / bollinger-mr."""
    signals = strategy_signals or {}
    trade_strategy = (trade_doc or {}).get("strategy") if isinstance(trade_doc, dict) else None
    try:
        asset_reg = getattr(asset_regime, "regime", None)
    except Exception:
        asset_reg = None
    mkt_reg = market_regime
    blocked = blocked or []

    # Hunter
    h_en = not strategy_profile_disabled(settings, "hunter")
    h_ran = (not hard_killed) and bars_ok and getattr(settings, "level_entry_enabled", True)
    h_setup = bool(primary.triggered) if primary is not None else bool(hunter_triggered)
    h_took = trade_strategy == "hunter" or (
        decision == "BUY" and trade_doc is not None and trade_strategy in (None, "hunter")
    )
    if hard_killed:
        h_skip = "hard_kill_switch"
    elif not h_en:
        h_skip = "strategy_disabled"
    elif not h_ran:
        h_skip = "not_run"
    elif not h_setup:
        h_skip = "no_qualifying_setup"
    elif h_setup and not h_took:
        h_skip = (blocked[0] if blocked else None) or "setup_not_taken"
    else:
        h_skip = None

    # Squeeze
    sq_en = not strategy_profile_disabled(settings, "squeeze")
    vcp = signals.get("vcp") or {}
    sq_setup = bool(vcp.get("detected") or vcp.get("qualified"))
    sq_took = trade_strategy == "squeeze"
    sq_ran = (not hard_killed) and bars_ok and getattr(settings, "trading_mode", "PAPER") in ("PAPER", "DRY_RUN")
    if not sq_en:
        sq_skip = "strategy_disabled"
    elif hard_killed:
        sq_skip = "hard_kill_switch"
    elif not sq_ran:
        sq_skip = "not_run"
    elif decision == "BUY" and trade_strategy == "hunter":
        sq_skip = "hunter_took_symbol"
        sq_ran = True
    elif not sq_setup:
        sq_skip = "no_qualifying_setup"
    elif sq_setup and not sq_took:
        sq_skip = "setup_not_taken"
    else:
        sq_skip = None

    # Bollinger-MR — profile exists; not on independent cycle executor path
    bb_en = not strategy_profile_disabled(settings, "bollinger-mr")
    bb_ran = False
    bb_setup = False
    bb_took = trade_strategy == "bollinger-mr"
    bb_skip = "not_in_cycle_pipeline" if bb_en else "strategy_disabled"

    regime = asset_reg or mkt_reg
    return [
        {
            "strategy": "hunter",
            "enabled": h_en,
            "ran": h_ran,
            "regime": regime,
            "setup_detected": h_setup,
            "recommendation": decision if h_setup else None,
            "confidence": getattr(macro, "confidence", None) if h_setup else 0.0,
            "decision": "TAKE" if h_took else ("SKIP" if h_setup else "WAIT"),
            "skip_reason": None if h_took else h_skip,
            "execution_state": execution_state(enabled=h_en, ran=h_ran, setup=h_setup, took=h_took),
            "rationale": (getattr(macro, "reason", None) or "")[:200],
        },
        {
            "strategy": "squeeze",
            "enabled": sq_en,
            "ran": sq_ran,
            "regime": regime,
            "setup_detected": sq_setup,
            "recommendation": "BUY" if sq_setup else None,
            "confidence": None,
            "decision": "TAKE" if sq_took else ("SKIP" if sq_setup else "WAIT"),
            "skip_reason": None if sq_took else sq_skip,
            "execution_state": execution_state(enabled=sq_en, ran=sq_ran, setup=sq_setup, took=sq_took),
            "rationale": str(vcp.get("evidence") or "")[:200],
        },
        {
            "strategy": "bollinger-mr",
            "enabled": bb_en,
            "ran": bb_ran,
            "regime": regime,
            "setup_detected": bb_setup,
            "recommendation": None,
            "confidence": None,
            "decision": "WAIT",
            "skip_reason": bb_skip,
            "execution_state": execution_state(enabled=bb_en, ran=bb_ran, setup=bb_setup, took=bb_took),
            "rationale": "bollinger-mr is not on the independent cycle executor path",
        },
    ]
