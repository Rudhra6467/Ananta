"""
Launch regression suite — highest-risk trading critical paths.

Covers the pure decision functions that gate real capital:
  * Exit engine triggers          (position_watcher.evaluate_exit + declarative exit)
  * Entry gating / fusion + kills  (risk_engine.fuse_signals / compute_kill_switches)
  * Position sizing determinism    (risk_engine.position_size_quantity)

All tests are DB-free, deterministic and fast. Run:  pytest tests/ -q  (from /app/backend)
"""
from __future__ import annotations

from models import MarketSnapshot, Portfolio, Position, RiskSettings
from position_watcher import EXIT_SL, EXIT_TRAIL, evaluate_exit
from risk_engine import compute_kill_switches, fuse_signals, position_size_quantity
from declarative_engine import evaluate as decl_evaluate


def _snap(price=100.0, bid=None, ask=None, spread_pct=0.05):
    bid = bid if bid is not None else price * 0.999
    ask = ask if ask is not None else price * 1.001
    return MarketSnapshot(
        symbol="ETH/USD", price=price, bid=bid, ask=ask,
        spread_pct=spread_pct, orderbook_imbalance=0.0,
    )


# --------------------------- Exit Engine triggers --------------------------- #
def test_structural_stop_triggers_sl():
    """Price trading through the structural stop exits as SL_HIT even when the
    % drawdown alone is well inside the hard stop."""
    pos = Position(symbol="ETH/USD", quantity=1.0, avg_cost=100.0,
                   peak_price=100.0, structural_stop=99.5)
    reason, details = evaluate_exit(pos, _snap(price=99.4), RiskSettings())
    assert reason == EXIT_SL
    assert details["structural_stop"] == 99.5


def test_hard_stop_loss_triggers_sl():
    """Drawdown beyond stop_loss_pct (default 2.2%) exits as SL_HIT."""
    pos = Position(symbol="ETH/USD", quantity=1.0, avg_cost=100.0, peak_price=100.0)
    reason, details = evaluate_exit(pos, _snap(price=97.0), RiskSettings())
    assert reason == EXIT_SL
    assert details["pnl_pct"] <= -RiskSettings().stop_loss_pct


def test_trailing_take_profit_triggers_trail():
    """Armed trail (run-up >= trail_arm_pct) that pulls back past the trail
    distance exits as TRAIL_HIT, locking the winner."""
    pos = Position(symbol="ETH/USD", quantity=1.0, avg_cost=100.0, peak_price=105.0)
    reason, details = evaluate_exit(pos, _snap(price=103.0), RiskSettings())
    assert reason == EXIT_TRAIL
    assert details["run_up_pct"] >= RiskSettings().trail_arm_pct
    assert details["pullback_pct"] >= details["trail_distance_pct"]


def test_no_trigger_holds():
    """A small green move that has not armed the trail nor breached the stop
    returns no exit (position held)."""
    pos = Position(symbol="ETH/USD", quantity=1.0, avg_cost=100.0, peak_price=100.5)
    reason, _ = evaluate_exit(pos, _snap(price=100.5), RiskSettings())
    assert reason is None


def test_strategy_declarative_exit_fires():
    """The declarative per-strategy exit rule (source of the STRAT_EXIT exit in
    position_watcher) fires when its condition is met and stays quiet otherwise."""
    spec = {"indicators": {}, "entry": [], "exit": [{"lhs": "close", "op": "lt", "rhs": 50}]}
    bars_exit = [[i, 60, 61, 59, 40, 100] for i in range(30)]   # last close 40 < 50 -> exit
    bars_hold = [[i, 60, 61, 59, 60, 100] for i in range(30)]   # last close 60 -> no exit
    assert decl_evaluate(spec, bars_exit, {}).exit is True
    assert decl_evaluate(spec, bars_hold, {}).exit is False


# --------------------------- Entry gating / fusion -------------------------- #
def test_entry_gating_buy_hold_blocked():
    """fuse_signals: Hunter-triggered -> BUY; not triggered -> HOLD; hard
    kill-switch -> BLOCKED (macro can never override these)."""
    s = RiskSettings()
    p = Portfolio()
    ok_snap = _snap(spread_pct=0.05)
    ok_kill = compute_kill_switches(ok_snap, p, s, macro_confidence=0.9)

    buy, _b, _ = fuse_signals(ok_snap, "NEUTRAL", 0.9, s, ok_kill,
                              has_position=False, primary_triggered=True)
    hold, _b2, _ = fuse_signals(ok_snap, "BULLISH", 0.9, s, ok_kill,
                                has_position=False, primary_triggered=False)
    assert buy == "BUY"
    assert hold == "HOLD"

    wide_snap = _snap(spread_pct=1.0)  # > max_spread_pct 0.5
    bad_kill = compute_kill_switches(wide_snap, p, s, macro_confidence=0.9)
    blocked, reasons, _ = fuse_signals(wide_snap, "BULLISH", 0.9, s, bad_kill,
                                       has_position=False, primary_triggered=True)
    assert blocked == "BLOCKED"
    assert any("SPREAD_BREACH" in r for r in reasons)


def test_kill_switch_breaches():
    """compute_kill_switches flags spread, confidence and daily-loss breaches."""
    s = RiskSettings()
    p = Portfolio()

    spread = compute_kill_switches(_snap(spread_pct=1.0), p, s, macro_confidence=0.9)
    assert spread.spread_breach is True and spread.overall_safe is False

    conf = compute_kill_switches(_snap(spread_pct=0.05), p, s, macro_confidence=0.5)
    assert conf.confidence_breach is True  # < min_confidence 0.80

    drawn = Portfolio(cash=1000.0, day_start_equity=1200.0)  # -16.6% day
    loss = compute_kill_switches(_snap(spread_pct=0.05), drawn, s, macro_confidence=0.9)
    assert loss.daily_loss_breach is True and loss.overall_safe is False


# --------------------------- Position sizing -------------------------------- #
def test_position_sizing_determinism_and_caps():
    """Fixed USD lot is sized exactly, deterministically, and never exceeds 95%
    of available cash; non-BUY decisions size to zero."""
    s = RiskSettings()
    p = Portfolio(cash=1200.0)
    snap = _snap(price=100.0)  # ask ~100.1

    q1 = position_size_quantity("BUY", snap, p, s, 0.9, usd_lot=10.0)
    q2 = position_size_quantity("BUY", snap, p, s, 0.9, usd_lot=10.0)
    assert q1 == q2 > 0
    assert q1 * snap.ask <= 10.0 + 1e-6  # sized to the lot, not more

    capped = position_size_quantity("BUY", snap, p, s, 0.9, usd_lot=10000.0)
    assert capped * snap.ask <= p.cash * 0.95 + 1e-6  # hard cash cap

    assert position_size_quantity("SELL", snap, p, s, 0.9, usd_lot=10.0) == 0.0
