"""
Multi-tenant request context (lightweight, zero heavy deps).

A ContextVar carries the ACTIVE tenant for the current request or engine
iteration. The low-level persistence helpers (load/save portfolio + settings,
trade inserts, cooldowns) read this so per-user data isolation happens at the
I/O layer with minimal churn in endpoint bodies.

Default is OWNER_TENANT ("owner") so every legacy code path (and the background
house engine) behaves EXACTLY as before unless a tenant is explicitly set.

Doc-id scheme (backward compatible):
  * owner  -> id "singleton"     (preserves the existing single-owner book)
  * user X -> id "tenant_<X>"
"""
from __future__ import annotations

from contextvars import ContextVar

OWNER_TENANT = "owner"

current_tenant: ContextVar[str] = ContextVar("current_tenant", default=OWNER_TENANT)


def get_tenant() -> str:
    return current_tenant.get()


def tenant_doc_id(tenant_id: str | None = None) -> str:
    """Portfolio / settings singleton doc id for a tenant."""
    t = tenant_id or current_tenant.get()
    return "singleton" if t == OWNER_TENANT else f"tenant_{t}"


def tenant_trade_filter(tenant_id: str | None = None) -> dict:
    """Mongo filter for the tenant's rows in a shared collection (trades /
    pending_orders). For the owner, legacy rows with no tenant_id (or null) are
    included — `{"$in": [..., None]}` matches missing fields in MongoDB."""
    t = tenant_id or current_tenant.get()
    if t == OWNER_TENANT:
        return {"tenant_id": {"$in": [OWNER_TENANT, None]}}
    return {"tenant_id": t}


def cooldown_id(symbol: str, tenant_id: str | None = None) -> str:
    t = tenant_id or current_tenant.get()
    return f"{t}:{symbol}"
