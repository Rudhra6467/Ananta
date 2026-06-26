"""Tests for the Technical-First fusion gate (Phase 1.5)."""
from __future__ import annotations

from models import KillSwitchStatus, MarketSnapshot, RiskSettings
from risk_engine import fuse_signals


def _snap(price=100.0, spread=0.1):
    return MarketSnapshot(
        symbol="SOL/USD", price=price, bid=price * (1 - spread / 200),
        ask=price * (1 + spread / 200), spread_pct=spread, orderbook_imbalance=0.0,
        exchange="kraken",
    )


def _kill(**over):
    base = dict(spread_breach=False, daily_loss_breach=False, confidence_breach=False,
                manual_kill=False, overall_safe=True,
                details={"spread_pct": 0.1, "daily_change_pct": 0.0, "macro_confidence": 0.1})
    base.update(over)
    return KillSwitchStatus(**base)


def test_low_confidence_no_longer_blocks_a_level_touch():
    """The SOL freeze fix: macro at 0.10 NEUTRAL must NOT block a clean support touch."""
    s = RiskSettings()
    zone = {"low": 99.0, "high": 101.0, "mid": 100.0, "touches": 5}
    decision, blocked, summary = fuse_signals(
        _snap(100.0), "NEUTRAL", 0.10, s, _kill(), has_position=False,
        htf_trend_aligned=False, at_support=True, support_zone=zone,
    )
    assert decision == "BUY"
    assert "LEVEL" in summary


def test_no_support_and_neutral_macro_holds():
    s = RiskSettings()
    decision, blocked, _ = fuse_signals(
        _snap(100.0), "NEUTRAL", 0.10, s, _kill(), has_position=False,
        htf_trend_aligned=False, at_support=False, support_zone=None,
    )
    assert decision == "HOLD"


def test_bullish_macro_with_trend_still_buys():
    s = RiskSettings()
    decision, _, _ = fuse_signals(
        _snap(100.0), "BULLISH", 0.55, s, _kill(), has_position=False,
        htf_trend_aligned=True, at_support=False, support_zone=None,
    )
    assert decision == "BUY"


def test_catastrophic_bearish_vetoes_entry_even_at_support():
    s = RiskSettings()
    zone = {"low": 99.0, "high": 101.0, "mid": 100.0, "touches": 5}
    # Bearish sentiment/macro NO LONGER vetoes — it cannot block a clean technical setup.
    decision, blocked, _ = fuse_signals(
        _snap(100.0), "BEARISH", 0.90, s, _kill(), has_position=False,
        at_support=True, support_zone=zone, breaker_state="PASS",
    )
    assert decision == "BUY"


def test_existential_veto_blocks_entry_even_at_support():
    s = RiskSettings()
    zone = {"low": 99.0, "high": 101.0, "mid": 100.0, "touches": 5}
    decision, blocked, _ = fuse_signals(
        _snap(100.0), "NEUTRAL", 0.10, s, _kill(), has_position=False,
        at_support=True, support_zone=zone, breaker_state="VETO",
    )
    assert decision == "HOLD"
    assert any("EXISTENTIAL" in b for b in blocked)


def test_mild_bearish_does_not_veto_a_level_touch():
    s = RiskSettings()
    zone = {"low": 99.0, "high": 101.0, "mid": 100.0, "touches": 5}
    decision, _, _ = fuse_signals(
        _snap(100.0), "BEARISH", 0.40, s, _kill(), has_position=False,
        at_support=True, support_zone=zone, breaker_state="CAUTION",
    )
    assert decision == "BUY"


def test_open_position_holds_unless_existential_veto():
    s = RiskSettings()
    # any non-veto breaker state on an open position -> HOLD (exits owned by the watcher)
    d1, _, _ = fuse_signals(_snap(100.0), "BEARISH", 0.95, s, _kill(), has_position=True, breaker_state="CAUTION")
    assert d1 == "HOLD"
    # existential VETO -> emergency SELL
    d2, _, _ = fuse_signals(_snap(100.0), "NEUTRAL", 0.10, s, _kill(), has_position=True, breaker_state="VETO")
    assert d2 == "SELL"


def test_hard_kill_still_blocks():
    s = RiskSettings()
    d, blocked, _ = fuse_signals(
        _snap(100.0), "NEUTRAL", 0.10, s, _kill(manual_kill=True), has_position=False,
        at_support=True, support_zone={"low": 99, "high": 101, "mid": 100, "touches": 3},
    )
    assert d == "BLOCKED"
    assert "MANUAL_KILL" in blocked
