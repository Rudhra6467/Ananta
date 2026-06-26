"""
reset_sprint.py — FULL destructive reset for the 1-Month Paper Trading Sprint (Phase 2).

Wipes all dynamic state for an absolute blank slate so the 3-day Rejection
Leaderboard metrics are perfectly accurate from cycle #1:
  * clears research_log, trades, reasoning, pending_orders, shadow_trades, cooldowns
  * resets the paper portfolio to a flat $300.00 USD baseline
  * sets the finalized 10-asset watchlist and confirms PAPER mode
  * clears the in-memory level cache

Usage:  python reset_sprint.py
"""
from __future__ import annotations

import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

from asset_profiles import DEFAULT_ASSETS
from levels import clear_level_cache
from models import Portfolio, RiskSettings

START_BALANCE = 300.0
WIPE_COLLECTIONS = [
    "research_log", "trades", "reasoning", "pending_orders", "shadow_trades", "cooldowns",
]


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    for col in WIPE_COLLECTIONS:
        res = await db[col].delete_many({})
        print(f"  cleared {col:16s} ({res.deleted_count} docs)")

    # Flat $300 portfolio baseline.
    portfolio = Portfolio(
        starting_balance=START_BALANCE, cash=START_BALANCE,
        realized_pnl=0.0, day_start_equity=START_BALANCE,
    )
    await db.portfolio.replace_one({"id": "singleton"}, portfolio.model_dump(), upsert=True)
    print(f"  portfolio reset -> ${START_BALANCE:.2f} flat, 0 positions")

    # Finalized 10-asset watchlist + PAPER lock (preserve other tuned settings if present).
    existing = await db.settings.find_one({"id": "singleton"}) or {}
    existing.pop("_id", None)
    settings = RiskSettings(**{**existing})
    settings.enabled_symbols = list(DEFAULT_ASSETS)
    settings.trading_mode = "PAPER"
    settings.manual_kill_switch = False
    settings.normal_lot_usd = 20.0
    await db.settings.replace_one({"id": "singleton"}, settings.model_dump(), upsert=True)
    print(f"  watchlist -> {settings.enabled_symbols}")
    print(f"  normal_lot_usd -> ${settings.normal_lot_usd:.2f}")
    print(f"  trading_mode -> {settings.trading_mode}  (manual_kill={settings.manual_kill_switch})")

    clear_level_cache()
    print("  level cache cleared")
    print("RESET COMPLETE — blank slate ready for the sprint.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
