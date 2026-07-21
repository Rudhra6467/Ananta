"""Regression: deployed "Fixed % Target + Stop" exit is honored by the LIVE executor
(position_watcher) and reflected in the Lab PDF labels — full parity with the backtest.

Covers the three root causes from the Exit Engine save/parity fix:
  1. TP% is persisted & used (not just SL%).
  2. Effective method resolves from exit_method_pref (+ per-coin override).
  3. Live executor exits at fixed TP/SL instead of always using the Universal Engine.
"""
from models import Position, RiskSettings
from position_watcher import _fixed_pct_decision, _resolve_exit_method, ACT_EXIT_FULL, ACT_NONE
from lab.lab_report import _exit_label, _live_exit_desc


def _pos(entry=100.0, symbol="BTC/USD"):
    return Position(symbol=symbol, quantity=1.0, avg_cost=entry, strategy="hunter")


def test_resolve_method_global_and_per_coin():
    s = RiskSettings(exit_method_pref="fixed_pct")
    assert _resolve_exit_method(s, "BTC/USD") == "fixed_pct"
    # per-coin override wins over global
    s2 = RiskSettings(exit_method_pref="native", asset_exit_overrides={"ETH/USD": {"method": "fixed_pct"}})
    assert _resolve_exit_method(s2, "ETH/USD") == "fixed_pct"
    assert _resolve_exit_method(s2, "BTC/USD") == "native"


def test_fixed_take_profit_hit():
    s = RiskSettings(exit_method_pref="fixed_pct", fixed_target_pct=4.0, stop_loss_pct=2.5)
    # +4% -> take profit
    d = _fixed_pct_decision(_pos(100.0), 104.0, s)
    assert d.action == ACT_EXIT_FULL and d.module == "FIXED_TP"


def test_fixed_stop_loss_hit():
    s = RiskSettings(exit_method_pref="fixed_pct", fixed_target_pct=4.0, stop_loss_pct=2.5)
    # -2.5% -> stop loss
    d = _fixed_pct_decision(_pos(100.0), 97.5, s)
    assert d.action == ACT_EXIT_FULL and d.module == "FIXED_SL"


def test_fixed_hold_inside_band():
    s = RiskSettings(exit_method_pref="fixed_pct", fixed_target_pct=4.0, stop_loss_pct=2.5)
    d = _fixed_pct_decision(_pos(100.0), 101.5, s)  # +1.5%, inside band
    assert d.action == ACT_NONE


def test_per_coin_fixed_params_override_global():
    s = RiskSettings(exit_method_pref="fixed_pct", fixed_target_pct=10.0, stop_loss_pct=10.0,
                     asset_exit_overrides={"BTC/USD": {"method": "fixed_pct", "target_pct": 2.0, "stop_pct": 1.0}})
    # +2% should trigger with the per-coin 2% target (global 10% would not)
    d = _fixed_pct_decision(_pos(100.0, "BTC/USD"), 102.0, s)
    assert d.action == ACT_EXIT_FULL and d.module == "FIXED_TP"


def test_per_strategy_override_wins_over_global():
    # Global native, but the position's strategy has a deployed Fixed% override.
    s = RiskSettings(exit_method_pref="native",
                     profile_overrides={"hunter": {"method": "fixed_pct", "target_pct": 4.5, "stop_pct": 2.7}})
    assert _resolve_exit_method(s, "BTC/USD", "hunter") == "fixed_pct"
    assert _resolve_exit_method(s, "BTC/USD", "squeeze") == "native"  # other strategies unaffected
    d = _fixed_pct_decision(_pos(100.0, "BTC/USD"), 104.5, s)  # hunter position +4.5%
    assert d.action == ACT_EXIT_FULL and d.module == "FIXED_TP"


def test_coin_override_beats_strategy_override():
    s = RiskSettings(exit_method_pref="native",
                     asset_exit_overrides={"BTC/USD": {"method": "fixed_pct", "target_pct": 1.5, "stop_pct": 1.0}},
                     profile_overrides={"hunter": {"method": "fixed_pct", "target_pct": 9.0, "stop_pct": 9.0}})
    # coin override (1.5%) wins over strategy override (9%)
    d = _fixed_pct_decision(_pos(100.0, "BTC/USD"), 101.5, s)
    assert d.action == ACT_EXIT_FULL and d.module == "FIXED_TP"


def test_pdf_labels_reflect_deployed_fixed_config():
    fixed_run = {
        "exit_method": "fixed", "target_profit": 40.0, "target_loss": 25.0, "exit_source": "live",
        "setting_overrides": {"exit_method_pref": "fixed_pct"},
        "result": {"exit_method_label": "Live Exit Engine \u00b7 Fixed % Target (TP $40 / SL $25)"},
    }
    assert "Fixed" in _exit_label(fixed_run) and "$40" in _exit_label(fixed_run)
    assert _live_exit_desc(fixed_run) == "Deployed config \u00b7 Fixed % Target + Stop"


def test_pdf_labels_native_unchanged():
    native_run = {
        "exit_method": "engine", "exit_source": "live",
        "setting_overrides": {"exit_method_pref": "native"},
        "result": {"exit_method_label": "Live Exit Engine (deployed config)"},
    }
    # existing regression string must remain for the native path
    assert _exit_label(native_run) == "Live Exit Engine (deployed config)"
    assert _live_exit_desc(native_run) == "Deployed config \u00b7 Universal Exit Engine"
