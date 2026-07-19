"""
Layer 1 - Market Aggregation.
Uses CCXT to pull spot market data from Ontario-compliant exchanges (Kraken + Coinbase).
Falls back gracefully if an exchange call fails.
"""
from __future__ import annotations

import asyncio
import logging
import time

import ccxt
import requests
from requests.adapters import HTTPAdapter

from models import MarketSnapshot

logger = logging.getLogger(__name__)


def _pooled_session() -> requests.Session:
    """A requests session with a generously-sized connection pool so concurrent
    threaded CCXT fetches (snapshots + OHLCV + levels warmup) don't exhaust the
    default 10-connection urllib3 pool and stall waiting for a free connection."""
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

# Lazy-initialised exchange clients (sync; we run them in a thread)
_KRAKEN: ccxt.kraken | None = None
_COINBASE: ccxt.coinbase | None = None

# Symbol mappings - CCXT expects exchange-native formats
# We use BTC/USD as the canonical symbol; map to USDT pairs where USD is unavailable.
_SYMBOL_MAP_KRAKEN = {
    "BTC/USD": "BTC/USD",
    "ETH/USD": "ETH/USD",
    "SOL/USD": "SOL/USD",
    "XRP/USD": "XRP/USD",
    "ADA/USD": "ADA/USD",
}
_SYMBOL_MAP_COINBASE = {
    "BTC/USD": "BTC/USD",
    "ETH/USD": "ETH/USD",
    "SOL/USD": "SOL/USD",
    "XRP/USD": "XRP/USD",
    "ADA/USD": "ADA/USD",
}

# Simple in-memory cache to avoid hammering exchanges (TTL seconds)
_CACHE: dict[str, tuple[float, MarketSnapshot]] = {}
_CACHE_TTL = 5.0  # seconds

# Separate OHLCV cache - 1h bars don't change every 5s
_OHLCV_CACHE: dict[str, tuple[float, list[list[float]]]] = {}
_OHLCV_TTL = 300.0  # 5 minutes; new 1h candle only forms once an hour


def _get_kraken() -> ccxt.kraken:
    global _KRAKEN
    if _KRAKEN is None:
        _KRAKEN = ccxt.kraken({"enableRateLimit": True, "timeout": 5000, "session": _pooled_session()})
    return _KRAKEN


def _get_coinbase() -> ccxt.coinbase:
    global _COINBASE
    if _COINBASE is None:
        _COINBASE = ccxt.coinbase({"enableRateLimit": True, "timeout": 5000, "session": _pooled_session()})
    return _COINBASE


def _fetch_snapshot_sync(symbol: str) -> MarketSnapshot | None:
    """Try Kraken first; fall back to Coinbase. Returns None if both fail."""
    # 1) Kraken
    try:
        kraken_symbol = _SYMBOL_MAP_KRAKEN.get(symbol, symbol)
        ex = _get_kraken()
        ticker = ex.fetch_ticker(kraken_symbol)
        ob = ex.fetch_order_book(kraken_symbol, limit=10)
        return _build_snapshot(symbol, ticker, ob, exchange="kraken")
    except Exception as e:
        logger.warning("Kraken fetch failed for %s: %s", symbol, e)

    # 2) Coinbase
    try:
        cb_symbol = _SYMBOL_MAP_COINBASE.get(symbol, symbol)
        ex = _get_coinbase()
        ticker = ex.fetch_ticker(cb_symbol)
        ob = ex.fetch_order_book(cb_symbol, limit=10)
        return _build_snapshot(symbol, ticker, ob, exchange="coinbase")
    except Exception as e:
        logger.warning("Coinbase fetch failed for %s: %s", symbol, e)

    return None


