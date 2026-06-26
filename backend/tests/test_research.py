"""Tests for the Research Database (Phase 2 validation layer)."""
from __future__ import annotations

import pytest

from research import (
    classify_cf,
    confidence_tier,
    resolve_counterfactuals,
    summarize_research,
)


# ---------- tier classification ----------
def test_confidence_tier_bands():
    assert confidence_tier(0.92) == "EXECUTE"
    assert confidence_tier(0.80) == "EXECUTE"
    assert confidence_tier(0.79) == "SHADOW"
    assert confidence_tier(0.70) == "SHADOW"
    assert confidence_tier(0.69) == "LOG_ONLY"
    assert confidence_tier(0.50) == "LOG_ONLY"
    assert confidence_tier(0.49) == "IGNORE"
    assert confidence_tier(0.0) == "IGNORE"


def test_confidence_tier_custom_floor():
    # raising the execute floor shifts the shadow band with it
    assert confidence_tier(0.84, execute_floor=0.85) == "SHADOW"
    assert confidence_tier(0.85, execute_floor=0.85) == "EXECUTE"


# ---------- counterfactual classification ----------
def test_classify_cf_bands():
    assert classify_cf(5.0) == "MISSED_OPPORTUNITY"
    assert classify_cf(-5.0) == "CORRECT_REJECTION"
    assert classify_cf(0.3) == "NEUTRAL"
    assert classify_cf(None) is None
    # band edges
    assert classify_cf(1.5) == "MISSED_OPPORTUNITY"
    assert classify_cf(-1.5) == "CORRECT_REJECTION"


# ---------- summary aggregation ----------
def test_summarize_research_distribution_and_buckets():
    rows = [
        {"row_type": "SETUP", "macro_confidence": 0.82, "macro_bias": "BULLISH",
         "absolute_decision": "EXECUTE", "confidence_tier": "EXECUTE",
         "cf_ret_7d": 4.0, "cf_resolved_7d": True},
        {"row_type": "SETUP", "macro_confidence": 0.74, "macro_bias": "BULLISH",
         "absolute_decision": "REJECT", "confidence_tier": "SHADOW",
         "cf_ret_7d": 3.0, "cf_resolved_7d": True},
        {"row_type": "SETUP", "macro_confidence": 0.75, "macro_bias": "BULLISH",
         "absolute_decision": "HOLD", "confidence_tier": "SHADOW",
         "cf_ret_7d": -4.0, "cf_resolved_7d": True},
        {"row_type": "SETUP", "macro_confidence": 0.20, "macro_bias": "NEUTRAL",
         "absolute_decision": "HOLD", "confidence_tier": "IGNORE"},
    ]
    out = summarize_research(rows)
    assert out["total_setup_rows"] == 4
    assert out["decision_distribution"]["EXECUTE"] == 1
    assert out["decision_distribution"]["REJECT"] == 1
    assert out["decision_distribution"]["HOLD"] == 2
    assert out["tier_distribution"]["SHADOW"] == 2
    assert out["counterfactuals_resolved"]["7d"] == 3
    # near-miss: 2 bullish rejections/holds in 0.70-0.79 (0.74 + 0.75)
    nm = out["near_miss_0_70_0_79_bullish"]
    assert nm["count"] == 2
    assert nm["resolved_7d"] == 2
    assert nm["missed_opportunity"] == 1  # +3.0%
    assert nm["correct_rejection"] == 1   # -4.0%


def test_summarize_research_excludes_background_rows():
    rows = [
        {"row_type": "BACKGROUND", "macro_confidence": 0.6, "macro_bias": "NEUTRAL",
         "absolute_decision": "HOLD", "confidence_tier": "BACKGROUND"},
        {"row_type": "SETUP", "macro_confidence": 0.6, "macro_bias": "NEUTRAL",
         "absolute_decision": "HOLD", "confidence_tier": "LOG_ONLY"},
    ]
    out = summarize_research(rows)
    assert out["total_setup_rows"] == 1


def test_summarize_empty():
    out = summarize_research([])
    assert out["total_setup_rows"] == 0
    assert out["near_miss_0_70_0_79_bullish"]["count"] == 0


# ---------- counterfactual resolver (in-memory fake db) ----------
class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n):
        return self._docs[:n]


class _FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, q, projection=None):
        done_field = next((k for k in q if k.startswith("cf_resolved_")), None)
        cutoff = q.get("timestamp", {}).get("$lte")
        out = []
        for d in self.docs:
            if done_field and d.get(done_field):
                continue
            if cutoff and d["timestamp"] > cutoff:
                continue
            out.append(d)
        return _FakeCursor(out)

    async def update_one(self, q, update):
        for d in self.docs:
            if d["id"] == q["id"]:
                d.update(update["$set"])
                return


class _FakeDB:
    def __init__(self, docs):
        self.research_log = _FakeCollection(docs)


@pytest.mark.asyncio
async def test_resolve_counterfactuals_fills_returns():
    from datetime import UTC, datetime, timedelta
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    docs = [{
        "id": "r1", "symbol": "BTC/USD", "price": 100.0, "timestamp": old,
        "cf_resolved_24h": False, "cf_resolved_72h": False, "cf_resolved_7d": False,
    }]
    db = _FakeDB(docs)

    async def fake_price(_sym):
        return 110.0  # +10%

    resolved = await resolve_counterfactuals(db, fetch_price=fake_price)
    assert resolved == 3  # 24h + 72h + 7d all elapsed
    assert docs[0]["cf_ret_24h"] == 10.0
    assert docs[0]["cf_ret_7d"] == 10.0
    assert docs[0]["cf_resolved_7d"] is True
