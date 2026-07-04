"""Tests for the adaptive lot sizing pipeline:

  setup_classifier   ->   trading_engine.evaluate_symbol   ->   risk_engine.position_size_quantity

Covers:
  * pure indicator math (EMA, ATR, ADX, percentile)
  * classify_setup branching (STRONG / NORMAL / NONE)
  * position_size_quantity USD-lot vs legacy %
  * trading_engine concurrent-cap (queue & skip behaviour)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models import (
    AIReasoning,  # noqa: F401  (imported by trading_engine; ensures path is wired)
    MarketSnapshot,
    Portfolio,
    Position,
    RiskSettings,
)
from risk_engine import position_size_quantity
from primary_layer import PrimarySignal
from setup_classifier import (
    adx,
    atr,
    classify_setup,
    ema,
    percentile_rank,
    true_range,
)

# A triggered primary signal for the layered-architecture tests (Phase 2): entries
# are now driven by the PRIMARY technical layer, not macro bias.
_PRIMARY_HIT = PrimarySignal(
    triggered=True, reason_codes=[],
    support_zone={"low": 99.0, "high": 101.0, "mid": 100.0, "touches": 8},
    structural_stop=97.02, evidence={},
)


# ------------------------------------------------------------------
# 1) Indicator math
# ------------------------------------------------------------------
def test_ema_smoothing_converges_to_constant_input():
    out = ema([10.0] * 50, period=10)
    assert len(out) == 50
    assert pytest.approx(out[-1], abs=1e-9) == 10.0


def test_true_range_handles_gap_up():
    # bar 1: gap up of 5; TR should be max(h-l, |h-prev_close|, |l-prev_close|)
    tr = true_range(highs=[100, 110], lows=[95, 108], closes=[100, 109])
    assert tr[0] == pytest.approx(5.0)
    # h-l=2, |110-100|=10, |108-100|=8 -> 10
    assert tr[1] == pytest.approx(10.0)


def test_atr_returns_same_length_and_positive():
    highs = [10 + i * 0.5 for i in range(30)]
    lows = [9 + i * 0.5 for i in range(30)]
    closes = [9.5 + i * 0.5 for i in range(30)]
    out = atr(highs, lows, closes, period=14)
    assert len(out) == 30
    assert all(v >= 0 for v in out)


def test_adx_trending_market_high_value():
    # Strong steady uptrend -> ADX should rise well above 20
    closes = [100 + i for i in range(60)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    out = adx(highs, lows, closes, period=14)
    assert out[-1] > 20.0


def test_percentile_rank_basic():
    assert percentile_rank([1, 2, 3, 4, 5], 3) == pytest.approx(60.0)
    assert percentile_rank([], 1.0) == 0.0


# ------------------------------------------------------------------
# 2) classify_setup branching
# ------------------------------------------------------------------
def _make_bars(n: int, base: float = 100.0, step: float = 0.5) -> list[list[float]]:
    """Build a steady uptrend OHLCV series: [ts, open, high, low, close, volume]."""
    bars: list[list[float]] = []
    for i in range(n):
        close = base + i * step
        bars.append([float(i * 3600 * 1000), close - step / 2, close + 0.6, close - 0.6, close, 1.0])
    return bars


def test_classify_returns_none_when_macro_not_bullish():
    bars = _make_bars(300)
    strength, evidence = classify_setup(bars, 0.9, "NEUTRAL")
    assert strength == "NONE"
    assert "macro bias" in evidence["reason"]


def test_classify_returns_normal_when_insufficient_history():
    bars = _make_bars(50)  # < 200
    strength, evidence = classify_setup(bars, 0.9, "BULLISH")
    assert strength == "NORMAL"
    assert "insufficient" in evidence["reason"]


def test_classify_returns_strong_on_uptrend_high_confidence():
    bars = _make_bars(300)  # clean uptrend, ADX should be high
    strength, evidence = classify_setup(
        bars, macro_confidence=0.9, macro_bias="BULLISH",
        min_strong_confidence=0.75, min_atr_percentile=60.0, min_adx=20.0,
    )
    assert strength == "STRONG"
    assert evidence["trend_aligned_long"] is True
    assert evidence["volatility_ok"] is True
    assert evidence["confidence_above_threshold"] is True


def test_classify_downgrades_to_normal_when_confidence_low():
    bars = _make_bars(300)
    strength, evidence = classify_setup(bars, macro_confidence=0.60, macro_bias="BULLISH")
    assert strength == "NORMAL"
    assert "downgrade_reason" in evidence
    assert "conf" in evidence["downgrade_reason"]


# ------------------------------------------------------------------
# 3) position_size_quantity USD-lot path
# ------------------------------------------------------------------
def _snap(ask: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTC/USD", price=ask, bid=ask - 0.5, ask=ask,
        spread_pct=0.1, orderbook_imbalance=0.2, exchange="kraken",
    )


def _portfolio(cash: float = 100.0) -> Portfolio:
    return Portfolio(cash=cash, day_start_equity=cash, starting_balance=cash)


def test_position_size_usd_lot_strong():
    s = RiskSettings(adaptive_sizing_enabled=True, strong_lot_usd=10.0)
    qty = position_size_quantity("BUY", _snap(ask=100.0), _portfolio(100.0), s, 0.9, usd_lot=10.0)
    assert qty == pytest.approx(0.10, abs=1e-6)


def test_position_size_usd_lot_normal():
    s = RiskSettings(adaptive_sizing_enabled=True, normal_lot_usd=5.0)
    qty = position_size_quantity("BUY", _snap(ask=50.0), _portfolio(100.0), s, 0.6, usd_lot=5.0)
    assert qty == pytest.approx(0.10, abs=1e-6)


def test_position_size_usd_lot_capped_by_cash():
    # cash=$5 -> max useable = $4.75; usd_lot=$10 should be clamped
    s = RiskSettings(adaptive_sizing_enabled=True)
    qty = position_size_quantity("BUY", _snap(ask=10.0), _portfolio(5.0), s, 0.9, usd_lot=10.0)
    assert qty == pytest.approx(0.475, abs=1e-6)


def test_position_size_legacy_path_unchanged():
    # No usd_lot -> falls back to % of equity * confidence
    s = RiskSettings(
        adaptive_sizing_enabled=False,
        position_size_pct_min=1.0, position_size_pct_max=3.0,
    )
    qty = position_size_quantity("BUY", _snap(ask=100.0), _portfolio(100.0), s, 0.5)
    # pct = 1 + (3-1)*0.5 = 2 -> notional $2 -> qty 0.02
    assert qty == pytest.approx(0.02, abs=1e-6)


def test_position_size_returns_zero_when_not_buy():
    s = RiskSettings()
    assert position_size_quantity("SELL", _snap(), _portfolio(), s, 0.9, usd_lot=10.0) == 0.0
    assert position_size_quantity("HOLD", _snap(), _portfolio(), s, 0.9, usd_lot=10.0) == 0.0


# ------------------------------------------------------------------
# 4) trading_engine concurrent-cap behaviour
# ------------------------------------------------------------------
class _StubInsertResult:
    """asyncio-friendly stub for motor's insert_one return."""
    inserted_id = "stub"


