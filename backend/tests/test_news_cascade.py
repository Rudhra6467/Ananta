"""Iteration 3 tests - live news cascade (RSS aggregate → mock fallback).

Verifies:
  * GET /api/news/current shape, cache info, source label
  * 5-min TTL caching (back-to-back calls return identical summary)
  * POST /api/cycle/run/BTC propagates live news into reasoning.news_summary
  * Regression sanity: root / portfolio / settings / market.snapshots / risk.status
    / public.snapshot (sanitized) / report.reasoning.pdf (valid PDF magic).
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback: parse frontend/.env
    _env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    try:
        with open(_env) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"')
                    break
    except OSError:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

VALID_SOURCES_PREFIXES = ("rss-aggregate", "mock-fallback")


# ---------- news endpoint ----------
class TestNewsCurrent:
    def test_news_current_200_shape(self):
        r = requests.get(f"{API}/news/current", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "summary" in data and isinstance(data["summary"], str)
        assert "ts" in data and isinstance(data["ts"], str)
        assert "cache" in data and isinstance(data["cache"], dict)

    def test_news_summary_non_empty(self):
        r = requests.get(f"{API}/news/current", timeout=30)
        assert r.status_code == 200
        summary = r.json()["summary"]
        assert summary.strip(), "summary must be non-empty"
        # If live (non-mock), should be substantial real text.
        cache = r.json()["cache"]
        if not cache["source"].startswith("mock-fallback"):
            assert len(summary) > 50, f"live summary too short: {len(summary)} chars"

    def test_news_source_label_is_valid(self):
        r = requests.get(f"{API}/news/current", timeout=30)
        assert r.status_code == 200
        src = r.json()["cache"]["source"]
        assert any(src.startswith(p) for p in VALID_SOURCES_PREFIXES), (
            f"unexpected cache.source: {src!r}"
        )

    def test_news_cache_info_fields(self):
        r = requests.get(f"{API}/news/current", timeout=30)
        cache = r.json()["cache"]
        assert "rss_feeds" in cache
        assert isinstance(cache["rss_feeds"], list)
        # Must include CoinDesk and CoinTelegraph (case-insensitive contains)
        joined = " ".join(cache["rss_feeds"]).lower()
        assert "coindesk" in joined, cache["rss_feeds"]
        assert "cointelegraph" in joined, cache["rss_feeds"]

    def test_news_ttl_cache_identical(self):
        # First call may be a cache miss (slow ~1-3s if RSS); second must be fast and identical.
        r1 = requests.get(f"{API}/news/current", timeout=30)
        assert r1.status_code == 200
        s1 = r1.json()["summary"]
        time.sleep(0.5)
        r2 = requests.get(f"{API}/news/current", timeout=10)
        assert r2.status_code == 200
        s2 = r2.json()["summary"]
        assert s1 == s2, "TTL cache violated: summary changed between back-to-back calls"
        # age_seconds of 2nd call should be > 0 (cache hit)
        age2 = r2.json()["cache"].get("age_seconds")
        assert age2 is not None and age2 >= 0


# ---------- end-to-end propagation into reasoning ----------
class TestNewsPropagatesToReasoning:
    def test_cycle_run_btc_contains_news_summary(self):
        # Warm news cache so cycle uses same summary we just observed.
        r_news = requests.get(f"{API}/news/current", timeout=30)
        assert r_news.status_code == 200
        live_summary = r_news.json()["summary"]

        # Run an evaluation cycle for BTC (does live news + Gemini ~6-10s)
        r_cycle = requests.post(f"{API}/cycle/run/BTC", timeout=60)
        assert r_cycle.status_code == 200, r_cycle.text
        body = r_cycle.json()
        # The reasoning entry the loop wrote should expose the news summary field.
        # Tolerate either nested shape: directly on body, or under "reasoning"/"evaluation".
        ns = None
        for key in ("news_summary",):
            if key in body and isinstance(body[key], str):
                ns = body[key]
                break
        if ns is None:
            # Some implementations nest under e.g. body["reasoning"]
            for sub in body.values():
                if isinstance(sub, dict) and isinstance(sub.get("news_summary"), str):
                    ns = sub["news_summary"]
                    break
        # Fallback: query /api/reasoning?limit=5 - the just-written record should have it.
        if not ns:
            r_reason = requests.get(f"{API}/reasoning?limit=5", timeout=15)
            assert r_reason.status_code == 200
            items = r_reason.json().get("items", [])
            assert items, "no reasoning entries written after cycle run"
            # Find most recent BTC entry
            for it in items:
                if it.get("symbol", "").startswith("BTC") and it.get("news_summary"):
                    ns = it["news_summary"]
                    break
        assert ns, "reasoning entry lacks non-empty news_summary"
        assert ns.strip() == live_summary.strip(), (
            "reasoning.news_summary does not match live news summary"
        )

    def test_reasoning_recent_entries_have_news(self):
        r = requests.get(f"{API}/reasoning?limit=5", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert items, "no reasoning items found (run cycle first?)"
        # At least one of the 5 most-recent items must have a non-empty news_summary.
        with_news = [it for it in items if (it.get("news_summary") or "").strip()]
        assert with_news, "no recent reasoning entries carry a news_summary"


# ---------- regression sanity (per review_request) ----------
class TestRegression:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "running"

    def test_portfolio(self):
        r = requests.get(f"{API}/portfolio", timeout=15)
        assert r.status_code == 200
        body = r.json()
        for k in ("cash", "equity", "positions"):
            assert k in body

    def test_settings(self):
        r = requests.get(f"{API}/settings", timeout=10)
        assert r.status_code == 200
        # secrets must be masked
        body = r.json()
        for k in ("coinbase_api_secret", "kraken_api_secret"):
            if body.get(k):
                assert set(str(body[k])) <= {"•"}

    def test_market_snapshots(self):
        r = requests.get(f"{API}/market/snapshots", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "snapshots" in body and isinstance(body["snapshots"], list)

    def test_risk_status(self):
        r = requests.get(f"{API}/risk/status", timeout=15)
        assert r.status_code == 200
        assert "status" in r.json()

    def test_public_snapshot_sanitized(self):
        r = requests.get(f"{API}/public/snapshot", timeout=20)
        assert r.status_code == 200
        body = r.json()
        # public settings must NOT contain API key/secret fields
        s = body.get("settings", {})
        for k in (
            "coinbase_api_key", "coinbase_api_secret",
            "kraken_api_key", "kraken_api_secret",
        ):
            assert k not in s, f"sensitive field leaked: {k}"

    def test_report_reasoning_pdf(self):
        r = requests.get(f"{API}/report/reasoning.pdf", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content.startswith(b"%PDF-"), "missing PDF magic"
