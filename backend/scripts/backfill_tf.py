"""Deep historical backfill for lower execution timeframes (15m, 30m, 1h).

Kraken ignores `since`; we page via Binance US (respects `since`, USD->USDT),
fallback Coinbase. Stored under the USD symbol. Usage:
    python scripts/backfill_tf.py 15m 30m
    python scripts/backfill_tf.py 1h 15m 30m
"""
import sys
import time

import ccxt

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, "/app/backend")
from asset_profiles import DEFAULT_ASSETS
from lab import data_store

DAYS = 420
STEP = {"15m": 900_000, "30m": 1_800_000, "1h": 3_600_000}


def _page(ex, sym, tf, since_ms, until_ms, page_limit):
    step = STEP[tf]
    out, cursor, last_ts = [], since_ms, None
    while cursor < until_ms:
        batch = ex.fetch_ohlcv(sym, tf, since=cursor, limit=page_limit)
        if not batch:
            break
        batch = [b for b in batch if b[0] <= until_ms]
        if not batch:
            break
        out.extend(batch)
        new_last = int(batch[-1][0])
        if last_ts is not None and new_last <= last_ts:
            break
        last_ts = new_last
        cursor = new_last + step
        time.sleep(getattr(ex, "rateLimit", 200) / 1000.0)
    seen = {int(b[0]): [float(x) for x in b[:6]] for b in out}
    return [seen[k] for k in sorted(seen)]


def backfill_symbol(usd_symbol, tf):
    now = int(time.time() * 1000)
    since = now - DAYS * 86_400_000
    base = usd_symbol.split("/")[0]
    for name, sym, lim in (("binanceus", f"{base}/USDT", 1000),
                           ("binance", f"{base}/USDT", 1000),
                           ("coinbase", usd_symbol, 300)):
        try:
            ex = getattr(ccxt, name)({"enableRateLimit": True})
            bars = _page(ex, sym, tf, since, now, lim)
            if len(bars) > 1000:
                return name, bars
        except Exception as e:
            print(f"  {usd_symbol} {tf} via {name}: {str(e)[:70]}", flush=True)
    return None, []


def main(tfs):
    data_store.init_db()
    for tf in tfs:
        print(f"=== {tf} ===", flush=True)
        for usd in DEFAULT_ASSETS:
            t0 = time.time()
            src, bars = backfill_symbol(usd, tf)
            if not bars:
                print(f"{usd} {tf}: NO DATA", flush=True)
                continue
            ins = data_store.upsert_candles(usd, tf, bars)
            cov = data_store.coverage(usd, tf)
            span = (cov["max_ts"] - cov["min_ts"]) / 86_400_000 if cov["count"] else 0
            print(f"{usd} {tf}: src={src} fetched={len(bars)} inserted={ins} total={cov['count']} span={span:.0f}d ({time.time()-t0:.1f}s)", flush=True)
    print("BACKFILL_DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["15m", "30m"])
