"""Tests for the SWING PIVOT strategy:

  * swing entry gate in fuse_signals (macro bullish + 4h EMA trend stack)
  * decoupled STRONG classifier (trend OR volatility)
  * position_watcher.evaluate_exit branches (SL / TRAIL / no-exit)
  * position_watcher.watch_once persists peak_price and writes a TradeLog
    with exit_reason on PAPER path

NOTE: the legacy MICRO_FLIP exit and the orderbook-imbalance entry gate were
removed in the swing pivot, so those tests no longer exist.
"""
from __future__ import annotations

import pytest

from models import KillSwitchStatus, MarketSnapshot, Portfolio, Position, RiskSettings
from position_watcher import EXIT_SL, EXIT_TRAIL, evaluate_exit, watch_once
from risk_engine import fuse_signals
from setup_classifier import classify_setup


# ---- helpers ----
def _snap(symbol="BTC/USD", price=100.0, imb=0.20) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol, price=price, bid=price - 0.05, ask=price + 0.05,
        spread_pct=0.1, orderbook_imbalance=imb, exchange="kraken",
    )


def _safe_kill() -> KillSwitchStatus:
    return KillSwitchStatus(
        spread_breach=False, daily_loss_breach=False,
        confidence_breach=False, manual_kill=False, overall_safe=True,
        details={"spread_pct": 0.1, "daily_change_pct": 0.0, "macro_confidence": 0.9},
    )


# ---------- 1) swing entry gate (4h EMA trend stack) ----------
def test_swing_buys_when_bullish_and_4h_trend_aligned():
    settings = RiskSettings(htf_trend_enabled=True)
    decision, _, summary = fuse_signals(
        _snap(), "BULLISH", 0.85, settings, _safe_kill(),
        has_position=False, htf_trend_aligned=True,
    )
    assert decision == "BUY"
    assert "4h trend aligned" in summary


def test_swing_holds_when_4h_trend_not_aligned():
    settings = RiskSettings(htf_trend_enabled=True)
    decision, _, summary = fuse_signals(
        _snap(), "BULLISH", 0.85, settings, _safe_kill(),
        has_position=False, htf_trend_aligned=False,
    )
    assert decision == "HOLD"
    assert "4h trend not aligned" in summary


def test_swing_buys_when_htf_filter_disabled():
    settings = RiskSettings(htf_trend_enabled=False)
    decision, _, _ = fuse_signals(
        _snap(), "BULLISH", 0.85, settings, _safe_kill(),
        has_position=False, htf_trend_aligned=None,
    )
    assert decision == "BUY"


def test_open_position_exits_only_on_existential_veto():
    settings = RiskSettings()
    # Bearish macro on an open position NO LONGER force-sells — exits are owned by
    # the structural stop + trailing engine. Only an existential breaker VETO sells.
    hold, _, _ = fuse_signals(
        _snap(), "BEARISH", 0.85, settings, _safe_kill(),
        has_position=True, htf_trend_aligned=None, breaker_state="CAUTION",
    )
    assert hold == "HOLD"
    decision, _, summary = fuse_signals(
        _snap(), "NEUTRAL", 0.10, settings, _safe_kill(),
        has_position=True, htf_trend_aligned=None, breaker_state="VETO",
    )
    assert decision == "SELL"
    assert "SELL" in summary


# ---------- 2) decoupled STRONG classifier ----------
def _bars(n=300, base=100.0, step=0.5):
    return [[i * 3600 * 1000, base + i*step - step/2, base + i*step + 0.6,
             base + i*step - 0.6, base + i*step, 1.0] for i in range(n)]


def test_classifier_strong_requires_trend_and_volatility():
    # Steady strong uptrend (high ADX) + low vol thresholds -> all three legs pass -> STRONG.
    bars = _bars(300, step=0.5)
    strength, ev = classify_setup(bars, macro_confidence=0.85, macro_bias="BULLISH",
                                  min_adx=10.0, min_atr_percentile=10.0)
    assert strength == "STRONG"
    assert ev["trend_aligned_long"] is True
    assert ev["volatility_ok"] is True


def test_classifier_downgrades_to_normal_without_volatility():
    # Trend aligned but volatility gate impossible -> strict AND fails -> NORMAL.
    bars = _bars(300, step=0.5)
    strength, ev = classify_setup(bars, macro_confidence=0.85, macro_bias="BULLISH",
                                  min_adx=101.0, min_atr_percentile=101.0)
    assert strength == "NORMAL"
    assert ev["trend_aligned_long"] is True
    assert ev["volatility_ok"] is False
    assert "volatility floor not met" in ev["downgrade_reason"]


def test_classifier_downgrades_to_normal_below_confidence():
    bars = _bars(300, step=0.5)
    strength, ev = classify_setup(bars, macro_confidence=0.79, macro_bias="BULLISH",
                                  min_strong_confidence=0.80, min_adx=10.0, min_atr_percentile=10.0)
    assert strength == "NORMAL"
    assert "conf" in ev["downgrade_reason"]


