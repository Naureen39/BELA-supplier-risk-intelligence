# Deployment and packaging

## What is in the stack (`compose.yaml`)

| Service | Image | Role | Limits | Notes |
|---|---|---|---|---|
| `caddy` | `caddy:2-alpine` | TLS, compression, routes `/api/*` to the API (no buffering, so live alerts stream) and everything else to the web app | 0.5 CPU, 256 MB | Only service with public ports (80, 443) |
| `web` | built from `infra/docker/web.Dockerfile` | Next.js | 1 CPU, 768 MB | Read-only file system; page cache in a volume |
| `api` | built from `infra/docker/api.Dockerfile` | FastAPI, 2 workers by default (`API_WORKERS`) | 2 CPU, 2 GB | Read-only file system, non-root (uid 10001), reports in a volume |
| `migrate` | the API image | `alembic upgrade head`, runs once before the API starts | | |
| `db` | `pgvector/pgvector:pg17` | PostgreSQL with pgvector, pgcrypto, pg_trgm | 2 CPU, 2 GB | Data in the `pgdata` volume |
| `jobs` | the API image | once a day: retention purge and revenue view refresh (a loop, not cron; it restarts with the stack) | 0.5 CPU, 512 MB | Harvesting news (`infra/cron/gdelt.cron`) is not scheduled here |
| `valkey` | `valkey/valkey:8-alpine` | rate limits, cache, live alert fan-out | 0.5 CPU, 384 MB | No persistence (nothing in it must survive) |
| `mailpit`, `seed` | profile `demo` only | mail catcher, one-shot demo seeder | | |

Every service has a restart policy (`unless-stopped`; one-shot jobs `no`), JSON log rotation (10 MB, 5 files),
`no-new-privileges`, and a health check; start order follows health. The database and Valkey sit on an internal network
with no route out. The API and web app are on an internal network that Caddy reaches; **the API therefore cannot make
outbound connections** (webhooks and external SMTP will fail and go to the dead letter queue). To allow them, attach the
API to a network with egress, and keep the webhook safety checks on.

## Configuration

`make env` (run by `make demo`) writes `.env` with random `POSTGRES_PASSWORD`, `DATA_KEY`, `CURSOR_SECRET`, and an
Ed25519 `JWT_PRIVATE_KEY_PEM`, and never overwrites an existing file. Also settable: `SITE_ADDRESS` (default `localhost`; a
real domain gets a public certificate from Let's Encrypt automatically and needs ports 80 and 443 reachable),
`ACME_EMAIL`, `API_WORKERS`, `DB_POOL_MAX`, `RATE_LIMIT_*`, `DEMO_MODE`, `SMTP_HOST`, and `DEMO_VIEWER_PASSWORD`.
Back up `.env`: without `DATA_KEY` an encrypted backup cannot be read (`docs/runbook.md`).

## Running

```
make demo          # demo: Mailpit, demo banner, seeded data, passwords printed once
docker compose up -d --build   # the same stack without demo data (set DEMO_MODE=false in .env)
```

For a non-demo install create the first administrator yourself (there is no seeded account): insert a `tenants` row and a
`users` row with an Argon2id hash from `app.auth.passwords.PasswordService`, or adapt `infra/demo/seed_demo.py`.

## A public read-only demo

Seed as usual, set `DEMO_VIEWER_PASSWORD` in `.env` to the printed viewer password, and rebuild the web image
(`docker compose --profile demo up -d --build web`): the login page then shows the viewer address and password. The viewer
role holds only the `view` permission (no uploads, rule changes, reports, or administration), enforced by the API. Do not
publish any other account's password, and keep rate limits on.

## Checkpoints

`python infra/models/fetch_checkpoints.py` downloads trained checkpoints listed in `infra/models/checkpoints.json` and
refuses any file whose SHA-256 differs from the manifest. The manifest is empty because no checkpoint has been trained
(`docs/model_card.md`). The platform runs without them, with reduced confidence on affected results.

## What has and has not been run

- Run and verified (without containers, on macOS with Python 3.14 and PostgreSQL 17): the migrations, the demo seed through
  the real API (about 250 suppliers resolved and scored), the API guide examples, the web build with demo mode, the login
  page with the demo panel (axe clean), screenshot capture, the backup drill, and the tests in `test_phase11.py` (compose
  structure, proxy settings, checkpoint verification, seed behavior).
- **Not run:** `docker compose up`, the Docker image builds, Caddy's TLS, the container health checks, and the `make demo`
  time. The files were checked as YAML and by those tests. Expect small fixes on the first real run (a missing system
  library in the API image or a Next.js file the web image does not copy are the likeliest). The CI `packaging` job
  builds both images and validates the compose file so the first push shows this.
- **Python versions:** the images use Python 3.13; the tests ran on 3.14 locally and CI uses 3.11.
- **Dependencies are only partly locked.** `requirements/api.txt` pins the direct runtime dependencies. Transitive
  versions are resolved at build time, so two builds can differ. Generate a full lock (`uv pip compile` or `pip-compile`)
  before relying on repeatable builds.
- **Scanning the images** (Trivy image scan) and a ZAP baseline against the running stack are still to do; the compose
  stack makes both possible.
