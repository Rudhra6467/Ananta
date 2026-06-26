"""Phase B — Execution Friction Layer tests.

Covers:
  * PAPER Post-Only maker fill simulation (process_pending_orders):
    PRICE_CROSSED / FLAT_2_TICKS / MISSED_FILL_PRICE_RUN / insufficient cash
  * log_friction_tally fee+slippage summation
  * LiveExecutor order_style routing (DRY_RUN): POST_ONLY rests @ bid, MARKET @ ask
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

import trading_engine as te
from live_execution import get_dry_run_executor
from models import MarketSnapshot, PendingOrder, Portfolio, RiskSettings


# ---------------- in-memory fake Mongo ----------------
class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return self._docs[:n]


class FakeColl:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def _match(self, doc, query):
        for k, v in query.items():
            if isinstance(v, dict) and "$gte" in v:
                if doc.get(k) is None or doc.get(k) < v["$gte"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

        class _R:
            inserted_id = "x"
        return _R()

    async def find_one(self, query=None, proj=None):
        for d in self.docs:
            if self._match(d, query or {}):
                return dict(d)
        return None

    def find(self, query=None, proj=None):
        return _Cursor([dict(d) for d in self.docs if self._match(d, query or {})])

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if self._match(d, query):
                del self.docs[i]
                return

    async def delete_many(self, query):
        self.docs = [d for d in self.docs if not self._match(d, query or {})]

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if self._match(d, query):
                d.update(update.get("$set", {}))
                return
        if upsert:
            nd = dict(query)
            nd.update(update.get("$set", {}))
            self.docs.append(nd)

    async def replace_one(self, query, doc, upsert=False):
        for i, d in enumerate(self.docs):
            if self._match(d, query):
                self.docs[i] = dict(doc)
                return
        if upsert:
            self.docs.append(dict(doc))

    async def count_documents(self, query=None):
        return sum(1 for d in self.docs if self._match(d, query or {}))


class FakeDB:
    def __init__(self, settings=None, portfolio=None, pendings=None, trades=None):
        self.settings = FakeColl([settings.model_dump()] if settings else [])
        self.portfolio = FakeColl([portfolio.model_dump()] if portfolio else [])
        self.pending_orders = FakeColl(pendings or [])
        self.trades = FakeColl(trades or [])
        self.reasoning = FakeColl()
        self.cooldowns = FakeColl()


def _snap(symbol="ETH/USD", price=100.0, bid=100.0, ask=100.3):
    return MarketSnapshot(symbol=symbol, price=price, bid=bid, ask=ask,
                          spread_pct=(ask - bid) / ((ask + bid) / 2) * 100,
                          orderbook_imbalance=0.1, exchange="kraken")


def _pending(symbol="ETH/USD", bid=100.0, qty=0.1, ticks=0):
    return PendingOrder(symbol=symbol, quantity=qty, limit_price=bid, ticks_flat=ticks,
                        sector="Layer 1 High Beta", volatility_regime="NORMAL",
                        atr_at_entry=1.0, atr_percentile_at_entry=55.0).model_dump()


def _async_snap(**kw):
    async def _f(symbol):
        return _snap(**kw)
    return _f


# ---------------- process_pending_orders ----------------
@pytest.mark.asyncio
async def test_maker_fills_when_price_crosses_bid(monkeypatch):
    db = FakeDB(settings=RiskSettings(maker_fee_pct=0.25),
                portfolio=Portfolio(cash=50.0), pendings=[_pending(bid=100.0, qty=0.1)])
    monkeypatch.setattr(te, "fetch_snapshot", _async_snap(price=99.0, bid=99.0, ask=99.3))
    res = await te.process_pending_orders(db)
    assert res and res[0]["outcome"] == "FILLED" and res[0]["reason"] == "PRICE_CROSSED"
    assert db.pending_orders.docs == []           # pending consumed
    buys = [t for t in db.trades.docs if t["side"] == "BUY"]
    assert len(buys) == 1 and buys[0]["price"] == 100.0  # filled at our resting bid
    assert buys[0]["fee_usd"] > 0                  # maker fee charged
    pf = db.portfolio.docs[0]
    assert any(p["symbol"] == "ETH/USD" for p in pf["positions"])


@pytest.mark.asyncio
async def test_maker_fills_after_two_flat_ticks(monkeypatch):
    db = FakeDB(settings=RiskSettings(), portfolio=Portfolio(cash=50.0),
                pendings=[_pending(bid=100.0)])
    # flat: price above our bid, best bid still == our bid (not crossed, not run-away)
    monkeypatch.setattr(te, "fetch_snapshot", _async_snap(price=100.5, bid=100.0, ask=100.4))

    res1 = await te.process_pending_orders(db)
    assert res1 == []                              # tick 1: just increments
    assert db.pending_orders.docs[0]["ticks_flat"] == 1

    res2 = await te.process_pending_orders(db)
    assert res2 and res2[0]["reason"] == "FLAT_2_TICKS"
    assert db.pending_orders.docs == []


@pytest.mark.asyncio
async def test_maker_missed_fill_when_price_runs_up(monkeypatch):
    db = FakeDB(settings=RiskSettings(), portfolio=Portfolio(cash=50.0),
                pendings=[_pending(bid=100.0)])
    # best bid ticks up away from our resting bid
    monkeypatch.setattr(te, "fetch_snapshot", _async_snap(price=101.0, bid=100.5, ask=100.8))
    res = await te.process_pending_orders(db)
    assert res and res[0]["outcome"] == "MISSED_FILL_PRICE_RUN"
    assert db.pending_orders.docs == []            # cancelled
    assert any("MISSED_FILL_PRICE_RUN" in (r.get("blocked_reasons") or [])
               for r in db.reasoning.docs)
    assert not [t for t in db.trades.docs if t["side"] == "BUY"]  # no fill


@pytest.mark.asyncio
async def test_maker_cancelled_when_insufficient_cash(monkeypatch):
    db = FakeDB(settings=RiskSettings(), portfolio=Portfolio(cash=5.0),
                pendings=[_pending(bid=100.0, qty=1.0)])  # needs $100, only $5
    monkeypatch.setattr(te, "fetch_snapshot", _async_snap(price=99.0, bid=99.0, ask=99.3))
    res = await te.process_pending_orders(db)
    assert res and res[0]["outcome"] == "CANCELLED_NO_CASH"
    assert db.pending_orders.docs == []
    assert not [t for t in db.trades.docs if t["side"] == "BUY"]


@pytest.mark.asyncio
async def test_process_pending_noop_when_empty():
    db = FakeDB(settings=RiskSettings(), portfolio=Portfolio(cash=50.0))
    assert await te.process_pending_orders(db) == []


# ---------------- friction tally ----------------
@pytest.mark.asyncio
async def test_log_friction_tally_sums_fees_and_slippage():
    now = datetime.now(UTC).isoformat()
    trades = [
        {"timestamp": now, "fee_usd": 0.2, "slippage_usd": 0.05},
        {"timestamp": now, "fee_usd": 0.1, "slippage_usd": 0.10},
    ]
    db = FakeDB(trades=trades)
    tally = await te.log_friction_tally(db, RiskSettings())
    assert tally["fees_usd"] == 0.3
    assert tally["slippage_usd"] == 0.15
    assert tally["total_friction_usd"] == 0.45


# ---------------- LiveExecutor order_style (DRY_RUN) ----------------
@pytest.mark.asyncio
async def test_executor_post_only_rests_at_bid(monkeypatch):
    ex, err = get_dry_run_executor()
    assert ex is not None, err
    monkeypatch.setattr(ex, "is_live_ready", lambda: (True, "ok"))

    async def fake_recheck(symbol, cap):
        return True, {"bid": 100.0, "ask": 100.5, "spread_pct": 0.5, "limit": cap}
    monkeypatch.setattr(ex, "recheck_spread", fake_recheck)
    monkeypatch.setattr(ex, "adjust_for_min_size", lambda *a, **k: (0.1, 10.0, "ok"))

    res = await ex.place_buy("ETH/USD", desired_notional=10.0, max_cash=50.0,
                             ask=100.5, max_spread_pct=0.5, order_style="POST_ONLY")
    assert res.status == "DRY_RUN"
    assert res.filled_price == 100.0  # maker rests at BID


@pytest.mark.asyncio
async def test_executor_market_fills_at_ask(monkeypatch):
    ex, err = get_dry_run_executor()
    assert ex is not None, err
    monkeypatch.setattr(ex, "is_live_ready", lambda: (True, "ok"))

    async def fake_recheck(symbol, cap):
        return True, {"bid": 100.0, "ask": 100.5, "spread_pct": 0.5, "limit": cap}
    monkeypatch.setattr(ex, "recheck_spread", fake_recheck)
    monkeypatch.setattr(ex, "adjust_for_min_size", lambda *a, **k: (0.1, 10.05, "ok"))

    res = await ex.place_buy("ETH/USD", desired_notional=10.0, max_cash=50.0,
                             ask=100.5, max_spread_pct=0.2, order_style="MARKET")
    assert res.status == "DRY_RUN"
    assert res.filled_price == 100.5  # taker takes the ASK
