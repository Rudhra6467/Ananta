"""
Clean-slate reset for the diversified 6-asset Kraken-native matrix.

- Flushes legacy `reasoning` text summaries and wipes `research_log` rows (fresh validation slate).
- Clears trades, pending maker orders, and cooldowns.
- Resets the portfolio to the $300 paper baseline.
- Re-maps the watchlist to the 6 assets and restores the operational spec, preserving API keys
  + trading_mode.

Usage:  python reset_six_asset.py
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / ".env")

from asset_profiles import DEFAULT_SIX_ASSETS  # noqa: E402
from models import Portfolio, RiskSettings  # noqa: E402


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # 1) Clean slate: flush diagnostic + trade collections.
    for coll in ("reasoning", "research_log", "trades", "pending_orders", "cooldowns",
                 "shadow_positions", "shadow_trades"):
        res = await db[coll].delete_many({})
        print(f"cleared {coll}: {res.deleted_count} docs")

    # 2) Reset portfolio to $300 baseline.
    fresh = Portfolio()
    await db.portfolio.replace_one({"id": "singleton"}, fresh.model_dump(), upsert=True)
    print(f"portfolio reset -> ${fresh.starting_balance:.0f}")

    # 3) Re-map watchlist, preserving API keys + trading_mode.
    existing = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    settings = RiskSettings(**existing) if existing else RiskSettings()
    settings.enabled_symbols = list(DEFAULT_SIX_ASSETS)
    await db.settings.replace_one({"id": "singleton"}, settings.model_dump(), upsert=True)
    print(f"watchlist -> {settings.enabled_symbols} (mode={settings.trading_mode})")

    client.close()
    print("six-asset clean slate complete.")


if __name__ == "__main__":
    asyncio.run(main())
