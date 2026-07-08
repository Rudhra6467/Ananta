"""Strategy Center lifecycle gate — DISABLED strategies must not open new entries."""
import trading_engine as te


def test_entry_allowed_defaults_on():
    # No meta row -> strategy defaults to enabled (unchanged behaviour).
    assert te.strategy_entry_allowed({}, "hunter") is True


def test_disabled_status_blocks():
    states = {"hunter": {"status": "DISABLED", "enabled": True}}
    assert te.strategy_entry_allowed(states, "hunter") is False


def test_error_status_blocks():
    states = {"squeeze": {"status": "ERROR", "enabled": True}}
    assert te.strategy_entry_allowed(states, "squeeze") is False


def test_enabled_false_blocks():
    states = {"continuation": {"status": "PAPER", "enabled": False}}
    assert te.strategy_entry_allowed(states, "continuation") is False


def test_live_and_paper_allow_entries():
    for st in ("LIVE", "PAPER", "TESTING", "OPTIMIZING"):
        states = {"hunter": {"status": st, "enabled": True}}
        assert te.strategy_entry_allowed(states, "hunter") is True
