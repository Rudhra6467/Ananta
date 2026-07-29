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


def create_access_token(email: str, role: str = "owner") -> str:
    payload = {
        "sub": email,
        "role": role,
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(hours=ACCESS_TTL_HOURS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALG)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("access_token")


# Roles that get full app (owner-level) access. `demo` is the permanent App-Review
# account — same privileges as owner for now (single shared engine); kept as a
# distinct role so a future multi-user migration can scope it without a rewrite.
PRIVILEGED_ROLES = {"owner", "demo"}


def _valid_owner_payload(token: str) -> dict | None:
    try:
        p = jwt.decode(token, _secret(), algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        return None
    if p.get("type") == "access" and p.get("role") in PRIVILEGED_ROLES:
        return p
    return None


def is_owner_request(request: Request) -> bool:
    """Non-raising owner check (used for secret-redaction logic)."""
    token = _extract_token(request)
    return bool(token and _valid_owner_payload(token))


async def require_owner(request: Request) -> dict:
    """FastAPI dependency for owner-only routes.

    Status semantics (so the frontend can react correctly):
    - 403 when NO token is present (public read-only visitor) or the token is valid
      but lacks the owner role — a legitimate app state, no re-login prompt.
    - 401 when a token IS present but is EXPIRED or INVALID/tampered — the owner
      session died; the frontend clears it and prompts a fresh login.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=403, detail="Owner authentication required.")
    try:
        jwt.decode(token, _secret(), algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")
    p = _valid_owner_payload(token)
    if not p:
        raise HTTPException(status_code=403, detail="Owner access required.")
    return p


# ---------- demo / App-Review account ----------
def demo_configured() -> bool:
    return bool(os.environ.get("DEMO_EMAIL") and os.environ.get("DEMO_PASSWORD"))


async def seed_demo(db) -> None:
    """Idempotently seed the permanent demo/App-Review account (role='demo').

    No-op when DEMO_EMAIL/DEMO_PASSWORD are absent."""
    if not demo_configured():
        return
    email = os.environ["DEMO_EMAIL"].strip().lower()
    password = os.environ["DEMO_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": email,
            "password_hash": hash_password(password),
            "role": "demo",
            "created_at": datetime.now(UTC).isoformat(),
        })
        logger.info("Seeded demo account: %s", email)
    else:
        upd = {"role": "demo"}
        if not verify_password(password, existing.get("password_hash", "")):
            upd["password_hash"] = hash_password(password)
        await db.users.update_one({"email": email}, {"$set": upd})

    # Populate a realistic demo book ONCE so the App-Review account lands on a
    # live-looking dashboard. Idempotent + safe: never clobbers a book that has
    # already accrued real trading activity.
    try:
        if await db.trades.count_documents({}) == 0:
            import demo_seed  # noqa: PLC0415
            out = await demo_seed.seed_demo_history(db)
            logger.info("Seeded demo history: %s", out)
    except Exception:  # noqa: BLE001
        logger.exception("Demo history seed skipped")


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
    """Idempotently create the single owner from env (bcrypt-hashed).

    Env is the bootstrap source of truth for a FRESH deployment. Once the owner
    edits their credentials IN-APP (`credentials_customized=True`), env NEVER
    overrides them again — so in-app email/password changes survive restarts and
    redeploys. Looks the owner up by ROLE (not env email) so a changed email does
    not spawn a duplicate owner doc.

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
    existing = await db.users.find_one({"role": "owner"})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": email,
            "password_hash": hash_password(password),
            "role": "owner",
            "display_name": None,
            "avatar": None,
            "credentials_customized": False,
            "created_at": datetime.now(UTC).isoformat(),
        })
        logger.info("Seeded owner account: %s", email)
        return
    if existing.get("credentials_customized"):
        return  # owner changed creds in-app — env must not override.
    upd = {}
    if existing.get("email") != email:
        upd["email"] = email
    if not verify_password(password, existing.get("password_hash", "")):
        upd["password_hash"] = hash_password(password)
    if upd:
        await db.users.update_one({"_id": existing["_id"]}, {"$set": upd})
        logger.info("Owner credentials re-synced from env.")


async def authenticate(db, email: str, password: str, ident: str) -> str | None:
    """Returns an access token on success, None on bad credentials.
    Raises 429 if locked out. Records failures for brute-force protection.

    Table-driven: any seeded user with a privileged role (owner/demo) can log in.
    Only seeded accounts exist in db.users today (no self-registration), so this
    is safe and leaves a clean seam for a future multi-user migration."""
    await check_lockout(db, ident)
    email = (email or "").strip().lower()
    user = await db.users.find_one({"email": email})
    role = (user or {}).get("role")
    if not user or role not in PRIVILEGED_ROLES or not verify_password(password, user.get("password_hash", "")):
        await _record_fail(db, ident)
        return None
    await _clear_fails(db, ident)
    return create_access_token(email, role)
