"""
lab/data_store.py — local historical OHLCV store (SQLite, WAL) for the Research Lab.

All validations run OFFLINE and FREE against this DB, which is backfilled once via
CCXT and auto-appended on daily candle closes. One writer (the backfill/append job),
many readers (backtests) — WAL mode makes that safe.

Schema:  candles(symbol, timeframe, ts INTEGER ms, open, high, low, close, volume)
         UNIQUE(symbol, timeframe, ts)  -> INSERT OR IGNORE = idempotent appends.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import contextmanager

logger = logging.getLogger("ananta.lab.data")

DB_PATH = os.environ.get("HISTORICAL_DB_PATH", "/app/backend/data/historical_candles.db")

TF_MS = {"15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL, ts INTEGER NOT NULL,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                UNIQUE(symbol, timeframe, ts)
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_candles_key ON candles(symbol, timeframe, ts)")


def upsert_candles(symbol: str, timeframe: str, bars: list[list[float]]) -> int:
    """Idempotent insert of [ts, o, h, l, c, v] rows. Returns rows newly inserted."""
    if not bars:
        return 0
    with _conn() as con:
        before = con.total_changes
        con.executemany(
            "INSERT OR IGNORE INTO candles(symbol,timeframe,ts,open,high,low,close,volume) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(symbol, timeframe, int(b[0]), float(b[1]), float(b[2]), float(b[3]),
              float(b[4]), float(b[5])) for b in bars],
        )
        return con.total_changes - before


def load_candles(symbol: str, timeframe: str,
                 start_ms: int | None = None, end_ms: int | None = None) -> list[list[float]]:
    """Return [ts, o, h, l, c, v] rows ascending by ts within [start_ms, end_ms]."""
    q = "SELECT ts,open,high,low,close,volume FROM candles WHERE symbol=? AND timeframe=?"
    args: list = [symbol, timeframe]
    if start_ms is not None:
        q += " AND ts>=?"; args.append(int(start_ms))
    if end_ms is not None:
        q += " AND ts<=?"; args.append(int(end_ms))
    q += " ORDER BY ts ASC"
    with _conn() as con:
        return [list(r) for r in con.execute(q, args).fetchall()]


def coverage(symbol: str, timeframe: str) -> dict:
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*), MIN(ts), MAX(ts) FROM candles WHERE symbol=? AND timeframe=?",
            (symbol, timeframe),
        ).fetchone()
    return {"symbol": symbol, "timeframe": timeframe,
            "count": row[0] or 0, "min_ts": row[1], "max_ts": row[2]}


def _paginate(symbol: str, timeframe: str, since_ms: int, until_ms: int) -> list[list[float]]:
    """Page through CCXT OHLCV from since_ms up to until_ms (Kraken -> Coinbase fallback)."""
    from market_data import (
        _SYMBOL_MAP_COINBASE, _SYMBOL_MAP_KRAKEN, _get_coinbase, _get_kraken,
    )
    step = TF_MS[timeframe]
    for get_ex, smap, label in (
        (_get_kraken, _SYMBOL_MAP_KRAKEN, "kraken"),
        (_get_coinbase, _SYMBOL_MAP_COINBASE, "coinbase"),
    ):
        try:
            ex = get_ex()
            sym = smap.get(symbol, symbol)
            out: list[list[float]] = []
            cursor = since_ms
            while cursor < until_ms:
                batch = ex.fetch_ohlcv(sym, timeframe=timeframe, since=cursor, limit=720)
                if not batch:
                    break
                out.extend(batch)
                cursor = int(batch[-1][0]) + step
                if len(batch) < 720:
                    break
                time.sleep(getattr(ex, "rateLimit", 500) / 1000.0)
            if out:
                # dedupe + clip
                seen = {}
                for b in out:
                    if b[0] <= until_ms:
                        seen[int(b[0])] = [float(x) for x in b[:6]]
                return [seen[k] for k in sorted(seen)]
        except Exception as e:
            logger.warning("backfill %s %s via %s failed: %s", symbol, timeframe, label, e)
    return []


def backfill(symbol: str, timeframe: str, days: int) -> dict:
    """Fetch `days` of history for (symbol, timeframe) from CCXT into the DB (idempotent)."""
    init_db()
    now_ms = int(time.time() * 1000)
    since = now_ms - days * 86_400_000
    bars = _paginate(symbol, timeframe, since, now_ms)
    inserted = upsert_candles(symbol, timeframe, bars)
    cov = coverage(symbol, timeframe)
    logger.info("backfill %s %s: fetched=%d inserted=%d total=%d", symbol, timeframe, len(bars), inserted, cov["count"])
    return {"fetched": len(bars), "inserted": inserted, **cov}


def append_latest(symbol: str, timeframe: str) -> dict:
    """Idempotent tail append — fetch the most recent ~5 days and INSERT OR IGNORE.
    Safe to run on every daily candle close."""
    return backfill(symbol, timeframe, days=5)
