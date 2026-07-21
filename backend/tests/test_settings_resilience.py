"""Regression: a null / partial settings write must never poison the singleton or 500 the
engine. Covers the launch-blocker chain (mobile NaN -> null PUT -> RiskSettings(**doc) 500)."""
from models import RiskSettings
from trading_engine import _safe_settings


def test_safe_settings_drops_nulls():
    doc = {"exit_method_pref": "fixed_pct", "fixed_target_pct": None, "stop_loss_pct": None}
    s = _safe_settings(doc)
    assert s.exit_method_pref == "fixed_pct"
    # nulls fall back to model defaults instead of raising
    assert s.fixed_target_pct == RiskSettings().fixed_target_pct
    assert s.stop_loss_pct == RiskSettings().stop_loss_pct


def test_safe_settings_bad_types_fall_back():
    doc = {"exit_method_pref": "fixed_pct", "fixed_target_pct": "not-a-number", "min_confidence": None}
    s = _safe_settings(doc)  # must not raise, must return a usable settings object
    assert isinstance(s, RiskSettings)
    assert isinstance(s.stop_loss_pct, float)


def test_safe_settings_valid_doc_roundtrips():
    doc = {"exit_method_pref": "fixed_pct", "fixed_target_pct": 4.5, "stop_loss_pct": 2.8}
    s = _safe_settings(doc)
    assert s.fixed_target_pct == 4.5 and s.stop_loss_pct == 2.8


def test_safe_settings_ignores_unknown_keys():
    s = _safe_settings({"exit_method_pref": "native", "bogus_key": 123, "_id": "x"})
    assert isinstance(s, RiskSettings) and s.exit_method_pref == "native"