class _StubCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def insert_one(self, doc):
        self.docs.append(doc)
        return _StubInsertResult()

    async def find_one(self, *args, **kwargs):
        return None

    async def replace_one(self, *args, **kwargs):
        return _StubInsertResult()

    async def count_documents(self, *args, **kwargs):
        return len(self.docs)

    def find(self, *args, **kwargs):
        docs = list(self.docs)
        class _Cur:
            def sort(self, *a, **k):
                return self
            async def to_list(self, n):
                return docs[:n]
        return _Cur()


class _StubDB:
    def __init__(self):
        self.settings = _StubCollection()
        self.portfolio = _StubCollection()
        self.trades = _StubCollection()
        self.reasoning = _StubCollection()
        self.cooldowns = _StubCollection()
        self.pending_orders = _StubCollection()


@pytest.mark.asyncio
async def test_evaluate_symbol_blocks_buy_when_5_slots_full():
    """When 5 positions are already open and a BUY signal fires on a new
    symbol, evaluate_symbol must downgrade to HOLD with MAX_POSITIONS_REACHED
    and skip trade execution (queue for next cycle)."""
    from trading_engine import evaluate_symbol

    five = [
        Position(symbol=f"X{i}/USD", quantity=0.01, avg_cost=10.0) for i in range(5)
    ]
    # cash 99.5 + 5*0.01*10 = 100 -> day_start_equity 100 keeps daily-loss switch unarmed
    portfolio = Portfolio(
        cash=99.5, positions=five, day_start_equity=100.0, starting_balance=100.0,
    )
    settings = RiskSettings(
        adaptive_sizing_enabled=True,
        max_concurrent_positions=5,
        min_confidence=0.0,  # don't kill on confidence
        htf_trend_enabled=False,  # not under test; skip the 4h-trend network fetch
    )

    snap = MarketSnapshot(
        symbol="BTC/USD", price=100.0, bid=99.9, ask=100.1,
        spread_pct=0.2, orderbook_imbalance=0.25, exchange="kraken",
    )
    macro = SimpleNamespace(bias="BULLISH", confidence=0.85, reason="trend strong",
                            model="test", model_dump=lambda: {"bias": "BULLISH", "confidence": 0.85})

    db = _StubDB()
    with (
        patch("trading_engine.load_settings", return_value=settings) as _s,
        patch("trading_engine.load_portfolio", return_value=portfolio),
        patch("trading_engine.fetch_snapshot", return_value=snap),
        patch("trading_engine.get_current_summary", return_value="news"),
        patch("trading_engine.analyze_macro", return_value=macro),
        patch("trading_engine.fetch_ohlcv_1h", return_value=_make_bars(300)),
        patch("trading_engine.get_levels", return_value=[]),
        patch("trading_engine.evaluate_primary", return_value=_PRIMARY_HIT),
        patch("trading_engine.detect_breakout", return_value=(False, {"reason": "not under test"})),
    ):
        _ = _s
        result = await evaluate_symbol(db, "BTC/USD")

    assert result["decision"] == "HOLD"
    assert any("MAX_POSITIONS_REACHED" in r for r in result["blocked_reasons"])
    assert result["trade"] is None
    # reasoning was persisted with the cap reason
    persisted = db.reasoning.docs[-1]
    assert persisted["decision"] == "HOLD"
    assert any("MAX_POSITIONS_REACHED" in r for r in persisted["blocked_reasons"])


