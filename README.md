# Provenance Risk: supplier risk intelligence

A platform that links public regulator records and news to the companies in a supplier list, follows ownership from
facility to parent, and scores each supplier from the linked records. Every score shows its evidence, uncertain matches
go to a person, and every result is a lead for human review, not a statement of fault.

> **Status: a complete build on synthetic data, not a production service.** The matching pipeline, API, web application,
> monitoring, reports, and revenue analytics are built and tested. The demo uses fictional companies and generated
> events. The neural linkers (BELA, BLINK) and the local language model are integrated through interfaces but have not been
> trained or run, so the demo resolves suppliers with retrieval and probabilistic scoring only. There is no gold
> evaluation set; published precision figures are labeled synthetic. See "What is and is not verified" below.

## Quick start: the demo

Needs Docker with the compose plugin (v2.23 or newer), `openssl`, and `make`. About 3 GB of disk for the images.

```
git clone https://github.com/Naureen39/BELA-supplier-risk-intelligence.git
cd BELA-supplier-risk-intelligence
make demo
```

`make demo` writes a `.env` with fresh random secrets, builds the images, starts PostgreSQL, Valkey, the API, the web
application, and Caddy (TLS), runs the migrations, seeds the demo, and **prints the six demo account passwords once**.
Then open <https://localhost> (Caddy signs the local certificate with its own authority: accept the browser warning or run
`docker compose exec caddy caddy trust`). Password reset and invitation emails are caught by Mailpit at
<http://localhost:8025>.

| Account | Role | What it can do |
|---|---|---|
| `viewer@demo.example` | viewer | read-only (the role to use for a public demo) |
| `analyst@demo.example` | analyst | upload, review matches, act on alerts |
| `manager@demo.example` | manager | also alert rules, analytics, reports |
| `admin@demo.example` | tenant admin | users, API keys, risk settings, audit log (sets up MFA at first sign-in) |
| `finance@demo.example` | finance analyst | revenue and billing analytics |
| `platform@demo.example` | platform admin | tenants and the platform review queue (sets up MFA at first sign-in) |

Passwords are generated per install and only their Argon2id hashes are stored. If you lose them: `make demo-reset`
(wipes the demo database and seeds again). Stop with `make demo-down`. To walk through every page, follow
[docs/walkthrough.md](docs/walkthrough.md).

**Not yet measured:** the plan's target is a seeded environment from a clean clone in under 20 minutes. The container
files were written on a machine without Docker, so the full `make demo` run, and therefore its time, has not been
observed. The seed itself (migrations excluded) runs in a few seconds, and every step was run separately without
containers. The CI `packaging` job builds both images. See [docs/deploy.md](docs/deploy.md).

## Quick start without Docker (development)

Needs Python 3.11 or newer, Node 22 or newer, PostgreSQL 16 or newer with the `pgvector`, `pgcrypto`, and `pg_trgm`
extensions, and optionally Valkey or Redis.

```
make setup && make web-install
createdb provenance
export DATABASE_URL=postgresql://localhost/provenance COOKIE_SECURE=false ALLOW_EPHEMERAL_SECRETS=true \
       PYTHONPATH=apps/api:.
make migrate
.venv/bin/python infra/demo/seed_demo.py --database-url $DATABASE_URL    # prints the account passwords once
make api                                                                 # http://127.0.0.1:8000/api/docs
make web-dev                                                             # http://127.0.0.1:3000
```

To also run the supplier upload through the real pipeline, start the API first and add
`--api-url http://127.0.0.1:8000 --web-url http://127.0.0.1:3000` to the seed command (leave the database unseeded:
it refuses a database that already has users).

## What is in the repository

| Path | Contents |
|---|---|
| `apps/api` | FastAPI service, Alembic migrations (raw SQL, PostgreSQL), resolution engine, event pipeline, alerts, reports, analytics |
| `apps/web` | Next.js marketing site and product application, Playwright and Vitest tests |
| `services` | Optional model services (BELA mention linker, BLINK re-ranker, language model runner) |
| `data` | Source downloaders, the source registry (`manifest.yaml`), demo data generators |
| `training` | Training data and model fitting |
| `infra` | Container files, Caddy configuration, demo seed, backup drill, load tests, cron entries, license report |
| `docs` | Documentation (index below) |
| `compose.yaml` | The production-style stack |

## Documentation

| Document | For |
|---|---|
| [docs/architecture.md](docs/architecture.md) | How the pieces fit together |
| [docs/api_guide.md](docs/api_guide.md) and [docs/api.md](docs/api.md) | Calling the API (curl, Python, JavaScript), authentication and security design |
| [docs/data_guide.md](docs/data_guide.md) | Data sources, what is loaded, how to rebuild |
| [docs/model_card.md](docs/model_card.md) and [docs/eval/report.md](docs/eval/report.md) | Models, training data, evaluation method and results |
| [docs/runbook.md](docs/runbook.md) and [docs/deploy.md](docs/deploy.md) | Operating, backing up, restoring, deploying |
| [docs/security_review.md](docs/security_review.md) | Security review against the specification |
| [docs/licensing.md](docs/licensing.md) | Data, model, font, and dependency licenses |
| [docs/perf.md](docs/perf.md), [docs/quality_review.md](docs/quality_review.md) | Measurements and quality findings |
| [docs/walkthrough.md](docs/walkthrough.md) | Product walkthrough script |
| `docs/resolution.md`, `docs/events.md`, `docs/workflows.md`, `docs/metrics.md`, `docs/app.md`, `docs/web.md` | Per-subsystem notes |

## Tests and checks

```
make test        # backend (needs TEST_DATABASE_ADMIN_URL for the database tests)
make lint        # ruff, mypy --strict, no em dashes
make web-check   # prettier, eslint, tsc, vitest
```

End-to-end browser tests: see [docs/app.md](docs/app.md). Screenshots of the site: `make screenshots` (output in
`docs/screenshots/`).

## What is and is not verified

Verified by automated tests or measurements in this repository: authentication, authorization, and tenant isolation;
the matching, scoring, alerting, and reporting logic; the web application in Chrome, Firefox, and WebKit; accessibility
checks with axe; API load tests on one machine; backup and restore of a database.

Not verified: the neural linkers and language model (not trained or run); accuracy on real supplier data (no gold set);
the container images and the full `make demo` run (no Docker on the build machine; CI builds them); screen reader use;
a penetration test or ZAP baseline; real-device browsers. Details are in the review documents above.

## License and data terms

Code license: not yet chosen. All rights reserved by the author until a license file is added; see
[docs/licensing.md](docs/licensing.md) for the data, model, and dependency licenses that constrain redistribution.
The project builds on the open-source BELA and BLINK releases and is not affiliated with their authors.
