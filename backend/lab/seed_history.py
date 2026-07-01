"""
lab/seed_history.py — deep historical seeding for the Research Lab (credit-free, offline).

Two sources, both FREE and keyless:
  1) Binance public data repo (data.binance.vision) — monthly kline ZIP/CSV per symbol.
     Gives immediate ~2 years of 4h history, detached from Kraken's ~120-day cap.
  2) Generic CSV files (e.g. CryptoDataDownload) you drop on disk — parsed & seeded.

After seeding, the existing CCXT `lab.data_store.append_latest` job keeps the tail fresh.

Binance URL pattern:
  https://data.binance.vision/data/spot/monthly/klines/{SYM}/{TF}/{SYM}-{TF}-{YYYY-MM}.zip
Binance kline CSV columns: open_time, open, high, low, close, volume, close_time, ...
open_time is ms historically; newer (2025+) files use microseconds -> normalised here.
"""
from __future__ import annotations

import csv as _csv
import io
import logging
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

from lab import data_store

logger = logging.getLogger("ananta.lab.seed")

BINANCE_BASE = "https://data.binance.vision/data/spot/monthly/klines"

# Our USD watchlist -> candidate Binance (USDT) symbols. First hit wins per month
# (RENDER was listed as RNDR before its 2024 rebrand, so we try both).
BINANCE_MAP: dict[str, list[str]] = {
    "BTC/USD": ["BTCUSDT"],
    "ETH/USD": ["ETHUSDT"],
    "SOL/USD": ["SOLUSDT"],
    "AVAX/USD": ["AVAXUSDT"],
    "XRP/USD": ["XRPUSDT"],
    "PAXG/USD": ["PAXGUSDT"],
    "LINK/USD": ["LINKUSDT"],
    "AAVE/USD": ["AAVEUSDT"],
    "ARB/USD": ["ARBUSDT"],
    "RENDER/USD": ["RENDERUSDT", "RNDRUSDT"],
}


def _norm_ts(v: float) -> int:
    """Normalise a Binance timestamp to milliseconds (handles ms and microseconds)."""
    ts = int(float(v))
    if ts > 1e14:          # microseconds (2025+ files)
        ts //= 1000
    elif ts < 1e11:        # seconds
        ts *= 1000
    return ts


def _parse_klines(text: str) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 6:
            continue
        try:
            ts = _norm_ts(parts[0])
            o, h, low, c, v = (float(parts[1]), float(parts[2]), float(parts[3]),
                               float(parts[4]), float(parts[5]))
        except (ValueError, IndexError):
            continue  # header row or malformed
        rows.append([ts, o, h, low, c, v])
    return rows


def _download_zip_csv(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ananta-lab/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            blob = resp.read()
        zf = zipfile.ZipFile(io.BytesIO(blob))
        return zf.read(zf.namelist()[0]).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            logger.warning("HTTP %s for %s", e.code, url)
        return None
    except Exception as e:
        logger.warning("download failed %s: %s", url, e)
        return None


def _month_range(months: int) -> list[tuple[int, int]]:
    """Last `months` COMPLETE months, oldest-first (excludes the current month)."""
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month
    out: list[tuple[int, int]] = []
    for _ in range(months):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out.append((y, m))
    return list(reversed(out))


def seed_from_binance(symbols: list[str] | None = None, months: int = 24,
                      timeframe: str = "4h") -> dict:
    """Download `months` of monthly kline CSVs from Binance and seed the local DB."""
    data_store.init_db()
    symbols = symbols or list(BINANCE_MAP.keys())
    results: dict[str, dict] = {}
    for sym in symbols:
        candidates = BINANCE_MAP.get(sym, [sym.replace("/", "").replace("USD", "USDT")])
        fetched = inserted = missing = 0
        for (y, m) in _month_range(months):
            got = False
            for bsym in candidates:
                url = f"{BINANCE_BASE}/{bsym}/{timeframe}/{bsym}-{timeframe}-{y:04d}-{m:02d}.zip"
                text = _download_zip_csv(url)
                if text:
                    bars = _parse_klines(text)
                    inserted += data_store.upsert_candles(sym, timeframe, bars)
                    fetched += len(bars)
                    got = True
                    break
            if not got:
                missing += 1
        cov = data_store.coverage(sym, timeframe)
        results[sym] = {"fetched": fetched, "inserted": inserted, "missing_months": missing,
                        "count": cov["count"], "min_ts": cov["min_ts"], "max_ts": cov["max_ts"]}
        logger.info("seeded %s %s: fetched=%d inserted=%d missing_months=%d total=%d",
                    sym, timeframe, fetched, inserted, missing, cov["count"])
    return results


# ---------- generic CSV seeding (CryptoDataDownload or any OHLCV export) ----------
def _find(header: list[str], *names: str) -> int | None:
    low = [h.strip().lower() for h in header]
    for n in names:
        for i, h in enumerate(low):
            if n in h:
                return i
    return None


def seed_from_csv(path: str, symbol: str, timeframe: str = "4h") -> dict:
    """Parse a local CSV (auto-detects columns; handles CryptoDataDownload's comment
    line + unix/date columns) and seed it into the DB under (symbol, timeframe)."""
    data_store.init_db()
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    # CryptoDataDownload prepends a URL/comment line before the header.
    if lines and ("http" in lines[0].lower() or lines[0].lower().startswith("//")):
        lines = lines[1:]
    reader = list(_csv.reader(lines))
    if not reader:
        return {"error": "empty_csv"}
    header = reader[0]
    ci_ts = _find(header, "unix", "open_time", "timestamp", "time", "date")
    ci_o = _find(header, "open")
    ci_h = _find(header, "high")
    ci_l = _find(header, "low")
    ci_c = _find(header, "close")
    ci_v = _find(header, "volume")
    if None in (ci_ts, ci_o, ci_h, ci_l, ci_c, ci_v):
        return {"error": "missing_columns", "header": header}
    bars: list[list[float]] = []
    for row in reader[1:]:
        try:
            raw = row[ci_ts]
            ts = _norm_ts(raw) if raw.replace(".", "").isdigit() else int(
                datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() * 1000)
            bars.append([ts, float(row[ci_o]), float(row[ci_h]), float(row[ci_l]),
                         float(row[ci_c]), float(row[ci_v])])
        except (ValueError, IndexError, KeyError):
            continue
    inserted = data_store.upsert_candles(symbol, timeframe, bars)
    cov = data_store.coverage(symbol, timeframe)
    return {"parsed": len(bars), "inserted": inserted, **cov}


if __name__ == "__main__":
    import json
    print(json.dumps(seed_from_binance(months=24, timeframe="4h"), indent=2, default=str))
