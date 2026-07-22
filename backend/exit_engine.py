"""
exit_engine.py — Universal Exit Engine / Trade Manager (Phase F, pure compute, ZERO LLM credits).

Decoupled, centralized exit logic. Entry strategies (Hunter / Squeeze / Relative
Strength / Neutral Crab / Bear Breakdown) are ONLY responsible for identifying
entries and tagging the position with their identity (``pos.strategy``) + an
initial profile. The Universal Exit Engine owns ALL risk management thereafter.

Architecture
------------
    [Strategy Entries]  -> pass strategy identity + initial profile
            |
            v
    UNIVERSAL EXIT ENGINE
      * Multi-module evaluation (A..F), each independent, no cross-mutation
      * Deterministic priority arbitration (single-pass sort, execute highest)

Modules
-------
  A  Structural Failure   (P1)  -> EXIT_FULL    (hard stop: structural / pct / locked floor)
  -  Kill Switch / Emerg.  (P2)  -> EXIT_FULL    (injected by the caller)
  F  Profit Protection     (P3)  -> TIGHTEN      (breakeven @ +1R, then lock a +1% profit floor)
  B  Momentum Exhaustion   (P4)  -> EXIT_PARTIAL (50%: overbought ZONE + volume climax + exhaustion candle)
  S  Structure Failure     (P5)  -> EXIT_FULL    (lower-low + momentum dead: exit, don't wait for stop)
  D  EMA Trend Loss        (P5)  -> EXIT_FULL    (close below 20-EMA / dead-cross)
  C  ATR Trail             (P6)  -> EXIT_FULL    (armed trailing stop = peak - X*ATR, arms @ +2R)
  E  Time Exit             (P7)  -> EXIT_FULL    (capital-efficiency watchdog)

Telemetry (MFE/MAE, exit module, best/worst exit prices) is captured by the
position watcher on the closing leg.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from asset_profiles import eff_setting
from setup_classifier import atr, ema, rsi

# 4h bar layout: [ts, open, high, low, close, volume]
_O, _H, _L, _C, _V = 1, 2, 3, 4, 5

# Actions
ACT_NONE = "NONE"
ACT_EXIT_FULL = "EXIT_FULL"
ACT_EXIT_PARTIAL = "EXIT_PARTIAL"
ACT_TIGHTEN = "TIGHTEN"

PARTIAL_FRACTION = 0.5
PROFIT_FLOOR_PCT = 1.0  # locked profit floor once Module F arms (+1% above entry)


# ---------------------------------------------------------------------------
# Strategy-specific initial profiles. Passed into the engine via pos.strategy.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyProfile:
    name: str
    profit_arm_pct: float          # MFE % that arms Profit Protection (Module F)
    trail_atr_mult: float          # ATR multiple for the Module C trailing stop
    time_exit_hours: float | None  # hard time cap (None = no fixed limit while trend intact)
    ema_priority: bool = False     # Squeeze prioritises EMA-loss exits
    ema_settle_hours: float = 6.0  # min age before EMA-loss (D) can fire (avoid entry noise)
    breakeven_r: float = 1.0       # lock stop to breakeven once MFE >= this many R (Module F)
    trail_arm_r: float = 2.0       # arm the ATR trail once MFE >= this many R (Module C)
    structure_exit: bool = True    # enable structure-failure exit (Module S)
    structural_stop_enabled: bool = True  # enable the STRUCTURAL_STOP candidate in Module A
    ema_trend_loss_enabled: bool = True   # enable Module D (EMA trend-loss exit)
    strat_exit_enabled: bool = True       # honour the strategy's own declarative exit rule (STRAT_EXIT)


PROFILES: dict[str, StrategyProfile] = {
    # Hunter: structural + 0.5 ATR stop, protect after +5%, moderate ATR trail, 48-72h.
    "hunter": StrategyProfile("hunter", 5.0, 2.0, 72.0),
    # Squeeze: stop at opposite Keltner/20MA, protect after +4%, aggressive ATR trail,
    # no fixed time limit while trend intact; EMA loss is highly prioritised.
    "squeeze": StrategyProfile("squeeze", 4.0, 2.5, None, ema_priority=True, ema_settle_hours=2.0),
    # Relative Strength: swing-low stop, protect after +6%, EMA+ATR trail, 3-5 days.
    "relative_strength": StrategyProfile("relative_strength", 6.0, 2.0, 120.0),
    # Neutral Crab: range-boundary stop, protect after +2.5%, tight trail, exit quick on range break.
    "neutral_crab": StrategyProfile("neutral_crab", 2.5, 1.5, 24.0),
    # Bear Breakdown: structure-above stop, protect after +5%, fast trail, trend-dependent.
    "bear_breakdown": StrategyProfile("bear_breakdown", 5.0, 1.5, None, ema_priority=True),
}
DEFAULT_PROFILE = PROFILES["hunter"]


def get_profile(strategy: str | None) -> StrategyProfile:
    return PROFILES.get((strategy or "hunter").lower(), DEFAULT_PROFILE)


def profile_for(strategy: str | None, settings=None) -> StrategyProfile:
    """Base profile patched with (1) global protective-exit toggles from settings, then
    (2) any per-strategy Research-Lab / user overrides in settings.profile_overrides
    (per-strategy wins over global). Returns the untouched base profile when settings is
    None and no overrides exist (live behaviour default)."""
    from dataclasses import replace
    prof = get_profile(strategy)
    key = (strategy or "hunter").lower()
    # (1) global protective-exit defaults from RiskSettings.
    if settings is not None:
        g = {}
        for pf, sf in (("structural_stop_enabled", "structural_stop_enabled"),
                       ("ema_trend_loss_enabled", "ema_trend_loss_enabled"),
                       ("structure_exit", "structure_failure_enabled"),
                       ("strat_exit_enabled", "strat_exit_enabled")):
            if hasattr(settings, sf) and getattr(settings, sf) is not None:
                g[pf] = getattr(settings, sf)
        if g:
            prof = replace(prof, **g)
    # (2) per-strategy overrides win over the global defaults.
    ov = getattr(settings, "profile_overrides", None) if settings is not None else None
    if ov and ov.get(key):
        valid = {k: v for k, v in ov[key].items() if hasattr(prof, k)}
        if valid:
            return replace(prof, **valid)
    return prof


# ---------------------------------------------------------------------------
@dataclass
class ExitSignal:
    priority: int
    module: str                 # A..F or KILL
    action: str                 # EXIT_FULL / EXIT_PARTIAL / TIGHTEN
    exit_reason: str            # short deterministic code (TradeLog.exit_reason)
    reason: str                 # human-readable deterministic description
    confidence: float = 1.0
    fraction: float = 1.0       # for EXIT_PARTIAL
    new_floor: float | None = None   # for TIGHTEN
    stop_price: float | None = None  # expected trigger price (for slippage accounting)


@dataclass
class ExitDecision:
    action: str
    module: str | None = None
    exit_reason: str | None = None
    reason: str = ""
    confidence: float = 0.0
    fraction: float = 1.0
    new_floor: float | None = None
    stop_price: float | None = None
    signals: list[dict] = field(default_factory=list)  # all raised signals (telemetry)
    context: dict = field(default_factory=dict)


def _age_hours(iso_ts: str, now: datetime | None = None) -> float:
    if not iso_ts:
        return 0.0
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (ref - ts).total_seconds() / 3600.0)
    except Exception:
        return 0.0


def _indicators(bars_4h: list[list[float]] | None) -> dict:
    """Pure-compute indicator snapshot from 4h bars. Returns {} if insufficient."""
    n = len(bars_4h or [])
    if n < 25:
        return {}
    closes = [b[_C] for b in bars_4h]
    highs = [b[_H] for b in bars_4h]
    lows = [b[_L] for b in bars_4h]
    opens = [b[_O] for b in bars_4h]
    vols = [b[_V] for b in bars_4h]
    try:
        rsi_last = rsi(closes, 14)[-1]
        ema20 = ema(closes, 20)[-1]
        ema50 = ema(closes, 50)[-1] if n >= 50 else ema(closes, 20)[-1]
        atr_last = atr(highs, lows, closes)[-1]
    except Exception:
        return {}
    vol_avg = sum(vols[-20:]) / 20.0 if n >= 20 else (sum(vols) / n)
    last_o, last_h, last_l, last_c, last_v = opens[-1], highs[-1], lows[-1], closes[-1], vols[-1]
    rng = max(1e-12, last_h - last_l)
    upper_wick = last_h - max(last_o, last_c)
    is_red = last_c < last_o
    close_pos = (last_c - last_l) / rng  # 0 = closed on low, 1 = on high
    # exhaustion: bearish reversal candle OR shooting-star (long upper wick, weak close)
    exhaustion_candle = bool(is_red or (upper_wick / rng >= 0.5 and close_pos <= 0.45))
    return {
        "rsi": round(rsi_last, 2),
        "ema20": ema20,
        "ema50": ema50,
        "atr": atr_last,
        "vol_last": last_v,
        "vol_avg20": vol_avg,
        "vol_climax": bool(vol_avg > 0 and last_v >= 2.0 * vol_avg),
        "exhaustion_candle": exhaustion_candle,
        "last_close": last_c,
    }


# ---------------------------------------------------------------------------
# Module evaluators. Each is pure and returns ExitSignal | None.
# ---------------------------------------------------------------------------
def _module_A_structural(pos, last: float, settings, prof: StrategyProfile) -> ExitSignal | None:
    """P1 hard-stop bucket: structural stop, % stop, or a locked profit floor breach."""
    sl_pct = eff_setting(settings, pos.symbol, "stop_loss_pct")
    pct_stop = pos.avg_cost * (1.0 - sl_pct / 100.0)
    candidates: list[tuple[float, str, str]] = [(pct_stop, "STOP_LOSS", "Hard %-stop hit")]
    if pos.structural_stop and prof.structural_stop_enabled:
        candidates.append((pos.structural_stop, "STRUCTURAL_STOP", "Validated support zone broke"))
    floor = getattr(pos, "locked_profit_floor", None)
    if floor:
        candidates.append((floor, "PROFIT_FLOOR", "Locked +1% profit floor breached"))
    # The TIGHTEST (highest) protective level that price has traded through wins.
    breached = [(lvl, code, desc) for lvl, code, desc in candidates if last <= lvl]
    if not breached:
        return None
    lvl, code, desc = max(breached, key=lambda x: x[0])
    return ExitSignal(1, "A", ACT_EXIT_FULL, code, f"{desc} ({last:.6f} <= {lvl:.6f})",
                      confidence=1.0, stop_price=lvl)


def _risk_per_unit(pos, settings) -> float:
    """Initial risk (R) per unit = entry − initial stop. Falls back to the %-stop
    distance when no structural stop is set. Used for R-multiple trade management."""
    if getattr(pos, "structural_stop", None) and pos.structural_stop < pos.avg_cost:
        return pos.avg_cost - pos.structural_stop
    sl_pct = eff_setting(settings, pos.symbol, "stop_loss_pct")
    return max(1e-9, pos.avg_cost * sl_pct / 100.0)


def _module_F_profit_protection(pos, last: float, prof: StrategyProfile, settings) -> ExitSignal | None:
    """P3: staged profit protection (upgrade-only floor).
      Stage 1 — MFE >= breakeven_r (R) -> lock stop to breakeven (entry).
      Stage 2 — MFE >= profit_arm_pct  -> lock a +1% profit floor.
    The highest applicable floor wins; only tightens (never loosens)."""
    if pos.avg_cost <= 0:
        return None
    if not getattr(settings, "profit_protection_enabled", True):
        return None  # breakeven / profit-protection disabled by the user
    peak = max(pos.peak_price or pos.avg_cost, last)
    mfe_pct = (peak - pos.avg_cost) / pos.avg_cost * 100.0
    R = _risk_per_unit(pos, settings)
    mfe_r = (peak - pos.avg_cost) / R if R > 0 else 0.0

    candidates: list[tuple[float, str]] = []
    if mfe_r >= prof.breakeven_r:
        candidates.append((pos.avg_cost, f"breakeven @ +{prof.breakeven_r:.2g}R"))
    if mfe_pct >= prof.profit_arm_pct:
        candidates.append((pos.avg_cost * (1.0 + PROFIT_FLOOR_PCT / 100.0), f"+{PROFIT_FLOOR_PCT}% floor @ +{prof.profit_arm_pct:.1f}%"))
    if not candidates:
        return None
    desired_floor, why = max(candidates, key=lambda x: x[0])
    cur = getattr(pos, "locked_profit_floor", None)
    if cur is not None and cur >= desired_floor - 1e-12:
        return None  # already locked at/above target -> let lower modules manage
    return ExitSignal(3, "F", ACT_TIGHTEN, "PROFIT_PROTECT",
                      f"MFE {mfe_pct:.2f}% ({mfe_r:.2f}R) — lock {why}",
                      confidence=1.0, new_floor=round(desired_floor, 8))


def _module_S_structure(pos, last: float, ind: dict, bars_4h, prof: StrategyProfile, age_h: float) -> ExitSignal | None:
    """P5: structure-failure exit — leave when the *reason* for the trade dies rather
    than waiting for the hard stop. Fires when the higher-low structure breaks (a fresh
    lower-low) AND momentum has died (RSI < 50 and close below the 20-EMA). Guarded so it
    protects gains/breakeven, not fresh or deeply-underwater entries (Module A owns those)."""
    if not prof.structure_exit or not ind or not bars_4h:
        return None
    if age_h < prof.ema_settle_hours:
        return None
    lows = [b[_L] for b in bars_4h]
    if len(lows) < 12:
        return None
    rsi_val = ind.get("rsi")
    ema20 = ind.get("ema20")
    close = ind.get("last_close", last)
    if rsi_val is None or ema20 is None:
        return None
    momentum_dead = rsi_val < 50.0 and close < ema20
    prior_swing_low = min(lows[-12:-3])
    recent_low = min(lows[-3:])
    structure_broken = recent_low < prior_swing_low
    pnl_pct = (last - pos.avg_cost) / pos.avg_cost * 100.0
    if structure_broken and momentum_dead and pnl_pct > -1.0:
        return ExitSignal(5, "S", ACT_EXIT_FULL, "STRUCTURE_FAILURE",
                          f"Structure failed: lower-low {recent_low:.6f} < {prior_swing_low:.6f}, "
                          f"momentum dead (RSI {rsi_val:.1f}, below 20-EMA) — exit, don't wait for stop",
                          confidence=0.8)
    return None


def _module_B_momentum(pos, ind: dict) -> ExitSignal | None:
    """P4: partial 50% on a true overbought-ZONE blow-off (one-time)."""
    if getattr(pos, "momentum_partial_taken", False) or not ind:
        return None
    r = ind.get("rsi")
    if r is None:
        return None
    # Overbought ZONE (not a hard line): 70+ = warning band, 80+ = stretched.
    warning = r >= 70.0
    stretched = r >= 80.0
    climax = ind.get("vol_climax", False)
    exhaustion = ind.get("exhaustion_candle", False)
    # Stretched needs ONE confirmation; warning band needs BOTH (avoids exiting strong trends early).
    fire = (stretched and (climax or exhaustion)) or (warning and climax and exhaustion)
    if not fire:
        return None
    return ExitSignal(4, "B", ACT_EXIT_PARTIAL, "MOMENTUM_EXHAUSTION",
                      f"Overbought blow-off (RSI {r:.1f}, climax={climax}, exhaustion={exhaustion}) — trim 50%",
                      confidence=0.9 if stretched else 0.7, fraction=PARTIAL_FRACTION)


def _module_D_ema_loss(pos, last: float, ind: dict, prof: StrategyProfile, age_h: float) -> ExitSignal | None:
    """P5: trend health. Close below 20-EMA or a 20/50 dead-cross."""
    if not ind or not prof.ema_trend_loss_enabled:
        return None
    if age_h < prof.ema_settle_hours:
        return None  # don't shake a fresh entry out on entry-bar noise
    ema20, ema50 = ind.get("ema20"), ind.get("ema50")
    close = ind.get("last_close", last)
    if ema20 is None:
        return None
    below_20 = close < ema20
    dead_cross = ema50 is not None and ema20 < ema50
    if prof.ema_priority:
        # Squeeze/Bear: a single close below the 20-EMA is enough.
        if below_20:
            return ExitSignal(5, "D", ACT_EXIT_FULL, "EMA_TREND_LOSS",
                              f"Close {close:.6f} below 20-EMA {ema20:.6f} (trend lost)",
                              confidence=0.85 if dead_cross else 0.7)
        return None
    # Default (Hunter/RS): require BOTH below-20 AND dead-cross to confirm deterioration.
    if below_20 and dead_cross:
        return ExitSignal(5, "D", ACT_EXIT_FULL, "EMA_TREND_LOSS",
                          f"Close below 20-EMA + 20/50 dead-cross ({close:.6f})", confidence=0.8)
    return None


def _module_C_atr_trail(pos, last: float, ind: dict, prof: StrategyProfile, settings) -> ExitSignal | None:
    """P6: armed ATR trailing stop = peak - X*ATR (X from the strategy profile)."""
    if pos.avg_cost <= 0:
        return None
    peak = max(pos.peak_price or pos.avg_cost, last)
    arm_pct = eff_setting(settings, pos.symbol, "trail_arm_pct")
    run_up_pct = (peak - pos.avg_cost) / pos.avg_cost * 100.0
    R = _risk_per_unit(pos, settings)
    run_up_r = (peak - pos.avg_cost) / R if R > 0 else 0.0
    # Arm on EITHER the R-multiple trigger (e.g. +2R) OR the legacy %-arm, whichever first.
    if run_up_r < prof.trail_arm_r and run_up_pct < arm_pct:
        return None  # not armed yet
    atr_val = ind.get("atr") if ind else None
    if atr_val and atr_val > 0:
        trail_stop = peak - prof.trail_atr_mult * atr_val
    else:
        # fallback to the static % trail when ATR is unavailable
        dist = eff_setting(settings, pos.symbol, "trail_distance_pct")
        trail_stop = peak * (1.0 - dist / 100.0)
    if last <= trail_stop:
        return ExitSignal(6, "C", ACT_EXIT_FULL, "ATR_TRAIL",
                          f"ATR trail hit: {last:.6f} <= peak {peak:.6f} - {prof.trail_atr_mult}*ATR",
                          confidence=0.9, stop_price=trail_stop)
    return None


def _module_E_time(pos, last: float, prof: StrategyProfile, age_h: float) -> ExitSignal | None:
    """P7: capital-efficiency watchdog."""
    if pos.avg_cost <= 0:
        return None
    pnl_pct = (last - pos.avg_cost) / pos.avg_cost * 100.0
    # Stagnation rule (Hunter spec): held >= 48h and floating PnL flat in [-0.4%, +0.3%].
    if age_h >= 48.0 and -0.4 <= pnl_pct <= 0.3:
        return ExitSignal(7, "E", ACT_EXIT_FULL, "TIME_EXIT",
                          f"Stagnant {age_h:.0f}h (PnL {pnl_pct:+.2f}%) — free collateral", confidence=0.6)
    # Hard time cap from the profile (e.g. Hunter 72h, RS 120h, Crab 24h).
    if prof.time_exit_hours is not None and age_h >= prof.time_exit_hours:
        return ExitSignal(7, "E", ACT_EXIT_FULL, "TIME_EXIT",
                          f"Held {age_h:.0f}h >= {prof.time_exit_hours:.0f}h cap ({prof.name})", confidence=0.6)
    return None


# ---------------------------------------------------------------------------
def evaluate_exit_engine(
    pos,
    last_price: float,
    bars_4h: list[list[float]] | None,
    settings,
    emergency: bool = False,
    now: datetime | None = None,
    profile_override: StrategyProfile | None = None,
) -> ExitDecision:
    """Run all modules, arbitrate by hardcoded priority, return the winning action.

    ``now`` — injectable clock (defaults to real wall-clock). Backtests MUST pass the
    simulated bar time so Module E / the EMA settle-gate age correctly.
    ``profile_override`` — swap the strategy profile (optimization sweeps / Option B);
    when None the live per-strategy PROFILES entry is used. Both keep live behaviour
    byte-for-byte unchanged when omitted.
    """
    if pos.avg_cost <= 0 or last_price <= 0:
        return ExitDecision(ACT_NONE, reason="no entry/last price")

    prof = profile_override or get_profile(getattr(pos, "strategy", "hunter"))
    age_h = _age_hours(pos.entry_timestamp, now)
    ind = _indicators(bars_4h)

    signals: list[ExitSignal] = []

    # P1 — Structural Failure / hard-stop bucket
    if (s := _module_A_structural(pos, last_price, settings, prof)):
        signals.append(s)
    # P2 — Kill Switch / Emergency Stop (injected by the caller)
    if emergency:
        signals.append(ExitSignal(2, "KILL", ACT_EXIT_FULL, "EMERGENCY_STOP",
                                  "Kill-switch / emergency stop active", confidence=1.0))
    # P3 — Profit Protection
    if (s := _module_F_profit_protection(pos, last_price, prof, settings)):
        signals.append(s)
    # P4 — Momentum Exhaustion (partial)
    if (s := _module_B_momentum(pos, ind)):
        signals.append(s)
    # P5 — Structure Failure (exit when the trade thesis dies; don't wait for the stop)
    if (s := _module_S_structure(pos, last_price, ind, bars_4h, prof, age_h)):
        signals.append(s)
    # P5 — EMA Trend Loss
    if (s := _module_D_ema_loss(pos, last_price, ind, prof, age_h)):
        signals.append(s)
    # P6 — ATR Trail
    if (s := _module_C_atr_trail(pos, last_price, ind, prof, settings)):
        signals.append(s)
    # P7 — Time Exit
    if (s := _module_E_time(pos, last_price, prof, age_h)):
        signals.append(s)

    context = {
        "strategy": prof.name,
        "profile": {
            "profit_arm_pct": prof.profit_arm_pct,
            "trail_atr_mult": prof.trail_atr_mult,
            "time_exit_hours": prof.time_exit_hours,
            "ema_priority": prof.ema_priority,
            "breakeven_r": prof.breakeven_r,
            "trail_arm_r": prof.trail_arm_r,
            "structure_exit": prof.structure_exit,
        },
        "age_hours": round(age_h, 2),
        "indicators": {k: ind.get(k) for k in ("rsi", "vol_climax", "exhaustion_candle")} if ind else {},
        "locked_profit_floor": getattr(pos, "locked_profit_floor", None),
    }
    sig_dicts = [
        {"priority": s.priority, "module": s.module, "action": s.action,
         "exit_reason": s.exit_reason, "reason": s.reason, "confidence": s.confidence}
        for s in signals
    ]

    if not signals:
        return ExitDecision(ACT_NONE, signals=sig_dicts, context=context)

    # Deterministic single-pass arbitration: lowest priority number wins.
    signals.sort(key=lambda x: x.priority)
    win = signals[0]
    return ExitDecision(
        action=win.action, module=win.module, exit_reason=win.exit_reason, reason=win.reason,
        confidence=win.confidence, fraction=win.fraction, new_floor=win.new_floor,
        stop_price=win.stop_price, signals=sig_dicts, context=context,
    )