def _build_snapshot(symbol: str, ticker: dict, ob: dict, exchange: str) -> MarketSnapshot:
    bid = float(ticker.get("bid") or (ob["bids"][0][0] if ob.get("bids") else 0.0))
    ask = float(ticker.get("ask") or (ob["asks"][0][0] if ob.get("asks") else 0.0))
    last = float(ticker.get("last") or ticker.get("close") or ((bid + ask) / 2 if bid and ask else 0.0))
    mid = (bid + ask) / 2.0 if bid and ask else last or 1.0
    spread_pct = ((ask - bid) / mid * 100.0) if mid > 0 else 0.0

    # Orderbook imbalance over top 10 levels
    bid_vol = sum(float(b[1]) for b in (ob.get("bids") or [])[:10])
    ask_vol = sum(float(a[1]) for a in (ob.get("asks") or [])[:10])
    total = bid_vol + ask_vol
    imbalance = ((bid_vol - ask_vol) / total) if total > 0 else 0.0

    return MarketSnapshot(
        symbol=symbol,
        price=last,
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        orderbook_imbalance=imbalance,
        volume_24h=float(ticker.get("baseVolume") or 0.0),
        change_24h_pct=float(ticker.get("percentage") or 0.0),
        exchange=exchange,
    )


# Bound the number of concurrent threaded exchange calls so a batch fetch
# (fetch_snapshots gathers over ALL symbols) can't spawn 20-30 simultaneous blocking
# HTTP calls and exhaust the connection/thread pools. 8 keeps warmup snappy while safe.
_FETCH_SEM = asyncio.Semaphore(8)


async def fetch_snapshot(symbol: str) -> MarketSnapshot | None:
    """Async wrapper that runs the sync CCXT call in a thread + uses TTL cache."""
    cached = _CACHE.get(symbol)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    async with _FETCH_SEM:
        snap = await asyncio.to_thread(_fetch_snapshot_sync, symbol)
    if snap is not None:
        _CACHE[symbol] = (now, snap)
    return snap


async def fetch_snapshots(symbols: list[str]) -> list[MarketSnapshot]:
    results = await asyncio.gather(*(fetch_snapshot(s) for s in symbols), return_exceptions=True)
    out: list[MarketSnapshot] = []
    for r in results:
        if isinstance(r, MarketSnapshot):
            out.append(r)
    return out


def get_cached_snapshot(symbol: str) -> MarketSnapshot | None:
    """Return the last cached snapshot for a symbol regardless of age (may be stale)."""
    c = _CACHE.get(symbol)
    return c[1] if c else None


async def fetch_snapshots_cached(symbols: list[str]) -> list[MarketSnapshot]:
    """Fast path for API endpoints: serve whatever is already in the in-memory cache
    instantly (ignoring the 5s TTL). Only symbols with NO cache entry at all trigger a
    live network fetch (first cold load). A background warmer keeps the cache fresh, so
    steady-state calls never touch the exchange and return in <5ms."""
    out: list[MarketSnapshot] = []
    missing: list[str] = []
    for s in symbols:
        c = _CACHE.get(s)
        if c is not None:
            out.append(c[1])
        else:
            missing.append(s)
    if missing:
        out.extend(await fetch_snapshots(missing))
    return out


async def warm_snapshots(symbols: list[str]) -> None:
    """Background refresh hook: re-fetch any symbol whose cache entry is older than the
    TTL so the fast path always has warm data. Cheap no-op when everything is fresh."""
    now = time.time()
    stale = [s for s in symbols
             if (c := _CACHE.get(s)) is None or now - c[0] >= _CACHE_TTL]
    if stale:
        await fetch_snapshots(stale)


def cache_stats() -> dict:
    """Non-blocking snapshot-cache health (no network). Used by /health/selfcheck."""
    now = time.time()
    ages = [now - ts for ts, _ in _CACHE.values()]
    return {
        "cached_symbols": len(_CACHE),
        "freshest_age_s": round(min(ages), 1) if ages else None,
        "stalest_age_s": round(max(ages), 1) if ages else None,
    }


