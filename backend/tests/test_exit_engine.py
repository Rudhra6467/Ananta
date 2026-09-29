"""Unit tests for the Universal Exit Engine (Phase F) — pure compute, no DB."""
from datetime import datetime, timedelta, timezone

from exit_engine import (
    ACT_EXIT_FULL,
    ACT_EXIT_PARTIAL,
    ACT_NONE,
    ACT_TIGHTEN,
    PROFILES,
    _module_A_structural,
    _module_B_momentum,
    _module_D_ema_loss,
    _module_F_profit_protection,
    evaluate_exit_engine,
    get_profile,
)
from models import Position, RiskSettings


def _pos(**kw) -> Position:
    base = dict(symbol="BTC/USD", quantity=1.0, avg_cost=100.0, peak_price=100.0, trough_price=100.0)
    base.update(kw)
    return Position(**base)


def _ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# ---------- profiles ----------
def test_profiles_lookup():
    assert get_profile("squeeze").ema_priority is True
    assert get_profile("hunter").profit_arm_pct == 5.0
    assert get_profile("relative_strength").time_exit_hours == 120.0
    assert get_profile("unknown_strategy").name == "hunter"  # default fallback


# ---------- Module A: structural / hard-stop bucket ----------
def test_module_A_structural_stop():
    s = RiskSettings()
    pos = _pos(structural_stop=98.0)
    sig = _module_A_structural(pos, last=97.5, settings=s)
    assert sig is not None and sig.action == ACT_EXIT_FULL and sig.exit_reason == "STRUCTURAL_STOP"


def test_module_A_pct_stop():
    s = RiskSettings()  # stop_loss_pct default 10%
    pos = _pos()
    assert _module_A_structural(pos, last=89.0, settings=s) is not None  # -11% < -10%
    assert _module_A_structural(pos, last=95.0, settings=s) is None      # -5% holds


def test_module_A_profit_floor_breach():
    s = RiskSettings()
    pos = _pos(locked_profit_floor=101.0)
    sig = _module_A_structural(pos, last=100.5, settings=s)
    assert sig is not None and sig.exit_reason == "PROFIT_FLOOR"


# ---------- Module F: profit protection ----------
def test_module_F_arms_floor():
    s = RiskSettings()
    prof = get_profile("hunter")  # arm at +5%
    pos = _pos(peak_price=106.0)   # MFE 6%
    sig = _module_F_profit_protection(pos, last=105.0, prof=prof, settings=s)
    assert sig is not None and sig.action == ACT_TIGHTEN
    assert round(sig.new_floor, 4) == 101.0  # +1% floor


def test_module_F_no_rearm_when_already_locked():
    s = RiskSettings()
    prof = get_profile("hunter")
    pos = _pos(peak_price=106.0, locked_profit_floor=101.0)
    assert _module_F_profit_protection(pos, last=105.0, prof=prof, settings=s) is None


def test_module_F_does_not_rearm_after_locking_at_awkward_prices():
    """Regression 2026-09-29: with non-round entries the 8-dp floor could round DOWN, so the
    stored floor sat below the unrounded target and F re-fired TIGHTEN on every tick, which
    (P3) blocked B/S/D/C/E. After one TIGHTEN is applied, F must go quiet at any entry price."""
    s = RiskSettings()
    prof = get_profile("hunter")
    rearmed = 0
    for i in range(2000):
        entry = 100.0 + i * 0.0137123456789
        pos = _pos(avg_cost=entry, peak_price=entry * 1.07)  # past +1R and the +5% arm
        first = _module_F_profit_protection(pos, last=entry * 1.05, prof=prof, settings=s)
        assert first is not None and first.action == ACT_TIGHTEN
        pos.locked_profit_floor = first.new_floor
        if _module_F_profit_protection(pos, last=entry * 1.05, prof=prof, settings=s) is not None:
            rearmed += 1
    assert rearmed == 0


def test_lower_modules_run_after_floor_locked():
    """Once the floor is locked, an EMA/trail/time exit must be able to win again."""
    s = RiskSettings()
    entry = 100.00000000449  # breakeven floor rounds DOWN at 8 dp (100.0 < entry)
    pos = _pos(avg_cost=entry, peak_price=entry * 1.03, entry_timestamp=_ago(100))  # +1R, below the +5% arm
    prof = get_profile("hunter")
    first = _module_F_profit_protection(pos, last=entry * 1.02, prof=prof, settings=s)
    pos.locked_profit_floor = first.new_floor
    d = evaluate_exit_engine(pos, entry * 1.02, None, s)  # gave back from the peak, held past 72h
    assert d.module != "F", "F must not keep re-tightening and masking the exits below it"
    assert d.action == "EXIT_FULL" and d.module in ("C", "E")