@pytest.mark.asyncio
async def test_evaluate_symbol_buys_when_slots_available():
    """When < cap, a BULLISH STRONG setup should place a PAPER Post-Only MAKER
    order resting at the best bid (Phase B: standard entries no longer fill at
    market — they rest as maker orders for the watcher to resolve)."""
    from trading_engine import evaluate_symbol

    portfolio = Portfolio(cash=100.0, day_start_equity=100.0, starting_balance=100.0)
    settings = RiskSettings(
        adaptive_sizing_enabled=True,
        max_concurrent_positions=5,
        min_confidence=0.0,
        normal_lot_usd=5.0,
        strong_lot_usd=10.0,
        htf_trend_enabled=False,  # not under test; skip the 4h-trend network fetch
    )

    snap = MarketSnapshot(
        symbol="BTC/USD", price=100.0, bid=99.9, ask=100.0,
        spread_pct=0.1, orderbook_imbalance=0.25, exchange="kraken",
    )
    macro = SimpleNamespace(bias="BULLISH", confidence=0.9, reason="ok",
                            model="test", model_dump=lambda: {"bias": "BULLISH", "confidence": 0.9})

    db = _StubDB()
    with (
        patch("trading_engine.load_settings", return_value=settings),
        patch("trading_engine.load_portfolio", return_value=portfolio),
        patch("trading_engine.fetch_snapshot", return_value=snap),
        patch("trading_engine.get_current_summary", return_value="news"),
        patch("trading_engine.analyze_macro", return_value=macro),
        patch("trading_engine.fetch_ohlcv_1h", return_value=_make_bars(300)),
        patch("trading_engine.get_levels", return_value=[]),
        patch("trading_engine.evaluate_primary", return_value=_PRIMARY_HIT),
        patch("trading_engine.detect_breakout", return_value=(False, {"reason": "not under test"})),
    ):
        result = await evaluate_symbol(db, "BTC/USD")

    assert result["decision"] == "BUY"
    assert result["trade"] is not None
    # Post-Only maker order resting at best bid (no immediate fill)
    assert result["trade"]["status"] == "PENDING_MAKER"
    assert result["trade"]["price"] == pytest.approx(99.9, abs=1e-6)
    # STRONG setup (strong_lot_usd=10.0) -> 0.10 BTC at $100 ask
    assert result["trade"]["quantity"] == pytest.approx(0.10, abs=1e-6)
    # a resting maker order was persisted, NOT a filled position
    assert len(db.pending_orders.docs) == 1
    assert db.pending_orders.docs[0]["symbol"] == "BTC/USD"
    # reasoning evidence captured the strength
    ev = db.reasoning.docs[-1]["evidence"]
    assert ev["setup_strength"] == "STRONG"
    assert "setup_evidence" in ev