def test_classifier_normal_when_confidence_low():
    bars = _bars(300)
    strength, ev = classify_setup(bars, macro_confidence=0.50, macro_bias="BULLISH")
    assert strength == "NORMAL"
    assert "conf" in ev["downgrade_reason"]


# ---------- 3) evaluate_exit branches (SL / TRAIL only) ----------
def test_evaluate_exit_sl_hit():
    pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0, peak_price=101.0)
    snap = _snap(price=98.0)  # -2% from entry
    settings = RiskSettings(stop_loss_pct=1.5)
    reason, details = evaluate_exit(pos, snap, settings)
    assert reason == EXIT_SL
    assert details["pnl_pct"] == pytest.approx(-2.0, abs=0.001)


def test_evaluate_exit_trail_hit_after_arm():
    # Trade ran from 100 -> 110 (+10%), now pulled back to 108.9 (-1.0% from peak)
    pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0, peak_price=110.0)
    snap = _snap(price=108.89)
    settings = RiskSettings(stop_loss_pct=1.5, trail_arm_pct=3.0, trail_distance_pct=1.0)
    reason, details = evaluate_exit(pos, snap, settings)
    assert reason == EXIT_TRAIL
    assert details["pullback_pct"] >= 1.0


def test_evaluate_exit_trail_not_armed_yet():
    # Trade only up +2% -> trailing not yet armed
    pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0, peak_price=102.0)
    snap = _snap(price=101.5)  # pullback exists but trail not armed
    settings = RiskSettings(stop_loss_pct=1.5, trail_arm_pct=3.0, trail_distance_pct=1.0)
    reason, _ = evaluate_exit(pos, snap, settings)
    assert reason is None


def test_evaluate_exit_returns_none_when_calm():
    pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0, peak_price=100.5)
    snap = _snap(price=100.6, imb=0.05)
    settings = RiskSettings(stop_loss_pct=1.5, trail_arm_pct=3.0, trail_distance_pct=1.0)
    reason, _ = evaluate_exit(pos, snap, settings)
    assert reason is None


# ---------- 3b) volatility-adaptive trailing envelope ----------
from position_watcher import trail_distance_for  # noqa: E402


def _pos_with_atr(atr_pct, breakout=False):
    return Position(
        symbol="BTC/USD", quantity=0.1, avg_cost=100.0, peak_price=100.0,
        atr_percentile_at_entry=atr_pct, breakout_mode=breakout,
    )


def test_dynamic_trail_clamps_to_floor_on_calm_tape():
    # ATR percentile 10 -> k*pct = 0.06*10 = 0.6 -> clamped up to the 2% floor
    s = RiskSettings(dynamic_trail_enabled=True, dynamic_trail_k=0.06,
                     dynamic_trail_min_pct=2.0, dynamic_trail_max_pct=6.0)
    assert trail_distance_for(_pos_with_atr(10.0), s) == pytest.approx(2.0)


def test_dynamic_trail_clamps_to_ceiling_on_violent_tape():
    # ATR percentile 100 -> 0.06*100 = 6.0 (exactly the ceiling); 120 would clamp down to 6
    s = RiskSettings(dynamic_trail_enabled=True, dynamic_trail_k=0.06,
                     dynamic_trail_min_pct=2.0, dynamic_trail_max_pct=6.0)
    assert trail_distance_for(_pos_with_atr(100.0), s) == pytest.approx(6.0)


def test_dynamic_trail_scales_linearly_in_band():
    # ATR percentile 50 -> 0.06*50 = 3.0 (inside the 2%-6% band, unclamped)
    s = RiskSettings(dynamic_trail_enabled=True, dynamic_trail_k=0.06,
                     dynamic_trail_min_pct=2.0, dynamic_trail_max_pct=6.0)
    assert trail_distance_for(_pos_with_atr(50.0), s) == pytest.approx(3.0)


def test_dynamic_trail_falls_back_to_static_when_disabled():
    s = RiskSettings(dynamic_trail_enabled=False, trail_distance_pct=3.0)
    assert trail_distance_for(_pos_with_atr(90.0), s) == pytest.approx(3.0)


def test_dynamic_trail_falls_back_to_static_when_atr_unknown():
    s = RiskSettings(dynamic_trail_enabled=True, trail_distance_pct=3.0)
    assert trail_distance_for(_pos_with_atr(None), s) == pytest.approx(3.0)


def test_dynamic_trail_uses_breakout_static_fallback():
    # No ATR percentile -> breakout position falls back to its own static distance
    s = RiskSettings(dynamic_trail_enabled=True, breakout_trail_distance_pct=4.5)
    assert trail_distance_for(_pos_with_atr(None, breakout=True), s) == pytest.approx(4.5)