def test_module_F_breakeven_at_1R():
    """With a structural stop 3% below entry, R=3. Peak +3% => +1R => lock breakeven."""
    s = RiskSettings()
    prof = get_profile("hunter")
    pos = _pos(structural_stop=97.0, peak_price=103.0)  # R=3, MFE=+3% = 1R, below +5% arm
    sig = _module_F_profit_protection(pos, last=102.0, prof=prof, settings=s)
    assert sig is not None and sig.action == ACT_TIGHTEN
    assert round(sig.new_floor, 4) == 100.0  # breakeven = entry


# ---------- Module B: momentum exhaustion (overbought zone) ----------
def test_module_B_stretched_fires_partial():
    pos = _pos()
    ind = {"rsi": 82.0, "vol_climax": True, "exhaustion_candle": False}
    sig = _module_B_momentum(pos, ind)
    assert sig is not None and sig.action == ACT_EXIT_PARTIAL and sig.fraction == 0.5


def test_module_B_warning_needs_both_confirmations():
    pos = _pos()
    # 72 RSI with only climax (no exhaustion) should NOT fire in the warning band
    assert _module_B_momentum(pos, {"rsi": 72.0, "vol_climax": True, "exhaustion_candle": False}) is None
    # both confirmations -> fires
    assert _module_B_momentum(pos, {"rsi": 72.0, "vol_climax": True, "exhaustion_candle": True}) is not None


def test_module_B_one_time_guard():
    pos = _pos(momentum_partial_taken=True)
    assert _module_B_momentum(pos, {"rsi": 85.0, "vol_climax": True, "exhaustion_candle": True}) is None


# ---------- Module D: EMA trend loss ----------
def test_module_D_squeeze_single_close():
    prof = get_profile("squeeze")  # ema_priority
    pos = _pos(strategy="squeeze")
    ind = {"ema20": 100.0, "ema50": 99.0, "last_close": 99.5}
    sig = _module_D_ema_loss(pos, last=99.5, ind=ind, prof=prof, age_h=5.0)
    assert sig is not None and sig.exit_reason == "EMA_TREND_LOSS"


def test_module_D_hunter_requires_dead_cross():
    prof = get_profile("hunter")
    pos = _pos()
    # below 20 but NO dead-cross (ema20 > ema50) -> hold
    assert _module_D_ema_loss(pos, 99.5, {"ema20": 100.0, "ema50": 99.0, "last_close": 99.5}, prof, 10.0) is None
    # below 20 AND dead-cross -> fire
    assert _module_D_ema_loss(pos, 99.5, {"ema20": 100.0, "ema50": 101.0, "last_close": 99.5}, prof, 10.0) is not None


def test_module_D_settle_window_blocks_fresh_entry():
    prof = get_profile("squeeze")
    pos = _pos(strategy="squeeze")
    ind = {"ema20": 100.0, "ema50": 99.0, "last_close": 99.5}
    assert _module_D_ema_loss(pos, 99.5, ind, prof, age_h=0.5) is None  # too fresh


# ---------- arbitration ----------
def test_emergency_kill_exits():
    s = RiskSettings()
    pos = _pos(entry_timestamp=_ago(1))
    d = evaluate_exit_engine(pos, last_price=100.0, bars_4h=None, settings=s, emergency=True)
    assert d.action == ACT_EXIT_FULL and d.module == "KILL"


def test_structural_beats_emergency_priority():
    s = RiskSettings()
    pos = _pos(structural_stop=99.0, entry_timestamp=_ago(1))
    d = evaluate_exit_engine(pos, last_price=98.0, bars_4h=None, settings=s, emergency=True)
    assert d.module == "A"  # P1 wins over KILL (P2)


def test_no_signal_holds():
    s = RiskSettings()
    pos = _pos(entry_timestamp=_ago(1))
    d = evaluate_exit_engine(pos, last_price=100.5, bars_4h=None, settings=s)
    assert d.action == ACT_NONE


def test_time_exit_stagnant():
    s = RiskSettings()
    pos = _pos(entry_timestamp=_ago(50))  # > 48h
    d = evaluate_exit_engine(pos, last_price=100.05, bars_4h=None, settings=s)  # flat PnL
    assert d.action == ACT_EXIT_FULL and d.module == "E"
