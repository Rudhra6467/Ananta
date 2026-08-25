"""Continuation is hist research shadow — not Wave A, not live watch."""
from lab.observation_replay import (
    RESEARCH_REGIMES,
    RESEARCH_SHADOW,
    WAVE_A,
    WAVE_A_REGIMES,
    _research_ok,
    _wave_a_ok,
)


def test_wave_a_unchanged():
    assert WAVE_A == ("hunter", "squeeze", "bollinger-mr")
    assert "continuation" not in WAVE_A
    assert RESEARCH_SHADOW == ("continuation",)


def test_continuation_gate_is_trend_up_not_wave_a():
    assert _research_ok("continuation", "TREND_UP")
    assert not _research_ok("continuation", "REVERSAL")
    assert not _wave_a_ok("continuation", "TREND_UP")
    assert WAVE_A_REGIMES["hunter"] == frozenset({"REVERSAL"})
    assert RESEARCH_REGIMES["continuation"] == frozenset({"TREND_UP"})
