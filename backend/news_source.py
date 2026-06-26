"""
Live macro news source for Layer 4 (Gemini macro reasoning).

Pulls real crypto headlines from a set of free, open RSS feeds. No API keys
required, no paid tiers.

Cascade:
  1. Parallel-fetch all configured RSS feeds (CoinDesk, CoinTelegraph,
     Bitcoin Magazine, Decrypt). Merge by `pubDate`, take top 5 freshest,
     strip HTML, attribute by source.
  2. Deterministic mock summaries (rotates per UTC minute). Only fires when
     every RSS feed has failed - keeps the trading loop alive offline.

HTML tags in RSS <description> bodies are stripped before the text reaches
the LLM. Results are cached for NEWS_CACHE_TTL_SECONDS (5 min) to avoid
hammering remote endpoints from the 90s background trading loop.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Free open RSS feeds. All verified accessible without auth.
RSS_FEEDS: list[tuple[str, str]] = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("BitcoinMagazine", "https://bitcoinmagazine.com/feed"),
    ("Decrypt", "https://decrypt.co/feed"),
]

NEWS_HTTP_TIMEOUT = 8
NEWS_CACHE_TTL_SECONDS = 300  # 5 min - macro context doesn't change tick-by-tick

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# ---------- HTML / XML helpers ----------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_HTML_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&#39;": "'", "&apos;": "'", "&nbsp;": " ", "&hellip;": "…",
    "&ndash;": "-", "&mdash;": "-", "&rsquo;": "'", "&lsquo;": "'",
    "&ldquo;": '"', "&rdquo;": '"',
}


def _strip_html(s: str) -> str:
    """Strip HTML tags + decode common entities + collapse whitespace."""
    if not s:
        return ""
    s = s.replace("<![CDATA[", "").replace("]]>", "")
    s = _TAG_RE.sub(" ", s)
    for ent, ch in _HTML_ENTITIES.items():
        s = s.replace(ent, ch)
    s = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
    return _WS_RE.sub(" ", s).strip()


def _parse_pubdate(s: str) -> datetime | None:
    """Parse RFC 822 (RSS standard) or ISO 8601 dates."""
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------- mock fallback ----------
_MOCK_SUMMARIES = [
    "US CPI prints slightly cooler than expected. Risk assets bid across the board, with BTC ETF inflows accelerating. Funding rates remain modest; on-chain accumulation by long-term holders steady.",
    "Hawkish Fed minutes released. Treasury yields jumping. Crypto majors seeing leveraged longs flushed, but spot bids holding near key support. Sentiment cautious-to-mixed.",
    "Major exchange reports unusual outflows. No confirmed exploit. Twitter sentiment turning anxious; implied volatility ticking higher. Capital rotation into stablecoins.",
    "ETH staking yields steady; L2 activity up week-over-week. Macro environment quiet ahead of NFP. Spot order books showing balanced two-way flow with no clear directional bias.",
    "Spot ETF approvals expected for additional altcoins. Pre-positioning visible on Coinbase. Funding remains neutral; orderbook depth has improved on Kraken.",
    "Geopolitical headlines weigh on risk sentiment. Equities red; DXY firmer. Crypto correlated to risk-off move; BTC dominance rising as alts underperform.",
    "Stablecoin market caps expanding for 4th consecutive week. Net exchange BTC balances continue to decline. Long-term holder supply at multi-year highs.",
    "Mixed macro signals: strong retail sales offset by softer manufacturing PMI. Crypto chops in a range; volatility compresses; breakout direction unclear.",
    "Whale wallet accumulates 1,200 BTC across two exchanges over 24h. Spot premium emerging on Coinbase vs Binance. Cautious bullish microstructure read.",
    "Funding rates flip negative on perpetuals while spot holds firm. Often a contrarian bullish signal historically but with low conviction in current regime.",
]


def _mock_summary(salt: str = "") -> str:
    bucket = datetime.now(UTC).strftime("%Y%m%d%H%M")
    h = hashlib.sha256(f"{bucket}-{salt}".encode()).hexdigest()
    idx = int(h, 16) % len(_MOCK_SUMMARIES)
    return _MOCK_SUMMARIES[idx]


# ---------- RSS fetch ----------
def _parse_rss_items(xml_bytes: bytes, source_name: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("RSS parse failed (%s): %s", source_name, e)
        return []
    items = root.findall(".//item")
    out: list[dict] = []
    for it in items:
        title = _strip_html(it.findtext("title") or "")
        if not title:
            continue
        desc = _strip_html(it.findtext("description") or "")
        pub_raw = it.findtext("pubDate") or ""
        pub_dt = _parse_pubdate(pub_raw)
        out.append({
            "title": title,
            "description": desc,
            "pub_date": pub_dt,
            "source": source_name,
        })
    return out


def _fetch_rss_one_sync(source_name: str, url: str) -> list[dict]:
    headers = {"User-Agent": _BROWSER_UA, "Accept": "application/rss+xml, application/xml, text/xml"}
    try:
        r = requests.get(url, headers=headers, timeout=NEWS_HTTP_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("RSS fetch failed (%s): %s", source_name, e)
        return []
    if r.status_code != 200:
        logger.warning("RSS fetch %s returned HTTP %s", source_name, r.status_code)
        return []
    return _parse_rss_items(r.content, source_name)


async def _fetch_rss_aggregate() -> list[dict] | None:
    """Fetch all RSS feeds in parallel, merge by date, return top 5 freshest."""
    results = await asyncio.gather(
        *(asyncio.to_thread(_fetch_rss_one_sync, name, url) for name, url in RSS_FEEDS),
        return_exceptions=True,
    )
    merged: list[dict] = []
    succeeded = 0
    for (name, _), r in zip(RSS_FEEDS, results, strict=True):
        if isinstance(r, list) and r:
            merged.extend(r)
            succeeded += 1
        else:
            logger.warning("RSS feed %s contributed 0 items this cycle", name)
    if succeeded < len(RSS_FEEDS):
        logger.warning("RSS aggregate degraded: %d/%d feeds returned items", succeeded, len(RSS_FEEDS))
    if not merged:
        return None
    # newest first - items with unparseable pub_date sort to the END
    very_old = datetime.fromtimestamp(0, tz=UTC)
    merged.sort(key=lambda x: x.get("pub_date") or very_old, reverse=True)
    return merged[:5]


# ---------- formatting ----------
def _article_to_line(a: dict) -> str:
    title = (a.get("title") or "").strip()
    if not title:
        return ""
    desc = _strip_html((a.get("description") or "").strip())
    source = (a.get("source") or "").strip()
    line = title
    if desc and desc.lower() != title.lower():
        line = f"{title} — {desc[:240]}"
    if source:
        line = f"{line} ({source})"
    return line


def _articles_to_summary(articles: list[dict]) -> str:
    lines = [ln for a in articles[:5] if (ln := _article_to_line(a))]
    return " | ".join(lines)


# ---------- public API ----------
_cache: dict[str, Any] = {"ts": 0.0, "text": "", "source": "uninitialized"}


async def get_current_summary(salt: str = "") -> str:
    """Return a macro summary string for Gemini.

    Cascade:
      1. cached value if fresh
      2. CoinDesk + CoinTelegraph + BitcoinMagazine + Decrypt RSS aggregate
         (top 5 freshest)
      3. deterministic mock fallback (only when all RSS feeds fail)
    """
    now = time.time()
    if _cache["text"] and now - _cache["ts"] < NEWS_CACHE_TTL_SECONDS:
        return _cache["text"]

    rss = await _fetch_rss_aggregate()
    if rss:
        text = _articles_to_summary(rss)
        if text:
            sources = sorted({a["source"] for a in rss})
            label = f"rss-aggregate ({'+'.join(sources)})"
            _cache.update({"ts": now, "text": text, "source": label})
            logger.info("News refreshed from RSS (%d articles, %s)", len(rss), label)
            return text

    fallback = _mock_summary(salt=salt)
    _cache.update({"ts": now, "text": fallback, "source": "mock-fallback"})
    logger.warning("News fell back to mock - every RSS feed was unreachable")
    return fallback


def get_cache_info() -> dict:
    """Diagnostic: which source did we use, and how stale is it?"""
    age = time.time() - _cache["ts"] if _cache["ts"] else None
    return {
        "source": _cache["source"],
        "age_seconds": round(age, 1) if age is not None else None,
        "rss_feeds": [name for name, _ in RSS_FEEDS],
    }