def test_evaluate_exit_high_vol_widens_trail_and_holds():
    # High-vol entry (ATR pct 100 -> 6% trail). Ran 100->110, pulled back to 105.0
    # (-4.5% from peak) which is INSIDE the 6% leash -> should NOT exit.
    s = RiskSettings(stop_loss_pct=10.0, trail_arm_pct=5.0,
                     dynamic_trail_enabled=True, dynamic_trail_k=0.06,
                     dynamic_trail_min_pct=2.0, dynamic_trail_max_pct=6.0)
    pos = _pos_with_atr(100.0)
    pos.peak_price = 110.0
    snap = _snap(price=105.0)  # -4.55% from peak < 6% ceiling
    reason, details = evaluate_exit(pos, snap, s)
    assert reason is None
    assert details["trail_distance_pct"] == pytest.approx(6.0)


def test_evaluate_exit_low_vol_tightens_trail_and_exits():
    # Low-vol entry (ATR pct 10 -> clamps to 2% floor). Same +10% run, pulled
    # back to 107.0 (-2.7% from peak) which EXCEEDS the 2% floor -> TRAIL_HIT.
    s = RiskSettings(stop_loss_pct=10.0, trail_arm_pct=5.0,
                     dynamic_trail_enabled=True, dynamic_trail_k=0.06,
                     dynamic_trail_min_pct=2.0, dynamic_trail_max_pct=6.0)
    pos = _pos_with_atr(10.0)
    pos.peak_price = 110.0
    snap = _snap(price=107.0)  # -2.7% from peak > 2% floor
    reason, details = evaluate_exit(pos, snap, s)
    assert reason == EXIT_TRAIL
    assert details["trail_distance_pct"] == pytest.approx(2.0)


# ---------- 4) watch_once end-to-end on PAPER ----------
class _Coll:
    def __init__(self, doc=None):
        self._doc = doc
        self.inserted: list[dict] = []
        self.replaced: list[tuple] = []

    async def find_one(self, *a, **kw):
        return self._doc

    async def insert_one(self, doc):
        self.inserted.append(doc)
        class _R:
            inserted_id = "x"
        return _R()

    async def replace_one(self, query, doc, upsert=False):
        self.replaced.append((query, doc))
        self._doc = doc
        class _R:
            pass
        return _R()

    def find(self, *a, **kw):
        docs = list(self.inserted)
        if self._doc:
            docs.append(self._doc)
        class _Cur:
            def __init__(self, d):
                self._d = d
            def sort(self, *a, **k):
                return self
            async def to_list(self, n):
                return self._d[:n]
        return _Cur(docs)

    async def count_documents(self, *a, **kw):
        return len(self.inserted)


class _DB:
    def __init__(self, settings_doc=None, portfolio_doc=None):
        self.settings = _Coll(settings_doc)
        self.portfolio = _Coll(portfolio_doc)
        self.trades = _Coll()
        self.reasoning = _Coll()
        self.cooldowns = _Coll()
        self.pending_orders = _Coll()


@pytest.mark.asyncio
async def test_watch_once_paper_sl_exit(monkeypatch):
    settings = RiskSettings(stop_loss_pct=1.5, trading_mode="PAPER",
                            enabled_symbols=["BTC/USD"])
    pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0, peak_price=100.5)
    portfolio = Portfolio(cash=50.0, positions=[pos], day_start_equity=60.0, starting_balance=100.0)
    db = _DB(settings_doc=settings.model_dump(), portfolio_doc=portfolio.model_dump())

    async def fake_snap(sym):
        return _snap(symbol=sym, price=98.0, imb=0.0)  # -2% drawdown
    monkeypatch.setattr("position_watcher.fetch_snapshot", fake_snap)

    exits = await watch_once(db)
    assert len(exits) == 1
    assert exits[0]["side"] == "SELL"
    # Phase F Universal Exit Engine emits granular codes; -2% vs 1.5% stop -> Module A STOP_LOSS
    assert exits[0]["exit_reason"] == "STOP_LOSS"
    assert exits[0]["exit_module"] == "A"
    # reasoning row written with exit_reason
    assert db.reasoning.inserted[-1]["evidence"]["exit_reason"] == "STOP_LOSS"
    # portfolio saved -> position closed
    final_portfolio = db.portfolio._doc
    assert all(p["symbol"] != "BTC/USD" for p in final_portfolio["positions"])


@pytest.mark.asyncio
async def test_watch_once_updates_peak_when_no_exit(monkeypatch):
    settings = RiskSettings(stop_loss_pct=10.0, trail_arm_pct=20.0, trading_mode="PAPER",
                            enabled_symbols=["BTC/USD"])
    pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0, peak_price=100.0)
    portfolio = Portfolio(cash=90.0, positions=[pos], day_start_equity=100.0, starting_balance=100.0)
    db = _DB(settings_doc=settings.model_dump(), portfolio_doc=portfolio.model_dump())

    async def fake_snap(sym):
        return _snap(symbol=sym, price=102.0, imb=0.10)  # +2%, well under SL/TRAIL
    monkeypatch.setattr("position_watcher.fetch_snapshot", fake_snap)

    exits = await watch_once(db)
    assert exits == []
    # portfolio saved with bumped peak_price
    final = db.portfolio._doc
    saved_pos = next(p for p in final["positions"] if p["symbol"] == "BTC/USD")
    assert saved_pos["peak_price"] == pytest.approx(102.0)
