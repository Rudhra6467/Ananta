"""Tests for the manual approval gate (lab/proposals.py)."""
from lab.proposals import apply_to_settings, best_params_from_run, build_diff
from models import RiskSettings


def test_best_params_walk_forward_majority():
    run = {"kind": "walk_forward", "result": {"fold_reports": [
        {"best_params": {"prof:hunter:profit_arm_pct": 5.0}, "oos_metric": 1.2},
        {"best_params": {"prof:hunter:profit_arm_pct": 5.0}, "oos_metric": 0.8},
        {"best_params": {"prof:hunter:profit_arm_pct": 6.0}, "oos_metric": 0.4},
    ]}}
    assert best_params_from_run(run) == {"prof:hunter:profit_arm_pct": 5.0}  # majority vote


def test_best_params_grid_and_sensitivity():
    grid = {"kind": "grid_search", "result": {"best": {"params": {"set:stop_loss_pct": 8.0}}}}
    assert best_params_from_run(grid) == {"set:stop_loss_pct": 8.0}
    sens = {"kind": "sensitivity", "result": {"target": "prof:squeeze:trail_atr_mult",
            "curve": [{"value": 2.0, "metric": 1.0}, {"value": 2.5, "metric": 3.0}]}}
    assert best_params_from_run(sens) == {"prof:squeeze:trail_atr_mult": 2.5}
    assert best_params_from_run({"kind": "backtest", "result": {}}) == {}


def test_build_diff_and_apply():
    s = RiskSettings()
    params = {"set:stop_loss_pct": 8.0, "prof:squeeze:trail_atr_mult": 2.0}
    diff = build_diff(params, s)
    assert any(d["key"] == "set:stop_loss_pct" for d in diff)
    changed = apply_to_settings(s, params)
    assert s.stop_loss_pct == 8.0
    assert s.profile_overrides["squeeze"]["trail_atr_mult"] == 2.0
    assert len(changed) == 2


def test_apply_clamps_out_of_range():
    s = RiskSettings()
    apply_to_settings(s, {"prof:hunter:trail_atr_mult": 99.0})  # clamp hi = 6.0
    assert s.profile_overrides["hunter"]["trail_atr_mult"] == 6.0
