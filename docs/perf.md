# Performance (Phase 10)

Measured on 2026-11-18. Everything below comes from synthetic data on one development machine, so read the figures as
"how the code behaves", not as capacity planning for production.

## Setup

| | |
|---|---|
| Machine | MacBook Pro, 15 cores, 24 GB memory. The load generator, the API, PostgreSQL, and Valkey all ran on it, so they competed for the same cores. |
| Software | PostgreSQL 17 with pgvector, Valkey, Python 3.14, uvicorn, Locust 2.47 |
| Data (`infra/perf/seed_perf.py`) | 20,000 fictional companies (15 percent with a parent), 8,030 facilities, 60,000 events with 60,000 accepted links and 36,000 link candidates, one tenant with 3,000 resolved suppliers (23,000 after the upload test), 187 demo tenants of business data |
| API | `infra/perf/run_api.sh`: rate limits raised (`RATE_LIMIT_KEY=10000000/60`), pool of 20 connections per process, 1 or 4 workers |
| Authentication | one API key with the view, review, and rules scopes. The login limiter is not part of these tests. |
| Reproduce | `PYTHONPATH=.:apps/api python infra/perf/seed_perf.py ADMIN_URL`, `infra/perf/run_api.sh DB VALKEY 4`, then `API_KEY=... locust -f infra/perf/locustfile.py --headless -u 50 ...` |

## Read load: 50 concurrent users

The mix (`infra/perf/locustfile.py`) is the supplier list (weight 6), supplier profile (5), score breakdown (3), events (3),
alerts (2), portfolio dashboard (2), quality dashboard (1), graph neighbors (1), and company search (1). All requests go through
real authentication and row level security.