# ---------------- 1h OHLCV fetch (for adaptive sizing classifier) ----------------
def _fetch_ohlcv_1h_sync(symbol: str, limit: int = 750) -> list[list[float]]:
    """Try Kraken first, then Coinbase. Returns CCXT-format OHLCV
    [[ts, open, high, low, close, volume], ...] sorted ascending by time.
    Returns [] if both exchanges fail."""
    # 1) Kraken
    try:
        kraken_symbol = _SYMBOL_MAP_KRAKEN.get(symbol, symbol)
        ex = _get_kraken()
        bars = ex.fetch_ohlcv(kraken_symbol, timeframe="1h", limit=limit)
        if bars:
            return [list(map(float, b)) for b in bars]
    except Exception as e:
        logger.warning("Kraken OHLCV fetch failed for %s: %s", symbol, e)

    # 2) Coinbase
    try:
        cb_symbol = _SYMBOL_MAP_COINBASE.get(symbol, symbol)
        ex = _get_coinbase()
        bars = ex.fetch_ohlcv(cb_symbol, timeframe="1h", limit=limit)
        if bars:
            return [list(map(float, b)) for b in bars]
    except Exception as e:
        logger.warning("Coinbase OHLCV fetch failed for %s: %s", symbol, e)

    return []


async def fetch_ohlcv_1h(symbol: str, limit: int = 750) -> list[list[float]]:
    """Async wrapper around 1h OHLCV with TTL cache. Used by the setup
    classifier to compute EMA/ATR/ADX for adaptive lot sizing."""
    key = f"{symbol}@{limit}"
    cached = _OHLCV_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < _OHLCV_TTL:
        return cached[1]
    bars = await asyncio.to_thread(_fetch_ohlcv_1h_sync, symbol, limit)
    if bars:
        _OHLCV_CACHE[key] = (now, bars)
    return bars


def _fetch_ohlcv_tf_sync(symbol: str, timeframe: str, limit: int) -> list[list[float]]:
    """Generic OHLCV fetch on any timeframe ('4h', '1d', ...) with Kraken->Coinbase fallback."""
    try:
        kraken_symbol = _SYMBOL_MAP_KRAKEN.get(symbol, symbol)
        ex = _get_kraken()
        bars = ex.fetch_ohlcv(kraken_symbol, timeframe=timeframe, limit=limit)
        if bars:
            return [list(map(float, b)) for b in bars]
    except Exception as e:
        logger.warning("Kraken %s OHLCV fetch failed for %s: %s", timeframe, symbol, e)
    try:
        cb_symbol = _SYMBOL_MAP_COINBASE.get(symbol, symbol)
        ex = _get_coinbase()
        bars = ex.fetch_ohlcv(cb_symbol, timeframe=timeframe, limit=limit)
        if bars:
            return [list(map(float, b)) for b in bars]
    except Exception as e:
        logger.warning("Coinbase %s OHLCV fetch failed for %s: %s", timeframe, symbol, e)
    return []


async def fetch_ohlcv_4h(symbol: str, limit: int = 300) -> list[list[float]]:
    """4h OHLCV with TTL cache; powers the higher-timeframe swing trend filter."""
    key = f"4h@{symbol}@{limit}"
    cached = _OHLCV_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < _OHLCV_TTL * 2:  # 4h candles change slower; cache longer
        return cached[1]
    bars = await asyncio.to_thread(_fetch_ohlcv_tf_sync, symbol, "4h", limit)
    if bars:
        _OHLCV_CACHE[key] = (now, bars)
    return bars


async def fetch_ohlcv_1d(symbol: str, limit: int = 540) -> list[list[float]]:
    """Daily OHLCV with a long TTL cache; powers the historical horizontal
    level engine (1–2 years of structure). Credit-free CCXT fetch."""
    key = f"1d@{symbol}@{limit}"
    cached = _OHLCV_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < _OHLCV_TTL * 12:  # daily structure barely moves intraday
        return cached[1]
    bars = await asyncio.to_thread(_fetch_ohlcv_tf_sync, symbol, "1d", limit)
    if bars:
        _OHLCV_CACHE[key] = (now, bars)
    return bars
