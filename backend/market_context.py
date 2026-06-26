"""
Sector grounding-data feeds for the adaptive Gemini prompts.

Two lean, read-only, server-cached sources (per integration playbook):
  - DefiLlama (https://api.llama.fi, KEYLESS): protocol TVL + 30d trend, per-chain TVL.
  - FRED (https://api.stlouisfed.org/fred, FREE API KEY): latest macro observations.

Both use `requests` in a thread (matching news_source.py) + in-memory TTL caches
(DefiLlama 10 min, FRED 6 h) so external calls stay minimal. FRED degrades GRACEFULLY
when FRED_API_KEY is absent — the PAXG prompt then honestly states "macro data unavailable"
rather than letting Gemini hallucinate fundamentals (poisoned-dataset guardrail).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timedelta

import requests

from asset_profiles import asset_class, chain_name, protocol_slug

logger = logging.getLogger(__name__)

LLAMA_BASE = "https://api.llama.fi"
FRED_BASE = "https://api.stlouisfed.org/fred"
HTTP_TIMEOUT = 8

DEFI_TTL = 600       # 10 min
MACRO_TTL = 21600    # 6 h

# FRED macro series that drive gold (PAXG): inflation, rates, real yield proxy, USD.
FRED_SERIES = {
    "CPIAUCSL": "CPI (index)",
    "FEDFUNDS": "Fed Funds Rate %",
    "DGS10": "10Y Treasury %",
    "T10YIE": "10Y breakeven inflation %",
    "DTWEXBGS": "Broad USD index",
}

# in-memory caches: key -> (expiry_epoch, value)
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    return None


def _cache_set(key: str, value, ttl: int):
    _cache[key] = (time.time() + ttl, value)


# ---------- DefiLlama (sync) ----------
def _fetch_chain_tvl_sync(chain: str) -> float | None:
    key = f"chain:{chain.lower()}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(f"{LLAMA_BASE}/v2/chains", timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
        for c in r.json():
            if str(c.get("name", "")).lower() == chain.lower():
                tvl = float(c.get("tvl", 0.0))
                _cache_set(key, tvl, DEFI_TTL)
                return tvl
    except Exception as e:
        logger.warning("DefiLlama chain TVL fetch failed (%s): %s", chain, e)
    return None


def _fetch_protocol_tvl_sync(slug: str) -> dict | None:
    """Returns {current_tvl_usd, change_30d_pct} or None."""
    key = f"protocol:{slug}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(f"{LLAMA_BASE}/protocol/{slug}", timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
        series = r.json().get("tvl", []) or []
        if not series:
            return None
        current = float(series[-1].get("totalLiquidityUSD", 0.0))
        cutoff = (datetime.now(UTC) - timedelta(days=30)).timestamp()
        past = next((float(p.get("totalLiquidityUSD", 0.0)) for p in series
                     if p.get("date", 0) >= cutoff), None)
        change_30d = round((current - past) / past * 100.0, 2) if past else None
        out = {"current_tvl_usd": current, "change_30d_pct": change_30d}
        _cache_set(key, out, DEFI_TTL)
        return out
    except Exception as e:
        logger.warning("DefiLlama protocol TVL fetch failed (%s): %s", slug, e)
    return None


# ---------- FRED (sync) ----------
def _fetch_macro_sync() -> dict | None:
    """Latest observation for each FRED series. None if no API key configured."""
    key = "macro:snapshot"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        return None  # graceful degradation — caller states "macro data unavailable"
    snapshot: dict[str, dict] = {}
    for sid, label in FRED_SERIES.items():
        try:
            r = requests.get(
                f"{FRED_BASE}/series/observations",
                params={"series_id": sid, "api_key": api_key, "file_type": "json",
                        "limit": 1, "sort_order": "desc"},
                timeout=HTTP_TIMEOUT,
            )
            if r.status_code != 200:
                continue
            obs = r.json().get("observations", [])
            if obs:
                snapshot[sid] = {"label": label, "date": obs[0].get("date"), "value": obs[0].get("value")}
        except Exception as e:
            logger.warning("FRED fetch failed (%s): %s", sid, e)
    if snapshot:
        _cache_set(key, snapshot, MACRO_TTL)
        return snapshot
    return None


# ---------- public async API ----------
def _format_l1(chain: str | None, tvl: float | None) -> str:
    if chain and tvl:
        return f"On-chain context (DefiLlama): {chain} chain TVL ${tvl/1e9:.2f}B."
    return "On-chain context: unavailable this cycle."


def _format_defi(slug: str | None, data: dict | None) -> str:
    if data and data.get("current_tvl_usd"):
        chg = data.get("change_30d_pct")
        chg_s = f", 30d trend {chg:+.1f}%" if chg is not None else ""
        return f"Protocol data (DefiLlama, {slug}): TVL ${data['current_tvl_usd']/1e9:.2f}B{chg_s}."
    return "Protocol TVL data: unavailable this cycle."


def _format_macro(snapshot: dict | None) -> str:
    if not snapshot:
        return ("Macro data: UNAVAILABLE (FRED key not configured). "
                "Do NOT invent inflation/rate figures — reason qualitatively or stay NEUTRAL.")
    parts = [f"{v['label']}={v['value']}" for v in snapshot.values() if v.get("value") not in (None, ".")]
    return "Macro context (FRED, latest): " + "; ".join(parts) + "."


async def get_sector_context(symbol: str) -> dict:
    """Returns {asset_class, prompt_block, data} for the adaptive Gemini prompt.

    Network calls run in a thread and are cached; mostly free on repeat cycles.
    """
    cls = asset_class(symbol)
    try:
        if cls == "L1":
            chain = chain_name(symbol)
            tvl = await asyncio.to_thread(_fetch_chain_tvl_sync, chain) if chain else None
            return {"asset_class": cls, "prompt_block": _format_l1(chain, tvl),
                    "data": {"chain": chain, "chain_tvl_usd": tvl}}
        if cls == "DEFI":
            slug = protocol_slug(symbol)
            data = await asyncio.to_thread(_fetch_protocol_tvl_sync, slug) if slug else None
            return {"asset_class": cls, "prompt_block": _format_defi(slug, data),
                    "data": data or {}}
        if cls == "METAL":
            snap = await asyncio.to_thread(_fetch_macro_sync)
            return {"asset_class": cls, "prompt_block": _format_macro(snap),
                    "data": snap or {}}
    except Exception as e:
        logger.warning("get_sector_context failed for %s: %s", symbol, e)
    return {"asset_class": cls, "prompt_block": "Sector data unavailable.", "data": {}}
