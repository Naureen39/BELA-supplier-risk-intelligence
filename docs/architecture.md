# Architecture overview

## Components

```
                     browser
                        |  HTTPS
                  +-----v-----+
                  |   Caddy   |  TLS, compression, no buffering of /api streams
                  +--+-----+--+
          /api/*     |     |   everything else
        +------------+     +------------+
        |                               |
  +-----v------+                  +-----v------+
  |  API       |  /api/v1         |  Web       |  Next.js: marketing site and the
  |  FastAPI   |<-----------------+  (Next.js) |  product application under /app
  +--+----+----+   (dev proxy)    +------------+
     |    |
     |    +--------> Valkey: rate limit counters, response cache, live alert fan-out
     v
  PostgreSQL 17: relational data, pgvector, pg_trgm, pgcrypto, row level security
     ^
     |  (optional, not required for the demo)
  Model services: BELA mention linker, BLINK re-ranker, local language model
```

In the compose stack only Caddy publishes ports. The database and Valkey are on an internal network.

## The data path

1. **Sources** (`data/`): regulator records (EPA ECHO, OSHA, NHTSA, CPSC, openFDA), SEC filings and GLEIF and Wikidata for
   ownership, GDELT for news discovery. Each source is registered with its terms in `data/manifest.yaml`.
2. **Knowledge base** (`apps/api/app/kb`): a canonical company table with aliases, identifiers, facilities, and ownership
   edges, built with deterministic rules; near-duplicates are never merged automatically, they become review items.
3. **Resolution** (`apps/api/app/resolution`): a record is normalized, candidates are retrieved (trigram and vector search),
   scored by a Fellegi-Sunter model with a logistic combiner and calibration, and routed to `accepted`, `review`, or `nil`
   using versioned thresholds. Optional neural re-ranking and language-model adjudication add to the evidence when their
   services are up; when they are not, the result is flagged `degraded` ("reduced confidence") and can never be accepted
   automatically.
4. **Events** (`apps/api/app/events`): regulator and news records become typed events with a severity, linked to companies
   through the same resolution step. Each link stores its method, score, route, and candidates.
5. **Scoring and alerts** (`apps/api/app/services/monitoring.py`): for each supplier, events reaching it through ownership
   (itself, parents, subsidiaries, siblings) are combined as `100 x (1 - product(1 - impact))`, where an impact multiplies
   severity, recency decay, link confidence, relationship weight, and source reliability. Rules turn changes into alerts.
6. **Product** (`apps/web`, `apps/api/app/routers`): supplier lists and profiles, a review queue, alerts with live delivery
   (server-sent events), a corporate-family explorer, analytics, PDF reports, and administration.

## Tenancy and security

- Every tenant table has row level security. Requests run `SET LOCAL ROLE app_user` and set the tenant in the transaction,
  so the database enforces isolation even if a query forgets a condition. System jobs use the owner connection.
- Sessions are EdDSA tokens in httpOnly strict cookies with CSRF double submit; API keys are hashed, scoped, and expiring;
  TOTP is mandatory for administrators. Details: `docs/api.md`, `docs/security_review.md`.
- The audit log is append-only and hash-chained; `GET /admin/audit/verify` and the backup drill check the chain.
- The business (revenue) analytics are platform-level views over synthetic subscription data (`docs/metrics.md`).

## Failure behavior

Retries with backoff and a dead letter queue for uploads, webhooks, and email; a database outage answers 503 with
`Retry-After`; a missing model service degrades resolution instead of failing it. See `docs/runbook.md`.

## Where things run

| Process | Command | Scale |
|---|---|---|
| API | `uvicorn --factory app.main:create_app` | several workers; all must share the secrets and `VALKEY_URL` |
| Web | `next start` | stateless; its page cache is a volume |
| Jobs | `make metrics-refresh`, `python -m app.services.retention`, `infra/cron/*.cron` | commands, scheduled by cron (no scheduler service yet) |
