"""Regression tests for the Strategy Import Pipeline (P2) — pure/deterministic parts
(format detection, validation guardrails, draft build, library projection). No LLM calls."""
from __future__ import annotations

import strategy_import as si

PINE = """//@version=5
strategy("EMA Cross", overlay=true)
fast = ta.ema(close, input.int(12))
slow = ta.ema(close, input.int(26))
if ta.crossover(fast, slow)
    strategy.entry("long", strategy.long)
"""

FREQ = """
from freqtrade.strategy import IStrategy
class MyStrat(IStrategy):
    timeframe = '1h'
    minimal_roi = {"0": 0.1}
    stoploss = -0.10
    def populate_indicators(self, dataframe, metadata):
        return dataframe
    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[(dataframe['rsi'] < 30), 'enter_long'] = 1
        return dataframe
    def populate_exit_trend(self, dataframe, metadata):
        return dataframe
"""

JESSE = """
from jesse.strategies import Strategy
class Golden(Strategy):
    def should_long(self): return self.rsi < 30
    def should_short(self): return False
    def go_long(self): self.buy = 1, self.price
    def update_position(self): pass
"""

JSON = '{"name":"My JSON Strat","entry":["rsi<30"],"exit":["rsi>70"],"timeframe":"4h"}'


def test_detect_pine():
    d = si.detect_format(PINE)
    assert d["best"] == "pine_script"
    assert d["scores"]["pine_script"] > d["scores"]["freqtrade"]


def test_detect_freqtrade():
    assert si.detect_format(FREQ)["best"] == "freqtrade"


def test_detect_jesse():
    assert si.detect_format(JESSE)["best"] == "jesse"


def test_detect_json():
    assert si.detect_format(JSON)["best"] == "json"


def test_validate_ready():
    ex = {"entry_rules": ["a"], "exit_rules": ["b"], "parameters": {"x": 1},
          "risk_management": {"stop_loss_pct": 5}, "direction": "long", "market_type": ["Crypto"]}
    v = si.validate_extraction(ex)
    assert v["status"] == "ready" and v["error_count"] == 0


def test_validate_blocks_no_entry():
    v = si.validate_extraction({"entry_rules": [], "exit_rules": ["x"]})
    assert v["status"] == "blocked" and v["error_count"] >= 1


def test_validate_warns_short():
    v = si.validate_extraction({"entry_rules": ["a"], "exit_rules": ["b"], "parameters": {"x": 1},
                                "risk_management": {"stop_loss_pct": 5}, "direction": "short"})
    assert v["warning_count"] >= 1
    assert any("long-only" in i["message"] for i in v["issues"])


def test_build_draft_shapes_library_fields():
    ex = {"name": "Foo", "category": "Momentum", "direction": "long", "timeframe": "4H",
          "entry_rules": ["e"], "exit_rules": ["x"], "parameters": {"p": 1},
          "risk_management": {"stop_loss_pct": 5}, "ai_health_score": 80, "ai_confidence": 75,
          "indicators": [{"name": "RSI", "params": {"period": 14}}],
          "conversion": {"confidence_score": 90, "notes": "ok", "warnings": ["w"]}}
    draft = si.build_draft(raw_source=PINE, source_format="pine_script",
                           detected=si.detect_format(PINE), extraction=ex)
    assert draft["imported"] is True and draft["internal"] is False
    assert draft["ai_grade"] == "B" and draft["rating"] == 4
    assert draft["conversion_confidence"] == 90
    assert draft["source_label"].startswith("Pine")
    assert draft["status"] == "draft"
    # library projection keeps the library-shaped fields + import provenance
    lib = si.to_library_doc(draft)
    for f in ("id", "name", "entry_rules", "ai_grade", "imported", "source_format"):
        assert f in lib
    assert "raw_source" not in lib


def test_unknown_category_defaults():
    draft = si.build_draft(raw_source="x", source_format="json", detected={"best": "json", "scores": {}},
                           extraction={"name": "Z", "category": "Nonsense", "entry_rules": ["a"]})
    assert draft["category"] == "Nonsense"  # stored, but validation flags as info
    v = si.validate_extraction({"entry_rules": ["a"], "exit_rules": ["b"], "parameters": {"p": 1},
                                "risk_management": {"s": 1}, "category": "Nonsense"})
    assert any("normalised" in i["message"] for i in v["issues"])
