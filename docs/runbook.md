# Runbook

How to run, check, back up, restore, and repair the platform. Everything here was exercised on a development machine
with PostgreSQL 17 and Valkey; items that could not be exercised are marked **not tested**. The container stack
(`compose.yaml`, Phase 11) was written without Docker available and has not been started, so it is marked **not run**
where it matters; the commands below also work with processes started directly.

## Components

| Component | Process | Depends on | Health |
|---|---|---|---|
| API | `uvicorn --factory app.main:create_app` | PostgreSQL, Valkey (optional) | `GET /api/v1/health` (alive), `GET /api/v1/health/ready` (database reachable) |
| Web | `next start` (proxies `/api` to the API) | the API | the home page answers 200 |
| PostgreSQL 16 or newer with pgvector, pgcrypto, pg_trgm | database | disk | `pg_isready` |
| Valkey | rate limit counters, response cache, live alert delivery | none | `valkey-cli ping` |
| Jobs (commands, not a scheduler yet) | `make metrics-refresh`, `python -m app.services.retention`, `infra/cron/*.cron` | database | exit status |

Without `VALKEY_URL` the API falls back to in-process rate limits, cache, and live alert delivery. That is correct for one
process and wrong for several: with more than one worker, live alerts reach only clients connected to the same worker.
Set `VALKEY_URL` whenever the API runs with more than one process.

## Configuration

Set through environment variables (see `.env.example`). The ones that matter operationally:

| Variable | Meaning |
|---|---|
| `DATABASE_URL`, `VALKEY_URL` | connections |
| `JWT_PRIVATE_KEY_PEM`, `DATA_KEY`, `CURSOR_SECRET` | secrets. **Every API process must use the same values.** With `ALLOW_EPHEMERAL_SECRETS=true` each process invents its own, which is only acceptable for a single development process. |
| `DB_POOL_MIN`, `DB_POOL_MAX` | connection pool per process (default 2 and 10). Keep `workers x DB_POOL_MAX` below PostgreSQL's `max_connections`. |
| `RATE_LIMIT_IP`, `RATE_LIMIT_USER`, `RATE_LIMIT_KEY`, `RATE_LIMIT_LOGIN_IP`, `RATE_LIMIT_LOGIN_ACCOUNT` | `requests/seconds`, for example `600/60`. Defaults are 600/60, 300/60, 600/60, 20/60, 10/900. |
| `COOKIE_SECURE`, `TRUST_PROXY_HEADERS` | keep `COOKIE_SECURE=true` behind TLS. Set `TRUST_PROXY_HEADERS=true` only when a trusted reverse proxy sets `X-Forwarded-For`, or per-address limits see the proxy's address. |
| `SMTP_HOST`, `SMTP_PORT`, `WEB_BASE_URL` | mail and the links inside it |
| `REPORT_DIR` | where generated PDF reports are stored (local disk today) |
| `EVAL_METRICS_PATH` | the evaluation file the analytics and the methodology page read |

## Deploying a version

1. Take a backup (below).
2. `cd apps/api && alembic upgrade head`. Migrations are forward only in practice: a `downgrade` exists for each, but only
   the 0006 downgrade is exercised by a test, so restoring the backup is the safe way back.
3. Restart the API processes, then rebuild and restart the web app (`npm run build`, `next start`).
4. Check `/api/v1/health/ready`, sign in, and open the overview.

## Backup and restore

**What to protect:** the PostgreSQL database (everything the product stores) and `REPORT_DIR` (generated PDFs; they can be
regenerated). Secrets live in the environment, not in the database: keep `DATA_KEY` safe, because without it encrypted
supplier identifiers and multi-factor secrets in a backup cannot be read.

**Take a backup**

```
pg_dump --format=custom --no-owner --file=backup.dump "$DATABASE_URL"
```

**Restore into a new database** (also the drill)

```
infra/backup/drill.sh "$SOURCE_DATABASE_URL" "$ADMIN_URL" restore_drill
```

The script dumps the source, creates a new database, restores into it, and compares the copy with the source: row counts of
20 tables, the schema version, the number of row level security policies and indexes, populated materialized views, a
checksum over supplier names and statuses, the tail of the audit log, whether the application role exists and row level
security is on, and a full verification of the audit hash chain on the restored copy. It exits non-zero if anything differs.

On a new server, create the application role before restoring, because roles belong to the cluster, not the database
(the script does this): `CREATE ROLE app_user NOLOGIN;`

