"""Closed-bar discipline: Hands never decides on a still-forming candle (2026-09-29).

Pure unit test. No network: the exchange fetchers are replaced with fakes.
Runs under pytest, or directly: python tests/test_closed_bars.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if "ccxt" not in sys.modules:  # keep the test runnable where ccxt isn't installed
    try:
        import ccxt  # noqa: F401
    except ImportError:
        sys.modules["ccxt"] = types.SimpleNamespace(kraken=object, coinbase=object)

import market_data as md  # noqa: E402

H = 3600
T0 = 1_790_690_400  # 2026-09-29 12:00:00 UTC, an hour boundary


def _bars(n: int, start: int = T0, tf: int = H):
    return [[float((start + i * tf) * 1000), 1.0, 2.0, 0.5, 1.5, 10.0] for i in range(n)]


def test_forming_bar_is_dropped():
    bars = _bars(4)  # 12:00, 13:00, 14:00, 15:00
    now = T0 + 3 * H + 30 * 60  # 15:30 -> the 15:00 bar is still forming
    out = md.closed_bars(bars, "1h", now)
    assert [b[0] for b in out] == [b[0] for b in bars[:3]]


def test_bar_counts_as_closed_exactly_at_its_close():
    bars = _bars(4)
    assert len(md.closed_bars(bars, "1h", T0 + 4 * H)) == 4
    assert len(md.closed_bars(bars, "1h", T0 + 4 * H - 1)) == 3


def test_4h_and_1d_use_their_own_period():
    b4 = _bars(3, tf=4 * H)
    assert len(md.closed_bars(b4, "4h", T0 + 2 * 4 * H + H)) == 2
    b1d = _bars(2, tf=24 * H)
    assert len(md.closed_bars(b1d, "1d", T0 + 24 * H + 5 * H)) == 1


def test_intraday_timeframes_use_their_own_period():
    b15 = _bars(4, tf=900)  # 12:00 12:15 12:30 12:45
    assert len(md.closed_bars(b15, "15m", T0 + 3 * 900 + 60)) == 3  # 12:46 -> 12:45 still forming
    assert len(md.closed_bars(b15, "15m", T0 + 4 * 900)) == 4
    b30 = _bars(3, tf=1800)
    assert len(md.closed_bars(b30, "30m", T0 + 2 * 1800 + 60)) == 2
    b5 = _bars(3, tf=300)
    assert len(md.closed_bars(b5, "5m", T0 + 3 * 300 - 1)) == 2


def test_fetch_intraday_refetches_after_each_15m_close_and_rejects_other_tfs():
    calls = []
    real_time = md.time.time
    clock = {"now": T0 + 900 - 30}  # 12:14:30

    def fake_fetch(symbol, timeframe, limit):
        calls.append((timeframe, clock["now"]))
        n = int((clock["now"] - T0) // 900) + 1  # includes the forming bar
        return _bars(n, tf=900)

    md._OHLCV_CACHE.clear()
    orig = md._fetch_ohlcv_tf_sync
    md._fetch_ohlcv_tf_sync = fake_fetch
    md.time.time = lambda: clock["now"]
    try:
        a = asyncio.run(md.fetch_ohlcv_intraday("BTC/USD", "15m", limit=10))
        assert a == []  # only the forming 12:00 bar exists yet
        clock["now"] = T0 + 900 + 60  # 12:16: the 12:00 bar closed since the fetch
        b = asyncio.run(md.fetch_ohlcv_intraday("BTC/USD", "15m", limit=10))
        assert len(calls) == 2 and b[-1][0] == T0 * 1000
        clock["now"] = T0 + 900 + 120  # same bar, inside the TTL: served from cache
        asyncio.run(md.fetch_ohlcv_intraday("BTC/USD", "15m", limit=10))
        assert len(calls) == 2
        try:
            asyncio.run(md.fetch_ohlcv_intraday("BTC/USD", "2h", limit=10))
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported timeframe must be refused")
    finally:
        md._fetch_ohlcv_tf_sync = orig
        md.time.time = real_time
        md._OHLCV_CACHE.clear()


def test_cache_expires_when_a_bar_closes():
    fetched = T0 + 2 * H - 120  # 13:58
    assert md._cache_fresh(fetched, fetched + 60, 300, "1h") is True       # 13:59, same bar
    assert md._cache_fresh(fetched, T0 + 2 * H + 120, 300, "1h") is False  # 14:02, 13:00 bar closed since


def test_fetch_ohlcv_1h_returns_closed_only_and_refetches_after_close(monkeypatch=None):
    calls = []
    real_time = md.time.time
    clock = {"now": T0 + 2 * H - 120}  # 13:58

    def fake_fetch(symbol, limit):
        calls.append(clock["now"])
        n = int((clock["now"] - T0) // H) + 1  # includes the forming bar, like Kraken
        return _bars(n)

    md._OHLCV_CACHE.clear()
    orig = md._fetch_ohlcv_1h_sync
    md._fetch_ohlcv_1h_sync = fake_fetch
    md.time.time = lambda: clock["now"]
    try:
        first = asyncio.run(md.fetch_ohlcv_1h("BTC/USD", limit=10))
        assert first[-1][0] == (T0 + 0 * H) * 1000  # 13:00 still forming -> last closed is 12:00
        clock["now"] = T0 + 2 * H + 120  # 14:02
        second = asyncio.run(md.fetch_ohlcv_1h("BTC/USD", limit=10))
        assert len(calls) == 2, "cache from 13:58 must not be served after the 14:00 close"
        assert second[-1][0] == (T0 + 1 * H) * 1000  # the 13:00 bar, now closed and complete
    finally:
        md._fetch_ohlcv_1h_sync = orig
        md.time.time = real_time
        md._OHLCV_CACHE.clear()


def test_switch_restores_old_behaviour():
    md.CLOSED_BARS_ONLY = False
    try:
        bars = _bars(4)
        assert md.closed_bars(bars, "1h", T0 + 3 * H + 1800) == bars
    finally:
        md.CLOSED_BARS_ONLY = True


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
