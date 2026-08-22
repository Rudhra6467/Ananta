"""
lab/data_store.py — durable historical OHLCV store (MongoDB) for the Research Lab.

Backed by MongoDB so the candle history SURVIVES production redeploys (the previous
SQLite file under /app/backend/data was ephemeral and wiped on every deploy). All
validations run OFFLINE and FREE against this store, which is backfilled once via CCXT
and auto-appended on daily candle closes.

Storage model:  collection `historical_candles`, ONE document per candle:
    { _id: "<symbol>|<timeframe>|<ts>", symbol, timeframe, ts(ms int), o, h, l, c, v }
The deterministic _id makes appends idempotent (upsert = the old INSERT OR IGNORE) and
dedupes for free. Index (symbol, timeframe, ts) powers range reads + ascending sort.

Public API is unchanged (init_db / upsert_candles / load_candles / coverage / backfill /
append_latest / TF_MS) so backtest / runner / server call sites need no changes.
"""
from __future__ import annotations

import logging
import os
import time

from pymongo import ASCENDING, MongoClient, UpdateOne

logger = logging.getLogger("ananta.lab.data")

COLLECTION = "historical_candles"

TF_MS = {"15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}

# Lazy, fork-safe Mongo client: ProcessPoolExecutor workers (the Lab runs backtests in a
# separate process) inherit the parent's client across fork, which pymongo forbids. We key
# the client by the creating PID and transparently recreate it after a fork/spawn.
_client: MongoClient | None = None
_client_pid: int | None = None
_indexed = False


def _load_env() -> None:
    if os.environ.get("MONGO_URL") and os.environ.get("DB_NAME"):
        return
    try:
        from pathlib import Path
        from dotenv import load_dotenv  # noqa: PLC0415
        backend = Path(__file__).resolve().parents[1]
        load_dotenv(backend / ".env")
        load_dotenv("/app/backend/.env")
    except Exception:
        pass


def _coll():
    global _client, _client_pid, _indexed
    pid = os.getpid()
    if _client is None or _client_pid != pid:
        _load_env()
        _client = MongoClient(os.environ["MONGO_URL"], tz_aware=False)
        _client_pid = pid
        _indexed = False
    coll = _client[os.environ["DB_NAME"]][COLLECTION]
    if not _indexed:
        coll.create_index([("symbol", ASCENDING), ("timeframe", ASCENDING), ("ts", ASCENDING)],
                           name="sym_tf_ts")
        _indexed = True
    return coll


def init_db() -> None:
    """Ensure the collection + index exist (idempotent)."""
    _coll()


def upsert_candles(symbol: str, timeframe: str, bars: list[list[float]]) -> int:
    """Idempotent insert of [ts, o, h, l, c, v] rows. Returns rows NEWLY inserted."""
    if not bars:
        return 0
    ops = []
    for b in bars:
        ts = int(b[0])
        ops.append(UpdateOne(
            {"_id": f"{symbol}|{timeframe}|{ts}"},
            {"$setOnInsert": {
                "symbol": symbol, "timeframe": timeframe, "ts": ts,
                "o": float(b[1]), "h": float(b[2]), "l": float(b[3]),
                "c": float(b[4]), "v": float(b[5]),
            }},
            upsert=True,
        ))
    res = _coll().bulk_write(ops, ordered=False)
    return int(res.upserted_count or 0)


def load_candles(symbol: str, timeframe: str,
                 start_ms: int | None = None, end_ms: int | None = None) -> list[list[float]]:
    """Return [ts, o, h, l, c, v] rows ascending by ts within [start_ms, end_ms]."""
    q: dict = {"symbol": symbol, "timeframe": timeframe}
    ts_filter: dict = {}
    if start_ms is not None:
        ts_filter["$gte"] = int(start_ms)
    if end_ms is not None:
        ts_filter["$lte"] = int(end_ms)
    if ts_filter:
        q["ts"] = ts_filter
    cur = _coll().find(q, {"_id": 0, "ts": 1, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}).sort("ts", ASCENDING)
    return [[d["ts"], d["o"], d["h"], d["l"], d["c"], d["v"]] for d in cur]


def coverage(symbol: str, timeframe: str) -> dict:
    coll = _coll()
    q = {"symbol": symbol, "timeframe": timeframe}
    count = coll.count_documents(q)
    min_ts = max_ts = None
    if count:
        first = coll.find(q, {"_id": 0, "ts": 1}).sort("ts", ASCENDING).limit(1)
        last = coll.find(q, {"_id": 0, "ts": 1}).sort("ts", -1).limit(1)
        min_ts = next(iter(first), {}).get("ts")
        max_ts = next(iter(last), {}).get("ts")
    return {"symbol": symbol, "timeframe": timeframe, "count": count, "min_ts": min_ts, "max_ts": max_ts}


def coverage_report(symbol: str, timeframe: str = "1h") -> dict:
    """Coverage plus ISO dates, span, and gap list. Used to prove ~1y exists."""
    from datetime import datetime, timezone

    cov = coverage(symbol, timeframe)
    step = TF_MS.get(timeframe, 3_600_000)
    min_ts, max_ts = cov.get("min_ts"), cov.get("max_ts")
    count = cov.get("count") or 0
    span_days = round((max_ts - min_ts) / 86_400_000, 1) if min_ts and max_ts else 0.0
    expected = int(span_days * (86_400_000 / step)) + 1 if span_days else 0
    gaps: list[dict] = []
    if count >= 2:
        coll = _coll()
        ts_list = [
            d["ts"]
            for d in coll.find(
                {"symbol": symbol, "timeframe": timeframe},
                {"_id": 0, "ts": 1},
            ).sort("ts", ASCENDING)
        ]
        for a, b in zip(ts_list, ts_list[1:]):
            delta = b - a
            if delta > step * 1.5:
                missing = max(0, int(delta / step) - 1)
                gaps.append({
                    "from_ts": a,
                    "to_ts": b,
                    "from_iso": datetime.fromtimestamp(a / 1000, tz=timezone.utc).isoformat(),
                    "to_iso": datetime.fromtimestamp(b / 1000, tz=timezone.utc).isoformat(),
                    "missing_bars": missing,
                })
    def _iso(ms):
        if not ms:
            return None
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

    usable_1y = bool(count >= 6000 and span_days >= 300)
    return {
        **cov,
        "from_iso": _iso(min_ts),
        "to_iso": _iso(max_ts),
        "span_days": span_days,
        "expected_bars": expected,
        "gap_count": len(gaps),
        "missing_bars_total": sum(g["missing_bars"] for g in gaps),
        "gaps": gaps[:20],
        "usable_1y": usable_1y,
        "note": "usable_1y requires ≥6000 1h bars and ≥300 calendar days",
    }


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
    """Fetch `days` of history for (symbol, timeframe) from CCXT into the store (idempotent)."""
    init_db()
    now_ms = int(time.time() * 1000)
    since = now_ms - days * 86_400_000
    bars = _paginate(symbol, timeframe, since, now_ms)
    inserted = upsert_candles(symbol, timeframe, bars)
    cov = coverage(symbol, timeframe)
    logger.info("backfill %s %s: fetched=%d inserted=%d total=%d", symbol, timeframe, len(bars), inserted, cov["count"])
    return {"fetched": len(bars), "inserted": inserted, **cov}


def append_latest(symbol: str, timeframe: str) -> dict:
    """Idempotent tail append — fetch the most recent ~5 days and upsert.
    Safe to run on every daily candle close."""
    return backfill(symbol, timeframe, days=5)
