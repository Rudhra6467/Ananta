"""Canonical point-in-time market ingestion helpers for the research warehouse.

The ingest layer is intentionally source-agnostic. Exchange adapters normalize their
records here before persistence, keeping the research database independent of CCXT or
any one vendor. Historical data and live data must use the same normalization contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from research_database import market_bar

SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")


def utc_datetime(value: datetime | str | int | float) -> datetime:
    """Normalize timestamps to timezone-aware UTC datetimes."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        # Numeric timestamps are accepted as milliseconds when large enough.
        seconds = float(value) / 1000.0 if abs(float(value)) > 10_000_000_000 else float(value)
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_ohlcv_row(
    *,
    symbol: str,
    timeframe: str,
    timestamp: datetime | str | int | float,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    trades: int | None = None,
    source: str,
    data_version: str = "v1",
) -> dict[str, Any]:
    """Normalize and validate one OHLCV observation."""
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported research timeframe: {timeframe}")
    values = (open, high, low, close, volume)
    if any(v is None for v in values):
        raise ValueError("OHLCV values cannot be null")
    o, h, l, c, v = map(float, values)
    if min(o, h, l, c) < 0 or v < 0:
        raise ValueError("OHLCV values cannot be negative")
    if h < max(o, c) or l > min(o, c) or h < l:
        raise ValueError("Invalid OHLC geometry")
    return market_bar(
        symbol=symbol.upper(), timeframe=timeframe, timestamp=utc_datetime(timestamp),
        o=o, h=h, l=l, c=c, volume=v, trades=trades,
        source=source, data_version=data_version,
    )


async def upsert_market_bars(db, rows: Iterable[dict[str, Any]]) -> int:
    """Idempotently upsert normalized bars by their canonical key."""
    from pymongo import UpdateOne

    operations = []
    for row in rows:
        operations.append(UpdateOne({"key": row["key"]}, {"$set": row}, upsert=True))
    if not operations:
        return 0
    result = await db.research_market_bars.bulk_write(operations, ordered=False)
    return int(result.upserted_count + result.modified_count + result.matched_count)


async def ingest_ohlcv(db, rows: Iterable[dict[str, Any]]) -> int:
    """Validate, normalize, and persist exchange-neutral OHLCV rows."""
    normalized = [normalize_ohlcv_row(**row) for row in rows]
    return await upsert_market_bars(db, normalized)


__all__ = ["SUPPORTED_TIMEFRAMES", "utc_datetime", "normalize_ohlcv_row", "upsert_market_bars", "ingest_ohlcv"]
