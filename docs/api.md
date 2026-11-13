# Backend API, authentication, and security (Phase 5)

Code: `apps/api/app/` (`main.py`, `routers/`, `auth/`, `core/`, `repo/`, `services/`).
OpenAPI is served at `/api/docs` and `/api/openapi.json`. Tests: `apps/api/tests/api/`.
Run: `make migrate`, then `make api`. Run the database tests with `TEST_DATABASE_ADMIN_URL` set
(PostgreSQL with pgvector) and optionally `VALKEY_URL`.

## Structure

Routers (prefix `/api/v1`): auth, users and admin, tenants, suppliers, uploads, reviews, resolve,
events, companies, graph, alerts, rules, reports, sources, analytics, billing, platform, contact,
health, and `stream/alerts`. Errors are RFC 7807 problem documents with a request id. Lists use
signed keyset cursors. Validation errors never echo submitted values.

## Authentication

| Item | Implementation |
|---|---|
| Passwords | Argon2id (RFC 9106 low-memory profile), minimum 12 characters, zxcvbn score of 3 or more, common password list, no composition rules |
| Login protection | Per-IP and per-account rate limits, lockout from the fifth failure with doubling duration up to 60 minutes, identical error for unknown account, wrong password, lock, and inactive account, timing equalised with a dummy hash, audit entries for failures |
| MFA | TOTP with one step of drift and replay rejection, 10 recovery codes (80 bits each, stored as keyed hashes, single use). Mandatory for tenant admins and platform admins, and for everyone when the tenant sets `require_mfa`; sign-in returns `mfa_enrollment_required` until enrolled |
| Access token | EdDSA JWT, 10 minutes, in an httpOnly Secure SameSite=Strict cookie. The user's role and active state are read from the database on each request, and the session family must be live, so logout, deactivation, and role changes apply immediately |
| Refresh token | Opaque, stored as SHA-256, rotated on every use. Reuse of a used token revokes the whole session family. Idle timeout 8 hours and absolute lifetime 30 days (configurable) |
| CSRF | Double-submit cookie and `X-CSRF-Token` header on every state-changing cookie-authenticated request |
| Password reset | Single-use, 30 minute, hashed tokens; same response for existing and unknown accounts; reset revokes all sessions |
| API keys | `pk_<prefix>_<secret>`, secret stored hashed, shown once, scoped (never user or admin scopes), expiry, last-used tracking, per-key rate limit. Keys cannot use session-only endpoints |

## Authorization and tenant isolation

Permissions follow the matrix in the plan (`auth/permissions.py`) and are enforced by dependencies.
Tenant requests run `SET LOCAL ROLE app_user` with `app.tenant_id` set, so PostgreSQL row level
security (migration 0004) binds every query even if a handler forgets a filter. `app_user` reads
global tables only, cannot touch refresh tokens, MFA secrets, or reset tokens, and has insert/select
only on the audit log. Authentication, platform queue writes, and background jobs use the owner
connection. A platform administrator without `X-Tenant-Id` has cross-tenant read scope; with the
header (audited) the request behaves as that tenant.

The transaction of a tenant request commits before the response is sent (`Depends(..., scope="function")`).

## Audit log

Append-only (trigger) with a hash chain written under an advisory lock in its own transaction, so
security events persist even if the request fails. `GET /admin/audit/verify` recomputes the chain.
Sensitive keys are redacted before storage; logs are JSON with the same redaction.

## Other protections

Per-IP, per-user, per-key and per-account limits (in process, or Valkey for multiple instances),
body limits (1 MB, 10 MB for uploads) enforced on streamed bodies, upload row limit 10,000, UTF-8
and extension checks, `Idempotency-Key` on uploads, CSV formula neutralisation on exports, supplier
tax IDs and account numbers encrypted with pgcrypto, strict security headers, no CORS.

## Verification status

Verified: 193 automated tests including every role against every endpoint group, cross-tenant API
and SQL tests, RLS and privilege tests, token rotation and reuse, lockout, MFA replay, audit tamper
detection, Valkey rate limit and pub/sub, and a smoke run under uvicorn. Coverage of `app` is 92%.

Not done:
- **OWASP ZAP baseline scan**: needs the running stack in containers; not run. Trivy, Bandit, and
  gitleaks are also not run locally (only in CI definitions where present).
- **Load and latency numbers** are Phase 10.
- **PDF reports** are Phase 6: `POST /reports/*` records the request and returns `queued`.
- **Rate limit values, lock durations, and token lifetimes** are defaults, not tuned.
- Platform revenue endpoints are minimal (MRR by plan and a summary); Phase 7 builds the full set.
- Celery scheduling is not wired; `services/alerts.py` and the Phase 4 `recompute` are the functions
  a scheduled task will call.
- The tenant `retention_days` setting is stored, but no purge job exists yet.
- API endpoints for corrections, merge-duplicates, and newsletter signup belong to Phase 6 and 8.
