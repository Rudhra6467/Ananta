"""
lab/backfill.py — one-shot CCXT backfill of the local historical store.

Usage:
    python -m lab.backfill                 # default watchlist, 4h+1d, ~2y
    python -m lab.backfill BTC/USD ETH/USD # specific symbols

Credit-free (keyless CCXT). Safe to re-run — inserts are idempotent.
The daily auto-append is wired separately via lab.data_store.append_latest.
"""
from __future__ import annotations

import sys

from lab import data_store

DEFAULT_SYMBOLS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "XRP/USD",
    "PAXG/USD", "LINK/USD", "AAVE/USD", "ARB/USD", "RENDER/USD",
]
TIMEFRAMES = [("4h", 730), ("1d", 730)]  # ~2 years each


def main(symbols: list[str]) -> None:
    data_store.init_db()
    for sym in symbols:
        for tf, days in TIMEFRAMES:
            r = data_store.backfill(sym, tf, days)
            print(f"{sym:12} {tf:3} -> fetched={r['fetched']:5} inserted={r['inserted']:5} total={r['count']:5}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if "/" in a]
    main(args or DEFAULT_SYMBOLS)
