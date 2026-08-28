"""I2 research shadows — not Wave A, not live watch."""
from lab.observation_replay import (
    DECLARATIVE_SHADOW,
    RESEARCH_REGIMES,
    RESEARCH_SHADOW,
    WAVE_A,
    WAVE_A_REGIMES,
    _research_ok,
    _wave_a_ok,
)


def test_wave_a_unchanged():
    assert WAVE_A == ("hunter", "squeeze", "bollinger-mr")
    for k in RESEARCH_SHADOW:
        assert k not in WAVE_A
    assert RESEARCH_SHADOW == (
        "continuation", "donchian-breakout", "atr-breakout", "keltner-breakout",
    )
    assert DECLARATIVE_SHADOW == ("donchian-breakout", "atr-breakout", "keltner-breakout")


def test_research_gates_are_trend_up_not_wave_a():
    assert WAVE_A_REGIMES["hunter"] == frozenset({"REVERSAL"})
    for k in RESEARCH_SHADOW:
        assert RESEARCH_REGIMES[k] == frozenset({"TREND_UP"})
        assert _research_ok(k, "TREND_UP")
        assert not _research_ok(k, "COMPRESSION")
        assert not _wave_a_ok(k, "TREND_UP")
