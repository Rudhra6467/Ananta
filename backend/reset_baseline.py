"""Reset the paper-trading DB to a clean $300 baseline.

- Wipes trades, reasoning, and resting pending orders.
- Resets the portfolio singleton to a fresh $300 starting capital.
- Syncs the operational risk config (stop-loss 10% / trail-arm 5% / trail-dist
  3%, lots $20/$30/$50, 8 concurrent slots, full symbol taxonomy, adaptive
  + dynamic-trail enabled) WITHOUT touching saved exchange API keys or the
  current trading_mode.

Usage:  python reset_baseline.py
"""
import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

from models import Portfolio, RiskSettings  # noqa: E402

TAXONOMY = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD"]


def main():
    # 1) wipe history + resting orders
    t = db.trades.delete_many({}).deleted_count
    r = db.reasoning.delete_many({}).deleted_count
    p = db.pending_orders.delete_many({}).deleted_count

    # 2) fresh $300 portfolio
    fresh = Portfolio()
    db.portfolio.replace_one({"id": "singleton"}, fresh.model_dump(), upsert=True)

    # 3) restore the full operational spec, preserving only secrets + mode
    cur = db.settings.find_one({"id": "singleton"}) or {}
    s = RiskSettings().model_dump()  # clean spec defaults
    for keep in ("kraken_api_key", "kraken_api_secret",
                 "coinbase_api_key", "coinbase_api_secret",
                 "trading_mode", "manual_kill_switch"):
        if cur.get(keep) not in (None, ""):
            s[keep] = cur[keep]
    s["enabled_symbols"] = TAXONOMY
    db.settings.replace_one({"id": "singleton"}, s, upsert=True)

    print(f"wiped trades={t} reasoning={r} pending={p}")
    print(f"portfolio reset -> ${fresh.starting_balance:.2f} cash=${fresh.cash:.2f}")
    print(f"settings synced -> SL={s['stop_loss_pct']}% arm={s['trail_arm_pct']}% "
          f"dist={s['trail_distance_pct']}% conf={s['min_confidence']} lots "
          f"{s['normal_lot_usd']}/{s['strong_lot_usd']}/{s['breakout_lot_usd']} "
          f"slots={s['max_concurrent_positions']} mode={s['trading_mode']} symbols={s['enabled_symbols']}")


if __name__ == "__main__":
    main()
