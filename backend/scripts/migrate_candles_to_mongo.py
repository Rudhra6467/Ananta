"""One-time migration: copy historical OHLCV candles from the legacy ephemeral SQLite
file into durable MongoDB (collection `historical_candles`). Idempotent — safe to re-run
(deterministic _id + ordered=False skips already-migrated candles).
"""
from __future__ import annotations

import os
import sqlite3

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import BulkWriteError

load_dotenv("/app/backend/.env")

SQLITE_PATH = os.environ.get("HISTORICAL_DB_PATH", "/app/backend/data/historical_candles.db")
COLLECTION = "historical_candles"
BATCH = 5000


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f"no sqlite file at {SQLITE_PATH} — nothing to migrate")
        return
    con = sqlite3.connect(SQLITE_PATH)
    total = con.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    print(f"sqlite candles: {total}")

    cli = MongoClient(os.environ["MONGO_URL"], tz_aware=False)
    coll = cli[os.environ["DB_NAME"]][COLLECTION]
    before = coll.estimated_document_count()
    print(f"mongo before: {before}")

    cur = con.execute("SELECT symbol,timeframe,ts,open,high,low,close,volume FROM candles ORDER BY symbol,timeframe,ts")
    batch, migrated, dupes = [], 0, 0
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        batch = [{
            "_id": f"{r[0]}|{r[1]}|{int(r[2])}", "symbol": r[0], "timeframe": r[1], "ts": int(r[2]),
            "o": float(r[3]), "h": float(r[4]), "l": float(r[5]), "c": float(r[6]), "v": float(r[7]),
        } for r in rows]
        try:
            res = coll.insert_many(batch, ordered=False)
            migrated += len(res.inserted_ids)
        except BulkWriteError as bwe:
            migrated += bwe.details.get("nInserted", 0)
            dupes += len(bwe.details.get("writeErrors", []))
        print(f"  migrated={migrated} dupes_skipped={dupes}", flush=True)

    after = coll.estimated_document_count()
    print(f"mongo after: {after} (delta +{after - before})")
    con.close()


if __name__ == "__main__":
    main()