**Realistic pace** (0.5 to 2 seconds between a user's requests; 90 seconds; 4 API workers), final code:

| Endpoint | Requests | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|
| `GET /suppliers?limit=50` | 857 | 6 | 9 | 14 |
| `GET /suppliers/{id}/profile` | 715 | 8 | 11 | 19 |
| `GET /suppliers/{id}/risk` | 427 | 5 | 7 | 11 |
| `GET /events?limit=50` | 445 | 6 | 9 | 11 |
| `GET /alerts?limit=50` | 293 | 6 | 9 | 13 |
| `GET /analytics/portfolio` | 303 | 7 | 10 | 200 |
| `GET /analytics/quality` | 153 | 6 | 8 | 55 |
| `GET /graph/neighbors` (depth 2) | 163 | 6 | 8 | 25 |
| `GET /companies/search` | 136 | 12 | 17 | 19 |
| **All** | **3,492** | **7** | **11** | **18** |

No request failed. The 99th percentile of the dashboards is the cache miss: the first request for a window runs the queries
(about 180 to 220 ms for the portfolio dashboard, 40 to 55 ms for quality, 28 ms for the revenue KPIs, measured cold), and
the next minute is served from the cache.

**Stress** (no pause between requests, 50 users, 60 seconds):

| Workers | Requests per second | p50 ms | p95 ms | p99 ms | Failures |
|---|---|---|---|---|---|
| 1 (earlier code) | 565 | 85 | 110 | 120 | 0 of 33,353 |
| 4 (final code) | 1,420 | 32 | 52 | 62 | 0 of 83,897 |

One worker is limited by Python executing one request at a time; four workers scaled to about 2.5 times the throughput on a
machine that was also running the load generator. Full per-endpoint tables are in `docs/perf/locust-*.csv`.

## Findings and fixes

| # | Finding | Evidence | Fix | Result |
|---|---|---|---|---|
| 1 | **Rescoring was quadratic.** Every supplier was tested against every event cluster. | 100 suppliers took 9.2 s and 200 took 17.8 s against 60,000 events (linear in suppliers, each scanning every event): 3,000 suppliers would take about 4.5 minutes. | Index events by company, and for each supplier look up only the companies that can reach it (itself, parents, subsidiaries, siblings): `CorporateGraph.event_sources`. | 3,000 suppliers rescored in 5.2 s; the same scores and alerts as before (100 suppliers: 143 alerts in both versions). |
| 2 | **Supplier list scored every supplier before taking a page.** Row level security is an OR with a function call, so the planner could not use the tenant index, and the join to the latest score ran for all rows. Bulk uploads also give thousands of rows the same `created_at`, and the index ended in `id` ascending while the query sorts `id` descending. | EXPLAIN: 21 ms at 23,000 suppliers, growing with portfolio size. | Take the page first, then join; add the tenant condition explicitly (row level security still applies); recreate the list indexes with `id DESC`. Same change for the alert list. | 0.11 ms at 23,000 suppliers, independent of portfolio size. At 23,000 suppliers the list's p50 under load went from 29 ms at a realistic pace and 240 ms under stress (new query, old index) to 6 ms and 29 ms. |
| 3 | **Company search** used one OR across a trigram match, a prefix, and a ticker, which forced a sequential scan. | 27 to 29 ms per search at 20,000 companies. | Three indexable queries combined with UNION, plus a prefix index and a ticker index. | 2.6 to 4 ms in the query; p50 under load fell from 42 ms to 12 ms. |
| 4 | Score components and link candidates were looked up by their parent id with no index. | Sequential scans in the generic plans. | Two indexes (migration 0008). | 0.29 to 0.09 ms and 0.71 to 0.09 ms; matters as the tables grow. |
| 5 | **Event ingestion was quadratic.** The event index was rebuilt on every call. | Found by reading the code while profiling ingestion. | Keep the index, rebuild only on a length mismatch. | Linear. |

The 20 slowest queries by total time, with their generic plans, are in `docs/perf/top-queries-before.md` and
`docs/perf/top-queries-after.md`, produced by `infra/perf/top_queries.py` from `pg_stat_statements`. **After** the fixes the
list is led by company search (3.7 ms per call), followed by dashboard queries that run 25 to 50 ms on a cache miss: the
facility event list, the heat map, the source mix, and the weighted event count by state. They are cached for a minute and have
not been optimized further. The "seq scan" flags in the table for tenant tables describe generic plans, which cannot use a
parameter value; the real plans for the supplier and alert lists were checked with EXPLAIN ANALYZE.

## Uploads: 10,000 suppliers

`infra/perf/upload_bench.py`: a 10,000 row CSV (0.5 MB) with 80 percent of the names degraded (suffix variants, abbreviations,
typos), 30 percent of cities and 10 percent of states removed.

| | |
|---|---|
| Accepted (parsed, validated, stored) | 0.56 s |
| Every row resolved | 28 s, 357 rows per second |
| Outcome | 4,781 auto-resolved, 5,062 sent to review, 157 unresolved |

Resolution is processor bound (about 2.8 ms per row in one Python process); batching the database writes (100 rows per
transaction, now also safe to resume after a failure) saved about 4 percent. The review share is high because the test data is
deliberately noisy and the thresholds are provisional, so it says nothing about real review rates. A process pool would scale
this with cores; it is not built.

## Ingestion: 10,000 articles and 10,000 regulator records

`infra/perf/ingest_bench.py`, 20,000 company catalog, one process:

| | Records | Time | Throughput |
|---|---|---|---|
| News articles (chunking, topic filter, linking, keyword classification, event construction) | 10,000 (4,792 produced an event) | 0.17 s | about 60,000 per second |
| Regulator records (normalization, retrieval, Fellegi-Sunter scoring, attachment) | 10,000 (9,499 events) | 22.9 s | 437 per second |

**The article figure is not a measure of the real system.** Mention detection here is a regular expression, standing in for
BELA, and 70 percent of the generated mentions are exact catalog names, which hit a fast path. BELA, BLINK, and the language
model are not loaded in this environment, so their throughput on a GPU is **not measured**. The regulator figure is the
realistic one for the structured path: it runs the full scoring. The plan's target of ingesting 10,000 articles has been met
for the pipeline around the models, and cannot be stated for the models themselves until the BELA and BLINK spikes are run.

## Vector search (`hnsw.ef_search`)

`infra/perf/hnsw_sweep.py`: 20,000 company names embedded with the hashed character n-gram stand-in (not bge-m3), 1,000 queries
with up to three perturbations each, recall of the right company in the top 5, caches warm.

| `ef_search` | Recall at 5 | Mean ms | p95 ms |
|---|---|---|---|
| 10 | 0.987 | 0.75 | 0.87 |
| 20 | 0.991 | 0.88 | 1.01 |
| 40 | 0.994 | 1.71 | 2.95 |
| **100 (default)** | 0.996 | 2.52 | 3.87 |
| 200 | 0.996 | 3.82 | 5.06 |
| 400 | 0.996 | 5.44 | 7.25 |

Recall stops improving at 100, so the default stays. Setting it lower trades a little recall for speed. Embedding the 20,000
names took 100 seconds with the stand-in. The numbers depend on the embedder: repeat the sweep with the production model once it
is loaded.

## Connection pooling

Each API process holds its own pool (`DB_POOL_MIN`, `DB_POOL_MAX`, default 2 and 10; the load tests used 4 and 20). With 4
workers and 50 users the pools were never exhausted and no request waited for a connection (no failures, no pool timeouts).
I did not search for the point where they are: size `workers x DB_POOL_MAX` below PostgreSQL's `max_connections`. When the pool
is exhausted the API answers 503 with `Retry-After` instead of an error.

## Targets

| Target | Result |
|---|---|
| Revenue endpoints under 500 ms on seeded data (Phase 7) | met: the slowest cold revenue request measured 38 ms in the test suite and 28 ms here |
| 50 concurrent users on supplier views and dashboards, p50 and p95 recorded | recorded above |
| Upload of 10,000 suppliers | recorded above (28 s to resolve everything) |
| Ingestion of 10,000 articles | recorded, with the caveat that the models are not included |
| Query plans of the slowest queries reviewed, indexes added | done (migration 0008) |

## Limits of these measurements

Single machine, load generator and servers sharing cores; no network latency; synthetic data with fictional names; a single
tenant under load; warm caches; PostgreSQL defaults apart from `pg_stat_statements`. The cache hit rate under the read profile
is high by design. None of this replaces a test on the production hardware.
