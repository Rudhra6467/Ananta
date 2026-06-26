"""Tests for the taker-fee accounting in PAPER buy/sell paths and the
$15 / $20 default lot sizes."""
from __future__ import annotations

import pytest

from models import Portfolio, RiskSettings
from trading_engine import _execute_buy, _execute_sell


def _new_portfolio(cash: float = 100.0) -> Portfolio:
    return Portfolio(cash=cash, day_start_equity=cash, starting_balance=cash)


def test_default_lot_sizes_are_20_and_30():
    s = RiskSettings()
    assert s.normal_lot_usd == 20.0
    assert s.strong_lot_usd == 30.0


def test_default_taker_fee_is_0_40_pct():
    assert RiskSettings().taker_fee_pct == 0.40


def test_buy_debits_notional_plus_fee_from_cash():
    p = _new_portfolio(100.0)
    # $15 notional at $100/coin -> 0.15 qty; fee 0.4% = $0.06
    notional, fee = _execute_buy(p, "BTC/USD", qty=0.15, price=100.0, fee_pct=0.40)
    assert notional == pytest.approx(15.0)
    assert fee == pytest.approx(0.06, abs=1e-6)
    assert p.cash == pytest.approx(100.0 - 15.0 - 0.06)
    pos = p.positions[0]
    assert pos.fee_paid_buy == pytest.approx(0.06)


def test_buy_rejected_when_notional_plus_fee_exceeds_cash():
    p = _new_portfolio(5.0)
    notional, fee = _execute_buy(p, "BTC/USD", qty=0.05, price=100.0, fee_pct=0.40)  # needs $5.02
    assert notional == 0.0 and fee == 0.0
    assert p.cash == pytest.approx(5.0)
    assert p.positions == []


def test_sell_credits_notional_minus_fee():
    p = _new_portfolio(100.0)
    _execute_buy(p, "BTC/USD", 0.15, 100.0, fee_pct=0.40)  # cost 15.06
    qty, notional, realized, fee = _execute_sell(p, "BTC/USD", price=100.0, fee_pct=0.40)
    assert qty == pytest.approx(0.15)
    assert notional == pytest.approx(15.0)
    assert fee == pytest.approx(0.06, abs=1e-6)
    # gross = 0, fees both legs = 0.12 -> realized_net = -0.12
    assert realized == pytest.approx(-0.12, abs=1e-6)
    # cash = 100 - 15.06 + (15 - 0.06) = 99.88
    assert p.cash == pytest.approx(99.88, abs=1e-6)
    assert p.positions == []


def test_round_trip_flat_market_loses_exactly_0_80_pct():
    p = _new_portfolio(100.0)
    _execute_buy(p, "BTC/USD", 0.15, 100.0, fee_pct=0.40)
    _, _, realized, _ = _execute_sell(p, "BTC/USD", 100.0, fee_pct=0.40)
    # 0.8% of 15 = 0.12
    assert realized == pytest.approx(-0.12, abs=1e-6)
    # realized_pnl tracker reflects net
    assert p.realized_pnl == pytest.approx(-0.12, abs=1e-6)


def test_round_trip_with_2_pct_gross_winner_nets_about_1_2_pct():
    p = _new_portfolio(100.0)
    _execute_buy(p, "BTC/USD", 0.15, 100.0, fee_pct=0.40)  # 0.15 BTC @ 100
    # price rises 2% -> 102
    _, _, realized, _ = _execute_sell(p, "BTC/USD", 102.0, fee_pct=0.40)
    # gross = (102-100)*0.15 = 0.30
    # buy fee 0.06 + sell fee = 102*0.15*0.004 = 0.0612
    # net = 0.30 - 0.06 - 0.0612 = 0.1788
    assert realized == pytest.approx(0.1788, abs=1e-4)


def test_zero_fee_path_matches_legacy_behaviour():
    p = _new_portfolio(100.0)
    notional, fee = _execute_buy(p, "BTC/USD", 0.10, 100.0, fee_pct=0.0)
    assert fee == 0.0
    assert p.cash == pytest.approx(90.0)
    _, _, realized, fee2 = _execute_sell(p, "BTC/USD", 110.0, fee_pct=0.0)
    assert fee2 == 0.0
    assert realized == pytest.approx(1.0, abs=1e-6)  # (110-100)*0.1
