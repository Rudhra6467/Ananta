"""Resumable historical OHLCV backfill for the Ananta research warehouse.

Usage examples:
    python research_backfill.py --symbol BTC/USD --timeframe 1h --days 365
    python research_backfill.py --symbol BTC/USD --timeframe 1d --days 1825
    python research_backfill.py --symbol BTC/USD --timeframe 1m --days 30 --exchange kraken

The script intentionally does NOT claim that an exchange API can cheaply provide five
years of 1-minute history. For deep 1m research, use an archival source and feed its
CSV/Parquet rows through research_ingest.ingest_ohlcv. Exchange mode is primarily for
recent history and validation.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ccxt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from research_database import asset_membership, ensure_research_indexes
from research_ingest import ingest_ohlcv, utc_datetime

ROOT = Path(__file__).parent
load_dotenv(ROOT / '.env')
LOG = logging.getLogger("research_backfill")
DEFAULT_BATCH = 500

# This is a research bootstrap universe, NOT a claim about historical top-10 membership.
# Historical membership must be populated separately from dated market-cap snapshots.
BOOTSTRAP_ASSETS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD",
    "AVAX/USD", "LINK/USD", "DOT/USD", "DOGE/USD", "LTC/USD",
]


def _exchange(name: str):
    cls = getattr(ccxt, name)
    return cls({"enableRateLimit": True, "timeout": 15000})


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--symbol', required=True)
    p.add_argument('--timeframe', required=True)
    p.add_argument('--days', type=int, default=30)
    p.add_argument('--exchange', default='kraken')
    p.add_argument('--batch', type=int, default=DEFAULT_BATCH)
    p.add_argument('--source-version', default='exchange-v1')
    return p.parse_args()


def _to_rows(symbol: str, timeframe: str, bars: list[list[float]], source: str, version: str):
    rows = []
    for b in bars:
        if len(b) < 6:
            continue
        rows.append({
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': b[0],
            'open': b[1], 'high': b[2], 'low': b[3], 'close': b[4], 'volume': b[5],
            'source': source, 'data_version': version,
        })
    return rows


def _fetch_page(exchange, symbol: str, timeframe: str, since_ms: int, limit: int):
    native = symbol
    try:
        return exchange.fetch_ohlcv(native, timeframe=timeframe, since=since_ms, limit=limit)
    except (ccxt.BadSymbol, ccxt.ExchangeError):
        raise


async def run(args: argparse.Namespace) -> int:
    if args.timeframe not in ("1m", "5m", "15m", "1h", "4h", "1d"):
        raise SystemExit("Unsupported timeframe")
    if args.days <= 0:
        raise SystemExit("--days must be positive")

    mongo_url = os.environ['MONGO_URL']
    db_name = os.environ['DB_NAME']
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    await client.admin.command('ping')
    await ensure_research_indexes(db)

    ex = _exchange(args.exchange)
    try:
        ex.load_markets()
        if args.symbol not in ex.markets:
            raise SystemExit(f"{args.symbol} is unavailable on {args.exchange}")

        end = datetime.now(UTC)
        start = end - timedelta(days=args.days)
        cursor = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        total = 0
        pages = 0
        previous_last = None
        while cursor < end_ms:
            bars = await asyncio.to_thread(_fetch_page, ex, args.symbol, args.timeframe, cursor, args.batch)
            if not bars:
                break
            bars = sorted(bars, key=lambda b: b[0])
            rows = _to_rows(args.symbol, args.timeframe, bars, args.exchange, args.source_version)
            rows = [r for r in rows if r['timestamp'] <= end_ms]
            if rows:
                total += await ingest_ohlcv(db, rows)
                pages += 1
            last = int(bars[-1][0])
            if previous_last is not None and last <= previous_last:
                LOG.warning("Exchange returned no forward progress; stopping safely")
                break
            previous_last = last
            cursor = last + 1
            LOG.info("%s %s page=%d bars=%d total_written=%d", args.symbol, args.timeframe, pages, len(rows), total)
            if len(bars) < args.batch:
                break
    finally:
        ex.close()
        client.close()
    print(f"backfill complete: symbol={args.symbol} timeframe={args.timeframe} days={args.days} pages={pages} written={total}")
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    asyncio.run(run(_args()))


if __name__ == '__main__':
    main()
