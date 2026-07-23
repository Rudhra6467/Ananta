"""Regression: 'Save without AI' (POST /library/import/direct) must never 500 on arbitrary
user-pasted JSON, and a JSON already in Ananta's declarative rule format must compile to an
EXECUTABLE strategy (declarable=True, entry rules present) — not a view-only blueprint.

Root cause of the production 500: build_draft assumed field types (name str, timeframes list,
declarative dict) and crashed on free-form JSON; the global exception handler then surfaced a
generic 'Internal server error'.
"""
from __future__ import annotations

import strategy_import as si

_DETECTED = {"best": "json", "scores": {}}


def _draft(ex, **kw):
    ex = {**ex, "ai_summary": "x", "conversion": {"confidence_score": 0}}
    return si.build_draft(raw_source="{}", source_format="json", detected=_DETECTED,
                          extraction=ex, name_override=kw.get("name"))


def test_build_draft_never_crashes_on_bad_types():
    for ex in [
        {"name": 123},                                   # numeric name
        {"name": "a", "timeframes": 5},                  # timeframes not a list
        {"name": "a", "timeframes": []},                 # empty timeframes
        {"name": "a", "declarative": [1, 2]},            # declarative as list
        {"name": "a", "declarative": "oops"},            # declarative as string
        {"name": "a", "conversion": "nope"},             # conversion wrong type
        {"description": "no name at all"},               # missing name
        {"name": "a", "entry": {"type": "breakout"}},    # free-form entry object (user's case)
    ]:
        d = _draft(ex)
        assert isinstance(d["name"], str) and d["name"]
        assert isinstance(d["timeframes"], list)
        assert d["declarable"] is False  # free-form / bad input is never wrongly executable


def test_declarative_json_compiles_to_executable():
    """A JSON in the engine's declarative format lifts into a compilable spec via the endpoint's
    normalization; here we validate the same declarative block build_draft consumes."""
    decl = {
        "compilable": True,
        "params": {"ema_fast": 9, "ema_slow": 21},
        "indicators": {"ema_fast": {"fn": "ema", "period": "$ema_fast"},
                       "ema_slow": {"fn": "ema", "period": "$ema_slow"}},
        "entry": [{"lhs": "ema_fast", "op": "cross_above", "rhs": "ema_slow"}],
        "exit": [{"lhs": "ema_fast", "op": "cross_below", "rhs": "ema_slow"}],
        "entry_reason": "fast EMA crossed slow EMA",
    }
    d = _draft({"name": "JSON EMA", "declarative": decl,
                "entry_rules": ["ema_fast cross above ema_slow"]})
    assert d["declarable"] is True
    assert d["declarative_spec"]["entry"] == decl["entry"]
    assert (d.get("validation") or {}).get("error_count", 0) == 0
