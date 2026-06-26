# Auth Testing Playbook — Ananta.AI Owner Gate (Phase 3.5)

Single-owner JWT auth. Bearer token in `Authorization` header. Public GETs open;
mutations require owner token (403 otherwise); exchange secrets redacted for non-owners.

## Credentials (preview)
- Owner email: `owner@ananta.ai`
- Owner password: see `/app/memory/test_credentials.md`

## API tests (use external REACT_APP_BACKEND_URL or localhost:8001)
1. Login (success):
```
curl -X POST $URL/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"owner@ananta.ai","password":"<OWNER_PASSWORD>"}'
# -> { "token": "<jwt>", "email": "owner@ananta.ai", "role": "owner" }
```
2. Login (bad password) -> 401.
3. `GET /api/auth/me` with `Authorization: Bearer <jwt>` -> owner object. Without token -> 403.
4. Mutation WITHOUT token -> 403:
```
curl -X PUT $URL/api/settings -H "Content-Type: application/json" -d '{"min_confidence":0.8}'  # 403
```
5. Mutation WITH owner token -> 200.
6. `GET /api/settings` WITHOUT token -> kraken/coinbase api_key + secret show `••••`.
   WITH owner token -> real values returned.
7. Public GETs (`/api/portfolio`, `/api/market/snapshots`, `/api/research/*`) -> 200 without token.

## DB checks
```
mongosh -> use <DB_NAME>
db.users.find({role:"owner"})          # bcrypt hash starts with $2b$
```
