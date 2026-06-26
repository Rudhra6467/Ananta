"""
Single-OWNER JWT auth gate (Phase 3.5).

Public visitors get read-only access (all GETs open); every mutating endpoint is
guarded by `require_owner` (HTTP 403 without a valid owner Bearer token), and
exchange secrets are redacted from GET /settings for non-owners.

Lean by design for a single owner: Bearer access token (12h), no refresh/reset
flow (rotate via .env), bcrypt-hashed password seeded idempotently from env,
basic brute-force lockout.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

JWT_ALG = "HS256"
ACCESS_TTL_HOURS = 12
MAX_FAILS = 5
LOCKOUT_MIN = 15

# Ephemeral fallback secret — generated once per process if JWT_SECRET is not set.
# Keeps the public read-only dashboard alive in misconfigured deployments instead of
# crashing the whole app; owner sessions simply won't survive a restart until the
# real JWT_SECRET env var is provided.
_EPHEMERAL_SECRET = uuid.uuid4().hex + uuid.uuid4().hex


def owner_configured() -> bool:
    """True only when both owner credentials are present in the environment."""
    return bool(os.environ.get("OWNER_EMAIL") and os.environ.get("OWNER_PASSWORD"))


# ---------- password hashing ----------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- JWT ----------
def _secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        logger.warning(
            "JWT_SECRET is not set — using a process-ephemeral secret. "
            "Owner sessions will reset on restart. Set JWT_SECRET in the deployment env."
        )
        return _EPHEMERAL_SECRET
    return secret


def create_access_token(email: str) -> str:
    payload = {
        "sub": email,
        "role": "owner",
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(hours=ACCESS_TTL_HOURS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALG)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("access_token")


def _valid_owner_payload(token: str) -> dict | None:
    try:
        p = jwt.decode(token, _secret(), algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        return None
    if p.get("type") == "access" and p.get("role") == "owner":
        return p
    return None


def is_owner_request(request: Request) -> bool:
    """Non-raising owner check (used for secret-redaction logic)."""
    token = _extract_token(request)
    return bool(token and _valid_owner_payload(token))


async def require_owner(request: Request) -> dict:
    """FastAPI dependency: 403 unless a valid owner token is present."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=403, detail="Owner authentication required.")
    try:
        jwt.decode(token, _secret(), algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid authentication token.")
    p = _valid_owner_payload(token)
    if not p:
        raise HTTPException(status_code=403, detail="Owner access required.")
    return p


# ---------- brute-force lockout ----------
async def check_lockout(db, ident: str) -> None:
    rec = await db.login_attempts.find_one({"_id": ident})
    if rec and rec.get("fails", 0) >= MAX_FAILS:
        until = rec.get("locked_until")
        if until and datetime.fromisoformat(until) > datetime.now(UTC):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")


async def _record_fail(db, ident: str) -> None:
    rec = await db.login_attempts.find_one({"_id": ident})
    fails = (rec.get("fails", 0) if rec else 0) + 1
    upd = {"fails": fails}
    if fails >= MAX_FAILS:
        upd["locked_until"] = (datetime.now(UTC) + timedelta(minutes=LOCKOUT_MIN)).isoformat()
    await db.login_attempts.update_one({"_id": ident}, {"$set": upd}, upsert=True)


async def _clear_fails(db, ident: str) -> None:
    await db.login_attempts.delete_one({"_id": ident})


# ---------- owner account ----------
async def seed_owner(db) -> None:
    """Idempotently create/update the single owner from env (bcrypt-hashed).

    No-op (with a warning) when owner credentials are absent, so the public
    read-only app still boots in a misconfigured deployment."""
    if not owner_configured():
        logger.warning(
            "OWNER_EMAIL/OWNER_PASSWORD not set — owner login disabled. "
            "Public read-only mode only. Set both in the deployment env to enable owner controls."
        )
        return
    email = os.environ["OWNER_EMAIL"].strip().lower()
    password = os.environ["OWNER_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": email,
            "password_hash": hash_password(password),
            "role": "owner",
            "created_at": datetime.now(UTC).isoformat(),
        })
        logger.info("Seeded owner account: %s", email)
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one(
            {"email": email}, {"$set": {"password_hash": hash_password(password)}},
        )
        logger.info("Owner password re-synced from env.")


async def authenticate(db, email: str, password: str, ident: str) -> str | None:
    """Returns an access token on success, None on bad credentials.
    Raises 429 if locked out. Records failures for brute-force protection."""
    if not owner_configured():
        return None
    await check_lockout(db, ident)
    email = (email or "").strip().lower()
    owner_email = os.environ["OWNER_EMAIL"].strip().lower()
    user = await db.users.find_one({"email": email})
    if email != owner_email or not user or not verify_password(password, user.get("password_hash", "")):
        await _record_fail(db, ident)
        return None
    await _clear_fails(db, ident)
    return create_access_token(owner_email)
