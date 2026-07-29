"""
Multi-tenant auth + provisioning for Ananta.

Two auth transports coexist on the shared backend:
  * Owner / demo  -> existing email+password JWT (auth.py).  tenant = "owner".
  * Google users  -> Emergent-managed OAuth session_token (cookie on web,
    Bearer on mobile).  tenant = the user's own user_id (isolated book).

`resolve_principal` unifies both into a single principal dict:
  {user_id, email, role, tenant_id, name?, picture?}

New Google users are provisioned lazily with their OWN isolated paper book +
settings the first time they hit a tenant-scoped endpoint.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx

import auth
from tenant_ctx import OWNER_TENANT, tenant_doc_id

logger = logging.getLogger(__name__)

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
SESSION_TTL_DAYS = 7


def _bearer_and_cookie(request) -> tuple[str | None, str | None]:
    bearer = None
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        bearer = header[7:].strip() or None
    cookie = request.cookies.get("session_token")
    return bearer, cookie


def _session_expired(sess: dict) -> bool:
    exp = sess.get("expires_at")
    if not exp:
        return False
    if isinstance(exp, str):
        try:
            exp = datetime.fromisoformat(exp)
        except Exception:
            return True
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    return exp < datetime.now(UTC)


def _principal_from_user(user: dict) -> dict:
    role = user.get("role", "user")
    tenant_id = OWNER_TENANT if role in ("owner", "demo") else user["user_id"]
    return {
        "user_id": user["user_id"],
        "email": user.get("email"),
        "role": role,
        "tenant_id": tenant_id,
        "name": user.get("name"),
        "picture": user.get("picture"),
    }


async def _principal_from_session(db, token: str) -> dict | None:
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess or _session_expired(sess):
        return None
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        return None
    return _principal_from_user(user)


async def resolve_principal(request, db) -> dict | None:
    """Return the authenticated principal (owner/demo JWT OR Google session),
    or None for an anonymous public visitor."""
    bearer, cookie = _bearer_and_cookie(request)

    # 1. Owner / demo JWT (email+password).
    if bearer:
        payload = auth._valid_owner_payload(bearer)
        if payload:
            return {
                "user_id": payload.get("sub"),
                "email": payload.get("sub"),
                "role": payload.get("role", "owner"),
                "tenant_id": OWNER_TENANT,
            }
        # 2. Bearer is a Google session_token (mobile transport).
        p = await _principal_from_session(db, bearer)
        if p:
            return p

    # 3. Google session cookie (web transport).
    if cookie:
        p = await _principal_from_session(db, cookie)
        if p:
            return p

    return None


# ---------- Google (Emergent OAuth) session exchange ----------
async def exchange_session_id(db, session_id: str) -> dict:
    """Exchange an Emergent session_id for the user profile + a persistent
    session_token. Upserts the user by email and stores the session. Returns the
    principal + session_token."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": session_id})
    if resp.status_code != 200:
        raise ValueError(f"session-data exchange failed ({resp.status_code})")
    data = resp.json()
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise ValueError("session-data returned no email")

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        # keep role/tenant stable; refresh profile fields
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": data.get("name"), "picture": data.get("picture"),
                      "last_login_at": datetime.now(UTC).isoformat()}},
        )
        user = {**existing, "name": data.get("name"), "picture": data.get("picture")}
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id,
            "id": user_id,
            "email": email,
            "name": data.get("name"),
            "picture": data.get("picture"),
            "role": "user",
            "tenant_id": user_id,
            "auth_provider": "google",
            "created_at": datetime.now(UTC).isoformat(),
            "last_login_at": datetime.now(UTC).isoformat(),
        }
        await db.users.insert_one({**user})
        logger.info("Provisioned new Google user %s (%s)", email, user_id)

    session_token = data.get("session_token") or uuid.uuid4().hex
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
    })

    principal = _principal_from_user(user)
    await ensure_provisioned(db, principal["tenant_id"])
    return {"principal": principal, "session_token": session_token}


async def logout_session(db, token: str | None) -> None:
    if token:
        await db.user_sessions.delete_one({"session_token": token})


# ---------- per-tenant book provisioning ----------
_provisioned_cache: set[str] = set()


async def ensure_provisioned(db, tenant_id: str) -> None:
    """Idempotently create an isolated paper book + settings for a new tenant."""
    if tenant_id == OWNER_TENANT or tenant_id in _provisioned_cache:
        return
    from models import Portfolio, RiskSettings  # noqa: PLC0415

    pid = tenant_doc_id(tenant_id)
    if not await db.portfolio.find_one({"id": pid}, {"_id": 0, "id": 1}):
        p = Portfolio()
        p.id = pid
        await db.portfolio.insert_one(p.model_dump())
    if not await db.settings.find_one({"id": pid}, {"_id": 0, "id": 1}):
        import strategy_profiles as sprofiles  # noqa: PLC0415
        s = RiskSettings()
        s.id = pid
        s.trading_mode = "PAPER"  # users are PAPER-only; LIVE is house/owner
        # Seed the validated Recommended Matrix so a fresh account ships with sensible
        # per-strategy regime + exit defaults (only proven strategies enabled).
        s.profile_overrides = sprofiles.apply_matrix({})
        s.recommended_matrix_version = sprofiles.MATRIX_VERSION
        await db.settings.insert_one(s.model_dump())
    _provisioned_cache.add(tenant_id)
