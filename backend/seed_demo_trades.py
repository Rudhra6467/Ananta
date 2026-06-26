"""Seed 15 synthetic historical PAPER round-trips to stress-test the Analytics
Panel + "Best Regime to Trade" insight card.

Distribution (matches the intended narrative):
  * LOW_COMPRESSION  -> mostly slight losses / chop (negative expectancy)
  * NORMAL           -> steady swing wins (solid positive expectancy)
  * HIGH_PANIC       -> asymmetric breakout wins (highest expectancy)

All docs are marked note="DEMO_SEED" so they can be removed with:
    python seed_demo_trades.py --clear

Usage:
    python seed_demo_trades.py          # seed
    python seed_demo_trades.py --clear  # remove all DEMO_SEED trades
"""
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

SECTORS = {"BTC/USDC": "Store of Value", "ETH/USDC": "Layer 1 High Beta",
           "SOL/USD": "Layer 1 High Beta", "XRP/USD": "Payments"}

# (regime, pnl, symbol) — friction derived below
PLAN = [
    # LOW_COMPRESSION — chop / slight losses
    ("LOW_COMPRESSION", -0.40, "XRP/USD"),
    ("LOW_COMPRESSION", -0.30, "BTC/USDC"),
    ("LOW_COMPRESSION", 0.20, "ETH/USDC"),
    ("LOW_COMPRESSION", -0.50, "SOL/USD"),
    ("LOW_COMPRESSION", -0.15, "XRP/USD"),
    # NORMAL — steady swing wins
    ("NORMAL", 0.80, "BTC/USDC"),
    ("NORMAL", 1.10, "ETH/USDC"),
    ("NORMAL", 0.60, "SOL/USD"),
    ("NORMAL", -0.40, "XRP/USD"),
    ("NORMAL", 0.90, "BTC/USDC"),
    ("NORMAL", 0.70, "ETH/USDC"),
    # HIGH_PANIC — asymmetric breakout wins
    ("HIGH_PANIC", 3.50, "SOL/USD"),
    ("HIGH_PANIC", -0.60, "ETH/USDC"),
    ("HIGH_PANIC", 2.80, "BTC/USDC"),
    ("HIGH_PANIC", -0.70, "SOL/USD"),
]

REGIME_ATR_PCT = {"LOW_COMPRESSION": 22.0, "NORMAL": 55.0, "HIGH_PANIC": 84.0}


def clear():
    r = db.trades.delete_many({"note": "DEMO_SEED"})
    print(f"removed {r.deleted_count} DEMO_SEED trades")


def seed():
    now = datetime.now(UTC)
    docs = []
    for i, (regime, pnl, symbol) in enumerate(PLAN):
        ts = (now - timedelta(hours=20 - i * 1.2)).isoformat()  # spread across ~20h
        price = 100.0
        qty = 0.2
        docs.append({
            "id": f"DEMO_{uuid.uuid4().hex[:8]}",
            "timestamp": ts, "symbol": symbol, "side": "SELL",
            "quantity": qty, "price": price, "notional": qty * price,
            "mode": "PAPER", "confidence": 0.85, "pnl": round(pnl, 4),
            "fee_usd": 0.05, "slippage_usd": round(0.02 + abs(pnl) * 0.01, 4),
            "status": "FILLED", "note": "DEMO_SEED",
            "exit_reason": "TRAIL_HIT" if pnl > 0 else "SL_HIT",
            "sector": SECTORS.get(symbol, "Altcoin / Commodity High Beta"),
            "volatility_regime": regime,
            "atr_at_entry": 1.2,
            "atr_percentile_at_entry": REGIME_ATR_PCT[regime],
        })
    db.trades.insert_many(docs)
    print(f"seeded {len(docs)} DEMO_SEED round-trips "
          f"(LOW_COMPRESSION/NORMAL/HIGH_PANIC). Best expectancy should be HIGH_PANIC.")


if __name__ == "__main__":
    if "--clear" in sys.argv:
        clear()
    else:
        clear()  # idempotent: clear any prior demo seed first
        seed()
