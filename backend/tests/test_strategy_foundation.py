"""Unit tests for the strategy foundation (registry + schema validation + inheritance)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy import get_schema, list_schemas, resolve_config, validate_params  # noqa: E402


def test_registry_has_builtins():
    keys = {s.key for s in list_schemas()}
    assert {"hunter", "squeeze", "continuation"} <= keys
    hunter = get_schema("hunter")
    assert hunter.version == "1.0.0"
    assert hunter.dna.confidence == 87
    assert any(p.id == "rsi_reset_min" for p in hunter.params)


def test_validate_params_ok_and_errors():
    schema = get_schema("hunter")
    ok, errs = validate_params(schema, {"rsi_reset_min": 28, "vcp_enabled": False})
    assert ok and not errs
    ok, errs = validate_params(schema, {"rsi_reset_min": 999, "nope": 1, "vcp_enabled": "yes"})
    assert not ok
    assert any("above max" in e for e in errs)
    assert any("unknown param" in e for e in errs)
    assert any("boolean" in e for e in errs)


def test_enum_validation():
    schema = get_schema("hunter")
    ok, _ = validate_params(schema, {"exit_method": "atr"})
    assert ok
    ok, errs = validate_params(schema, {"exit_method": "banana"})
    assert not ok and any("one of" in e for e in errs)


def test_inheritance_resolution():
    schema = get_schema("hunter")
    root = {"id": "root", "parent_config_id": None, "params": {"rsi_reset_min": 28, "target_profit": 3.0}}
    child = {"id": "child", "parent_config_id": "root", "params": {"normal_lot_usd": 120}}
    by_id = {"root": root, "child": child}
    resolved = resolve_config(child, by_id, schema)
    assert resolved["rsi_reset_min"] == 28        # from parent
    assert resolved["target_profit"] == 3.0       # from parent
    assert resolved["normal_lot_usd"] == 120       # from child override
    assert resolved["exit_method"] == "fixed"      # from schema default (untouched)


def test_inheritance_cycle_is_safe():
    schema = get_schema("squeeze")
    a = {"id": "a", "parent_config_id": "b", "params": {"normal_lot_usd": 50}}
    b = {"id": "b", "parent_config_id": "a", "params": {"normal_lot_usd": 60}}
    resolved = resolve_config(a, {"a": a, "b": b}, schema)  # must not infinite-loop
    assert "normal_lot_usd" in resolved


if __name__ == "__main__":
    test_registry_has_builtins()
    test_validate_params_ok_and_errors()
    test_enum_validation()
    test_inheritance_resolution()
    test_inheritance_cycle_is_safe()
    print("OK")
