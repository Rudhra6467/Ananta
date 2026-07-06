"""
Ananta Platform — strategy foundation (Phase 1).

Three decoupled layers, designed for the destination (marketplace / optimizer / copy-trading)
even though we build incrementally:

    Strategy  ->  Parameter Schema  ->  Configuration  -> (Validation -> Execution -> Perf DB -> AI)

- Schema     = a strategy's self-description (params: type/range/default/grid/visibility/group).
               Static + VERSIONED (hunter@1.0.0). Never overwritten.
- Config     = a SPARSE set of overrides against a schema (one backtest / bot / marketplace listing).
               Tenant-aware, supports inheritance (parent_config_id) so you never duplicate 100 params.
- Strategy   = pure logic (registered in the REGISTRY); knows nothing about tenants/exchanges/storage.

This module is intentionally storage-agnostic: it deals in plain dicts + pydantic models so the
same code path serves the API, the optimizer, and (later) user-uploaded marketplace strategies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Parameter Schema primitives
# --------------------------------------------------------------------------- #
class ParamType(str, Enum):
    FLOAT = "float"
    INT = "int"
    PERCENT = "percent"
    BOOL = "bool"
    ENUM = "enum"


class Visibility(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    PROFESSIONAL = "professional"


class ParamGroup(str, Enum):
    ENTRY = "Entry"
    FILTERS = "Filters"
    RISK = "Risk"
    EXIT = "Exit"
    TIME = "Time"


class ParamSpec(BaseModel):
    """One tunable knob. This SINGLE object drives the Research Lab form, the optimizer
    search space (grid/min/max), Beginner/Pro UI adaptivity (visibility) and marketplace validation."""
    id: str
    label: str
    type: ParamType
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    grid: list[Any] = Field(default_factory=list)     # discrete values the optimizer sweeps
    options: list[Any] = Field(default_factory=list)  # allowed values for ENUM
    group: ParamGroup = ParamGroup.ENTRY
    visibility: Visibility = Visibility.INTERMEDIATE
    unit: str | None = None
    help: str = ""
    # conditional visibility, e.g. {"param": "exit_method", "equals": "atr"}
    depends_on: dict | None = None
    # true when this id maps 1:1 to a live RiskSettings field (engine already consumes it)
    engine_backed: bool = True


class StrategyDNA(BaseModel):
    """Self-describing metadata so the marketplace, optimizer and onboarding wizard can
    reason about a strategy with no extra code."""
    purpose: str
    works_best: str
    avoid: str
    risk: str = "Medium"          # Low | Medium | High
    holding: str = ""             # e.g. "2-10 days"
    preferred_coins: list[str] = Field(default_factory=list)
    confidence: int = 0           # 0..100 self-reported baseline confidence
    tags: list[str] = Field(default_factory=list)


class StrategySchema(BaseModel):
    key: str
    version: str
    name: str
    description: str = ""
    dna: StrategyDNA
    params: list[ParamSpec] = Field(default_factory=list)

    def defaults(self) -> dict:
        return {p.id: p.default for p in self.params}

    def by_id(self) -> dict[str, ParamSpec]:
        return {p.id: p for p in self.params}


# --------------------------------------------------------------------------- #
# Configuration model (persisted; tenant-aware + inheritable + versioned)
# --------------------------------------------------------------------------- #
class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=new_id)
    tenant_id: str = "owner"                 # every row is tenant-scoped from day one
    strategy_key: str
    strategy_version: str
    name: str
    params: dict = Field(default_factory=dict)   # SPARSE overrides only (inheritance-friendly)
    parent_config_id: str | None = None          # inheritance chain
    origin: str = "user"                          # builtin | user | marketplace | optimizer
    rating: dict | None = None                    # institutional score (Phase 3): stars/PF/dd/confidence/...
    validation_status: str = "unvalidated"        # unvalidated | passed | failed (Phase 3 promotion gate)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# --------------------------------------------------------------------------- #
# Registry (versioned)
# --------------------------------------------------------------------------- #
REGISTRY: dict[str, StrategySchema] = {}   # "key@version" -> schema
_LATEST: dict[str, str] = {}               # key -> latest registered version


def register(schema: StrategySchema) -> None:
    REGISTRY[f"{schema.key}@{schema.version}"] = schema
    _LATEST[schema.key] = schema.version   # register versions in ascending order → last wins


def get_schema(key: str, version: str | None = None) -> StrategySchema | None:
    if version:
        return REGISTRY.get(f"{key}@{version}")
    v = _LATEST.get(key)
    return REGISTRY.get(f"{key}@{v}") if v else None


def list_schemas() -> list[StrategySchema]:
    """Latest version of every registered strategy."""
    return [s for k in _LATEST if (s := get_schema(k))]


# --------------------------------------------------------------------------- #
# Validation + inheritance resolution
# --------------------------------------------------------------------------- #
def validate_params(schema: StrategySchema, params: dict) -> tuple[bool, list[str]]:
    """Structural validation of a sparse override dict against its schema."""
    errors: list[str] = []
    by_id = schema.by_id()
    for k, v in (params or {}).items():
        spec = by_id.get(k)
        if spec is None:
            errors.append(f"unknown param '{k}'")
            continue
        t = spec.type
        if t in (ParamType.FLOAT, ParamType.PERCENT):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                errors.append(f"'{k}' must be a number")
                continue
            if spec.min is not None and v < spec.min:
                errors.append(f"'{k}' below min {spec.min}")
            if spec.max is not None and v > spec.max:
                errors.append(f"'{k}' above max {spec.max}")
        elif t == ParamType.INT:
            if isinstance(v, bool) or not isinstance(v, int):
                errors.append(f"'{k}' must be an integer")
                continue
            if spec.min is not None and v < spec.min:
                errors.append(f"'{k}' below min {spec.min}")
            if spec.max is not None and v > spec.max:
                errors.append(f"'{k}' above max {spec.max}")
        elif t == ParamType.BOOL:
            if not isinstance(v, bool):
                errors.append(f"'{k}' must be a boolean")
        elif t == ParamType.ENUM:
            if v not in spec.options:
                errors.append(f"'{k}' must be one of {spec.options}")
    return (len(errors) == 0, errors)


def resolve_config(config: dict, by_id: dict[str, dict], schema: StrategySchema | None) -> dict:
    """Flatten a config into a full param set: schema defaults <- parent chain (root→leaf) <- self.
    Cycle-safe. `by_id` maps config_id → config dict (same tenant)."""
    merged: dict = dict(schema.defaults()) if schema else {}
    chain: list[dict] = []
    seen: set[str] = set()
    cur: dict | None = config
    while cur is not None and cur.get("id") not in seen:
        seen.add(cur["id"])
        chain.append(cur)
        pid = cur.get("parent_config_id")
        cur = by_id.get(pid) if pid else None
    for c in reversed(chain):  # root first, leaf last (leaf wins)
        merged.update(c.get("params") or {})
    return merged
