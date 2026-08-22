"""One-time deep 1h historical backfill for the backtester (execution timeframe = 1h).

Kraken's OHLC endpoint ignores `since` (returns only the most recent ~720 candles),
so for deep history we page via Binance US (720/page, respects `since`, USD->USDT),
falling back to Coinbase (300/page) per symbol. Data is stored under the USD symbol.
"""
import sys
import time

import ccxt

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except Exception:
    pass
from asset_profiles import DEFAULT_ASSETS
from lab import data_store

DAYS = 420
STEP_MS = 3_600_000  # 1h


def _page(ex, sym, since_ms, until_ms, page_limit):
    out, cursor, last_ts = [], since_ms, None
    while cursor < until_ms:
        batch = ex.fetch_ohlcv(sym, "1h", since=cursor, limit=page_limit)
        if not batch:
            break
        batch = [b for b in batch if b[0] <= until_ms]
        if not batch:
            break
        out.extend(batch)
        new_last = int(batch[-1][0])
        if last_ts is not None and new_last <= last_ts:
            break  # no forward progress
        last_ts = new_last
        cursor = new_last + STEP_MS
        time.sleep(getattr(ex, "rateLimit", 300) / 1000.0)
    # dedupe by ts
    seen = {int(b[0]): [float(x) for x in b[:6]] for b in out}
    return [seen[k] for k in sorted(seen)]


def backfill_symbol(usd_symbol):
    now = int(time.time() * 1000)
    since = now - DAYS * 86_400_000
    base = usd_symbol.split("/")[0]
    attempts = [
        ("binanceus", f"{base}/USDT", 720),
        ("coinbase", usd_symbol, 300),
        ("binance", f"{base}/USDT", 720),
    ]
    for name, sym, lim in attempts:
        try:
            ex = getattr(ccxt, name)({"enableRateLimit": True})
            bars = _page(ex, sym, since, now, lim)
            if len(bars) > 720:  # got real depth
                return name, sym, bars
        except Exception as e:
            print(f"  {usd_symbol} via {name} ({sym}): {str(e)[:70]}", flush=True)
    return None, None, []


data_store.init_db()
for usd in DEFAULT_ASSETS:
    t0 = time.time()
    src, sym, bars = backfill_symbol(usd)
    if not bars:
        print(f"{usd}: NO DATA", flush=True)
        continue
    ins = data_store.upsert_candles(usd, "1h", bars)
    cov = data_store.coverage(usd, "1h")
    span_days = (cov["max_ts"] - cov["min_ts"]) / 86_400_000 if cov["count"] else 0
    print(f"{usd}: src={src} fetched={len(bars)} inserted={ins} total={cov['count']} span={span_days:.0f}d ({time.time()-t0:.1f}s)", flush=True)
print("BACKFILL_DONE", flush=True)
