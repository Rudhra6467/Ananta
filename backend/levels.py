"""
levels.py — Historical Horizontal Support/Resistance Level Engine (Phase 1.5a).

Scans 1–2 years of Daily + 4h candles and maps durable HORIZONTAL support/
resistance zones via fractal swing-pivot detection + price clustering. This is
the structural memory the "clean chance-taking" entry model buys into: a price
band that has been touched/rejected multiple times over 1–2 years is a clean
horizontal floor (the SOL ~$86–87 flip zone is exactly this).

Pure CCXT/compute — NO LLM, NO credits. Zones change slowly, so results are
cached per-symbol (6h TTL); ongoing cost is effectively zero.

Design notes
------------
* A zone earns significance from the NUMBER of pivots that clustered into it
  ("touches"). Daily pivots are weighted heavier than 4h pivots (a level that
  matters on the daily is structurally stronger than an intraday wiggle).
* Both pivot highs AND lows feed the same clusters — a level flips between
  support and resistance over time, and the flip zones are the most tradable.
* `nearest_support` answers the only question the entry trigger cares about:
  "is price right now sitting on a major historical floor?"
"""
from __future__ import annotations

import asyncio
import logging
import time

from market_data import fetch_ohlcv_1d, fetch_ohlcv_1h

logger = logging.getLogger(__name__)

# OHLCV bar layout: [timestamp_ms, open, high, low, close, volume]
_TS, _O, _HI, _LO, _C, _V = 0, 1, 2, 3, 4, 5

# Per-symbol cache: {symbol: (epoch, zones)}. Zones recompute slowly.
_LEVEL_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL_SECONDS = 6 * 3600

# Defaults (overridable via RiskSettings)
DEFAULT_TOL_PCT = 0.75       # cluster band width: pivots within 0.75% merge into one zone
DEFAULT_MIN_TOUCHES = 2      # a zone must be tested at least twice to count
DEFAULT_DAILY_LOOKBACK = 540  # ~18 months of daily bars
DEFAULT_1H_LOOKBACK = 720     # ~30 days of 1h bars (execution-timeframe intraday leg)
PIVOT_K = 3                   # fractal half-window: extreme vs ±3 neighbours
DAILY_WEIGHT = 2.0
INTRADAY_WEIGHT = 1.0


def clear_level_cache() -> None:
    """For tests / forced recompute."""
    _LEVEL_CACHE.clear()


def _pivots(bars: list[list[float]], k: int) -> list[tuple[float, float]]:
    """Return [(timestamp, price), ...] for every fractal swing high and low.

    A bar is a swing HIGH if its high is the max within ±k neighbours; a swing
    LOW if its low is the min. Both are returned (flip zones use both)."""
    out: list[tuple[float, float]] = []
    n = len(bars)
    if n < 2 * k + 1:
        return out
    for i in range(k, n - k):
        window = bars[i - k:i + k + 1]
        hi = bars[i][_HI]
        lo = bars[i][_LO]
        if hi >= max(b[_HI] for b in window):
            out.append((bars[i][_TS], hi))
        if lo <= min(b[_LO] for b in window):
            out.append((bars[i][_TS], lo))
    return out


def _cluster(points: list[tuple[float, float, float]], tol_pct: float) -> list[dict]:
    """Greedy 1-D clustering of (ts, price, weight) into horizontal zones.

    Points are sorted by price; a point joins the current cluster if it sits
    within ``tol_pct`` of the cluster's running mean, else it starts a new one.
    """
    if not points:
        return []
    items = sorted(points, key=lambda p: p[1])
    clusters: list[dict] = []
    for ts, price, w in items:
        if clusters:
            c = clusters[-1]
            mean = c["sum"] / c["n"]
            if mean > 0 and abs(price - mean) / mean * 100.0 <= tol_pct:
                c["sum"] += price
                c["n"] += 1
                c["weight"] += w
                c["lo"] = min(c["lo"], price)
                c["hi"] = max(c["hi"], price)
                c["last_ts"] = max(c["last_ts"], ts)
                continue
        clusters.append({
            "sum": price, "n": 1, "weight": w,
            "lo": price, "hi": price, "last_ts": ts,
        })
    return clusters


