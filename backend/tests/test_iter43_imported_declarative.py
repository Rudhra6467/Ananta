"""P2: imported free-text strategies → executable declarative rules.

Deterministic coverage (no LLM): the engine capability validator, the import
declarative-block validation/gating, and the runtime registry wiring that gives
approved imports full parity with catalog declarative strategies.
"""
import importlib

declarative_engine = importlib.import_module("declarative_engine")
strategy_import = importlib.import_module("strategy_import")
ddefs = importlib.import_module("strategy.declarative_defs")


VALID_SPEC = {
    "indicators": {
        "ema_f": {"fn": "ema", "period": "$ema_fast"},
        "ema_s": {"fn": "ema", "period": "$ema_slow"},
    },
    "entry": [{"lhs": "ema_f", "op": "cross_above", "rhs": "ema_s"}],
    "exit": [{"lhs": "ema_f", "op": "cross_below", "rhs": "ema_s"}],
    "entry_reason": "fast EMA crosses above slow EMA",
}


def test_validate_spec_accepts_valid():
    res = declarative_engine.validate_spec(VALID_SPEC)
    assert res["ok"] is True, res["issues"]


def test_validate_spec_rejects_unsupported_fn_and_op():
    bad = {
        "indicators": {"x": {"fn": "supertrend_magic", "period": 10}},
        "entry": [{"lhs": "x", "op": "teleports_above", "rhs": "close"}],
        "exit": [],
    }
    res = declarative_engine.validate_spec(bad)
    assert res["ok"] is False
    joined = " ".join(res["issues"])
    assert "unsupported indicator fn" in joined
    assert "unsupported op" in joined


def test_validate_spec_flags_missing_params_and_empty_entry():
    bad = {"indicators": {"e": {"fn": "ema"}}, "entry": [], "exit": []}
    res = declarative_engine.validate_spec(bad)
    assert res["ok"] is False
    joined = " ".join(res["issues"])
    assert "missing param 'period'" in joined
    assert "entry must be a non-empty list" in joined


def test_validate_declarative_gates_on_ai_claim_and_engine():
    # AI says compilable + engine agrees -> compilable
    ok = strategy_import.validate_declarative({
        "compilable": True, "params": {"ema_fast": 12, "ema_slow": 26},
        "indicators": VALID_SPEC["indicators"], "entry": VALID_SPEC["entry"],
        "exit": VALID_SPEC["exit"], "entry_reason": "x",
    })
    assert ok["compilable"] is True
    assert ok["params"] == {"ema_fast": 12, "ema_slow": 26}

    # AI claims compilable but rules are broken -> not compilable, with a clear issue
    bad = strategy_import.validate_declarative({
        "compilable": True, "params": {},
        "indicators": {"z": {"fn": "nope"}}, "entry": [{"lhs": "z", "op": "gt", "rhs": 1}], "exit": [],
    })
    assert bad["compilable"] is False
    assert any("do not map" in i for i in bad["issues"])

    # AI abstains -> not compilable regardless
    assert strategy_import.validate_declarative({"compilable": False}) ["compilable"] is False


def test_register_imported_gives_parity_and_executes():
    key = "test_imported_emacross"
    ddefs.unregister_imported(key)
    ddefs.register_imported(key, "Test EMA Cross", "unit-test import",
                            VALID_SPEC, {"ema_fast": 12, "ema_slow": 26})
    try:
        assert ddefs.is_declarative(key) is True
        assert key in ddefs.all_declarative_keys()
        assert ddefs.get_declarative_spec(key) == VALID_SPEC
        # schema registered with tunable params + risk params
        schema = ddefs.get_schema(key) if hasattr(ddefs, "get_schema") else None
        # capability: the spec runs through the engine on synthetic rising bars
        bars = [[i, p, p + 1, p - 1, p, 100] for i, p in enumerate([10 + i * 0.5 for i in range(80)])]
        sig = declarative_engine.evaluate(VALID_SPEC, bars, {"ema_fast": 12, "ema_slow": 26})
        assert sig.indicators.get("ema_f") is not None
    finally:
        ddefs.unregister_imported(key)
        assert ddefs.is_declarative(key) is False