**Drill result (2026-11-18, local PostgreSQL 17):** a 20,000 company, 60,000 event, 23,000 supplier database
(12.8 MB dump) dumped in 1.0 seconds and restored in 51 seconds. All checks passed, including the audit chain. The restore
time is dominated by rebuilding the indexes, the vector index among them, so it grows with data volume, not with dump
size. This is one run on one machine; repeat it on the production hardware and record the time. **Not tested:** restoring
from a base backup with point in time recovery, restoring across major versions, restoring `REPORT_DIR`.

**Suggested policy (not enforced by the code):** a nightly logical backup kept for 14 days, plus continuous archiving if
the recovery point objective is shorter than a day. State the objectives you commit to once they are measured on real
hardware; this repository does not promise any.

## Routine jobs

| Job | Command | When |
|---|---|---|
| Refresh revenue views | `make metrics-refresh` | nightly |
| Purge expired data | `PYTHONPATH=apps/api python -m app.services.retention` (add `--dry-run` first) | nightly (`infra/cron/retention.cron`) |
| Harvest news | `infra/cron/gdelt.cron` | every 3 hours |
| Rescore suppliers and raise alerts | `POST /api/v1/monitoring/recompute` (manager) or `recompute_all` | after new events load |

The retention job deletes, per tenant and after `retention_days`: alerts with their history and deliveries, superseded
risk scores (the newest score of each supplier stays), decided reviews, closed corrections, and reports (rows and files
inside `REPORT_DIR` only). Globally it removes expired credentials and dead letters resolved more than 90 days ago. It never
touches the audit log, suppliers, uploads, or public event records.

## Failures and what to do

**Failed background work (dead letters).** Uploads, webhooks, and email that still fail after their retries are kept in the
dead letter queue. A platform administrator lists them with `GET /api/v1/platform/dead-letters` and retries or discards one
with `POST /api/v1/platform/dead-letters/{id}` (`{"action": "retry"}` or `"discard"`). Retrying an upload continues with the
rows that are still pending. Retrying a webhook repeats the safety checks. A rising count of open items means something
downstream is failing: check the error column first.

**Database down or restarting.** The API answers 503 with `Retry-After: 5` and no internal detail, and recovers by itself
when the database returns. `GET /health` stays 200 and `GET /health/ready` fails, so route traffic by readiness.

**Valkey down.** The cache is skipped (reads fall through to the database). The rate limiter and live alert delivery use
the same server: check their behavior before relying on this in production (**not tested**).

**A model service (BELA, BLINK, or the language model) down.** Resolution continues with retrieval and Splink scoring. The
result is flagged `degraded`, a note says "reduced confidence", the route cannot be an automatic accept, and the supplier page
shows a "Reduced confidence" notice. After the service returns, rerun the affected suppliers or review them.

**Rate limit complaints.** The 429 response carries `Retry-After`. Raise the matching `RATE_LIMIT_*` value rather than turning
limits off. Keys have their own limit, so one noisy integration does not block people.

**Slow queries.** Enable `pg_stat_statements`, run a load, and `python infra/perf/top_queries.py "$DATABASE_URL"`. The report
lists the 20 slowest queries with their generic plans and flags sequential scans. See `docs/perf.md` for what it found.

**Suspected tampering.** `GET /api/v1/admin/audit/verify` (tenant administrator) or `app.core.audit.verify_chain` reports the
first entry whose hash does not match.

**Rotating secrets.** Replacing `JWT_PRIVATE_KEY_PEM` or `CURSOR_SECRET` signs everyone out and invalidates open page
cursors; there is no overlap period for the old key. Replacing `DATA_KEY` makes existing encrypted values unreadable: there is
no re-encryption tool (**not built**). Plan a migration before rotating it.

## Containers (`compose.yaml`, see `docs/deploy.md`)

Start: `docker compose up -d --build` (or `make demo`). Stop: `docker compose down` (add `-v` only to delete the data).
Look at state: `docker compose ps` (health is shown), `docker compose logs -f api`. Logs rotate at 10 MB times 5 files per
service. Migrations run in the `migrate` service before the API starts, so a deployment is: take a backup, pull or
rebuild, `docker compose up -d --build`. Backup and restore commands run against the `db` container:
`docker compose exec db pg_dump -U provenance --format=custom provenance > backup.dump`. The restore drill script needs a
reachable PostgreSQL; point it at the published port or run it from a container on the `data` network. **Not tested.**
TLS certificates live in the `caddy_data` volume: keep it, or Caddy asks for new certificates (rate limited) on a rebuild.

## What is not covered

- Log shipping and central log storage (containers write JSON logs to the host's Docker log files only).
- Monitoring and alerting: the application exposes health endpoints and structured logs with request identifiers; there are no
  dashboards or alert rules for operators yet.
- High availability and failover: none.
- Capacity planning beyond `docs/perf.md`.