def compute_levels(
    daily_bars: list[list[float]],
    h4_bars: list[list[float]],
    *,
    tol_pct: float = DEFAULT_TOL_PCT,
    min_touches: int = DEFAULT_MIN_TOUCHES,
    pivot_k: int = PIVOT_K,
) -> list[dict]:
    """Pure function: candles -> ranked horizontal zones.

    Returns a list of zone dicts sorted by structural strength (descending):
        {low, high, mid, touches, strength, last_touch_ms}
    """
    points: list[tuple[float, float, float]] = []
    for ts, price in _pivots(daily_bars or [], pivot_k):
        points.append((ts, price, DAILY_WEIGHT))
    for ts, price in _pivots(h4_bars or [], pivot_k):
        points.append((ts, price, INTRADAY_WEIGHT))

    zones: list[dict] = []
    for c in _cluster(points, tol_pct):
        if c["n"] < min_touches:
            continue
        zones.append({
            "low": round(c["lo"], 8),
            "high": round(c["hi"], 8),
            "mid": round(c["sum"] / c["n"], 8),
            "touches": int(c["n"]),
            "strength": round(c["weight"], 2),
            "last_touch_ms": int(c["last_ts"]),
        })
    zones.sort(key=lambda z: z["strength"], reverse=True)
    return zones


def nearest_support(price: float | None, zones: list[dict], proximity_pct: float) -> dict | None:
    """The strongest zone price is currently TESTING from above.

    A zone qualifies if price sits inside it, or just above its high within
    ``proximity_pct``. Among qualifiers, the strongest (most-touched) wins —
    that is the clean historical floor the entry model buys into.
    """
    if not price or price <= 0 or not zones:
        return None
    best: dict | None = None
    for z in zones:
        lo, hi = z["low"], z["high"]
        band_low = lo * (1.0 - proximity_pct / 100.0)
        band_high = hi * (1.0 + proximity_pct / 100.0)
        # support = zone is at/below current price (mid not far above price)
        if z["mid"] <= price * (1.0 + proximity_pct / 100.0) and band_low <= price <= band_high:
            if best is None or z["strength"] > best["strength"]:
                best = z
    return best


def nearest_resistance(price: float | None, zones: list[dict], proximity_pct: float) -> dict | None:
    """The strongest zone sitting ABOVE current price (overhead supply)."""
    if not price or price <= 0 or not zones:
        return None
    above = [z for z in zones if z["mid"] > price * (1.0 + proximity_pct / 100.0)]
    if not above:
        return None
    # closest overhead zone, tie-broken by strength
    above.sort(key=lambda z: (z["mid"] - price, -z["strength"]))
    return above[0]


async def get_levels(symbol: str, settings=None) -> list[dict]:
    """Cached zone fetch for a symbol. Credit-free (CCXT only)."""
    now = time.time()
    cached = _LEVEL_CACHE.get(symbol)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]

    daily_limit = int(getattr(settings, "level_lookback_days", DEFAULT_DAILY_LOOKBACK)) if settings else DEFAULT_DAILY_LOOKBACK
    tol = float(getattr(settings, "level_zone_tol_pct", DEFAULT_TOL_PCT)) if settings else DEFAULT_TOL_PCT
    min_touches = int(getattr(settings, "level_min_touches", DEFAULT_MIN_TOUCHES)) if settings else DEFAULT_MIN_TOUCHES

    daily = await fetch_ohlcv_1d(symbol, limit=daily_limit)
    intraday = await fetch_ohlcv_1h(symbol, limit=DEFAULT_1H_LOOKBACK)
    # compute_levels is CPU-heavy clustering over ~1000+ bars — run it off the event
    # loop so the single uvicorn worker never freezes on a cold cache (all 10 symbols).
    zones = await asyncio.to_thread(compute_levels, daily, intraday, tol_pct=tol, min_touches=min_touches)
    _LEVEL_CACHE[symbol] = (now, zones)
    logger.info("Levels computed for %s: %d zones (daily=%d 1h=%d bars)", symbol, len(zones), len(daily), len(intraday))
    return zones
