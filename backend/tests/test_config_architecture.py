"""Guards for the config architecture (Settings unification, Option A).

These are pure/static checks — no DB or network — so they run fast and protect the
invariant that the live engine reads only RiskSettings and that clamp bounds live in
a single place.
"""
import pathlib

import pytest

from models import RiskSettings
from settings_spec import (
    FLOAT_CLAMPS,
    INT_CLAMPS,
    PROFILE_CLAMPS,
    clamp_profile_value,
    clamp_settings_dict,
    clamp_value,
)
from strategy import engine_backed_params, get_schema

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ENGINE_MODULES = [
    "trading_engine.py", "exit_engine.py", "risk_engine.py",
    "position_watcher.py", "shadow_sim.py", "levels.py",
]


def test_clamp_keys_are_real_risksettings_fields():
    fields = set(RiskSettings.model_fields.keys())
    for k in list(FLOAT_CLAMPS) + list(INT_CLAMPS):
        assert k in fields, f"clamp registry references unknown RiskSettings field: {k}"


def test_clamp_value_bounds():
    assert clamp_value("min_confidence", 5.0) == 1.0
    assert clamp_value("min_confidence", -1.0) == 0.0
    assert clamp_value("max_concurrent_positions", 999) == 20
    assert clamp_value("max_concurrent_positions", 0) == 1
    # unknown key passes through untouched
    assert clamp_value("not_a_field", 1234) == 1234
    # int fields return ints
    assert isinstance(clamp_value("sl_cooldown_seconds", 10), int)


def test_clamp_profile_value_bounds():
    assert clamp_profile_value("trail_atr_mult", 100) == 6.0
    assert clamp_profile_value("profit_arm_pct", 0.0) == 0.5
    assert clamp_profile_value("unknown", 42) == 42


def test_clamp_settings_dict_in_place():
    data = {"min_confidence": 2.0, "max_daily_loss_pct": 999.0, "trading_mode": "LIVE"}
    out = clamp_settings_dict(data)
    assert out is data
    assert data["min_confidence"] == 1.0
    assert data["max_daily_loss_pct"] == 50.0
    assert data["trading_mode"] == "LIVE"  # non-numeric untouched


def test_profile_clamp_keys_known():
    assert set(PROFILE_CLAMPS) == {"trail_atr_mult", "profit_arm_pct", "time_exit_hours"}


@pytest.mark.parametrize("module", ENGINE_MODULES)
def test_engine_modules_do_not_read_strategy_configs(module):
    """The engine must read config only from RiskSettings, never strategy_configs.

    We look for actual collection access (`db.strategy_configs` / `.strategy_configs.`),
    not prose mentions in comments/docstrings.
    """
    src = (BACKEND / module).read_text()
    assert "db.strategy_configs" not in src and ".strategy_configs." not in src, (
        f"{module} accesses the strategy_configs collection — the engine must read only RiskSettings"
    )


def test_engine_backed_params_filters_forward_looking_and_maps_to_fields():
    """Phase-2 activation: only engine-backed params (that map to RiskSettings fields)
    survive; forward-looking knobs (e.g. exit_method) are dropped."""
    schema = get_schema("hunter")
    resolved = dict(schema.defaults())
    resolved.update({"rsi_reset_max": 42.0, "normal_lot_usd": 120.0, "exit_method": "atr", "target_profit": 9.0})
    eb = engine_backed_params(schema, resolved)
    # engine-backed & mapped to real RiskSettings fields
    fields = set(RiskSettings.model_fields.keys())
    assert eb.get("rsi_reset_max") == 42.0
    assert eb.get("normal_lot_usd") == 120.0
    for k in eb:
        assert k in fields, f"engine-backed param {k} is not a RiskSettings field"
    # forward-looking knobs dropped
    assert "exit_method" not in eb
    assert "target_profit" not in eb
