"""Tests for the diversified 6-asset matrix: asset profiles + PAXG exit overrides."""
from __future__ import annotations

from asset_profiles import asset_class, eff_setting, exit_overrides, scan_interval
from models import Position, RiskSettings
from position_watcher import evaluate_exit


def test_asset_class_mapping():
    assert asset_class("BTC/USD") == "L1"
    assert asset_class("ETH/USD") == "L1"
    assert asset_class("LINK/USD") == "DEFI"
    assert asset_class("AAVE/USD") == "DEFI"
    assert asset_class("PAXG/USD") == "METAL"
    assert asset_class("UNKNOWN/USD") == "L1"  # safe default


def test_scan_interval_staggering():
    assert scan_interval("BTC/USD") == 1     # majors every cycle
    assert scan_interval("LINK/USD") == 3    # DeFi slower
    assert scan_interval("PAXG/USD") == 3    # gold slower


def test_exit_overrides_only_metal():
    assert exit_overrides("PAXG/USD")["stop_loss_pct"] == 2.5
    assert exit_overrides("BTC/USD") == {}   # crypto uses global settings


def test_eff_setting_prefers_override():
    s = RiskSettings()
    # global SL is 10%, PAXG override is 2.5%
    assert eff_setting(s, "BTC/USD", "stop_loss_pct") == s.stop_loss_pct
    assert eff_setting(s, "PAXG/USD", "stop_loss_pct") == 2.5
    assert eff_setting(s, "PAXG/USD", "trail_arm_pct") == 1.0


class _Snap:
    def __init__(self, price):
        self.price = price


def test_paxg_tight_stop_triggers_where_crypto_would_not():
    """A 3% drawdown must STOP PAXG (2.5% SL) but NOT crypto (10% SL)."""
    s = RiskSettings()
    paxg = Position(symbol="PAXG/USD", quantity=1.0, avg_cost=100.0, peak_price=100.0)
    btc = Position(symbol="BTC/USD", quantity=1.0, avg_cost=100.0, peak_price=100.0)
    snap = _Snap(97.0)  # -3%
    reason_paxg, _ = evaluate_exit(paxg, snap, s)
    reason_btc, _ = evaluate_exit(btc, snap, s)
    assert reason_paxg == "SL_HIT"   # 3% > 2.5% gold stop
    assert reason_btc is None        # 3% < 10% crypto stop


def test_paxg_tight_trail_arms_on_small_move():
    """PAXG arms its trail at +1% and exits on a 0.7% pullback; crypto would not."""
    s = RiskSettings()
    # ran to +1.5% (peak 101.5), now pulled back to 100.6 => 0.89% pullback from peak
    paxg = Position(symbol="PAXG/USD", quantity=1.0, avg_cost=100.0, peak_price=101.5)
    snap = _Snap(100.6)
    reason, details = evaluate_exit(paxg, snap, s)
    assert reason == "TRAIL_HIT"
    assert details["stop_loss_pct"] == 2.5
