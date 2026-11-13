# Product workflows (Phase 6)

Code: `apps/api/app/routers/{uploads,suppliers,corrections,monitoring,business}.py` and
`apps/api/app/services/{review,profile,portfolio,monitoring,notify,reports,pdf}.py`.
Tests: `apps/api/tests/api/test_phase6.py` (includes the end-to-end exit scenario).
Migration: `0005_workflows.py`. PDF generation needs Pango (`libpango-1.0-0` on Debian, Homebrew
`pango` on macOS with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`, which the Makefile sets).

## Supplier upload

`GET /uploads/template` returns a CSV template. `POST /uploads/preview` validates a file and proposes
a column mapping without storing anything (columns, detected mapping, unmapped fields, valid and
invalid row counts, sample rows). `POST /uploads` stores and resolves in a background task; progress
and counts are on `GET /uploads/{id}`. `GET /uploads/{id}/export` returns results with canonical
identifiers and `GET /uploads/{id}/errors` the rows that were not imported. Limits: UTF-8, name
column required, 10,000 rows, 10 MB, `Idempotency-Key` supported. Exports neutralise spreadsheet
formulas, and tax IDs and account numbers are encrypted and never exported.

## Review queue

`GET /reviews/{id}` returns the uploaded record beside each candidate with field agreement (name
similarity, state, city, country, CIK, LEI, ticker, parent, industry) and the model scores
(retrieval, Splink-style weight, BLINK when present). Actions: accept, choose another company,
reject, mark unresolved, and "not in database". `POST /reviews/bulk-accept` accepts every open review
above a probability and margin. `POST /suppliers/{id}/merge` marks a duplicate (hidden from lists,
scoring, and concentration; reversible with `unmerge`). Decisions are stored on the review. Labeled
examples go to `training_feedback` only when the tenant opted in, with no tenant identifier.

## Supplier profile

`GET /suppliers/{id}/profile`: canonical record and aliases, identifiers, family tree (ancestors and
descendants, source and as-of date per edge, portfolio overlay), facilities with coordinates, event
timeline with the relation and path to the supplier, risk score with every component and category
sub-scores, and source links.

## Corporate graph

`/graph/neighbors` (depth up to 3, at most 500 nodes, portfolio overlay), `/graph/path`, and
`/graph/concentration` (suppliers and high or critical suppliers grouped under their ultimate parent,
with shares and a cumulative Pareto share).

## Monitoring, alerts, and notifications

`services/monitoring.py` rescoring wraps the Phase 4 library around the tables: it loads accepted
events, clusters duplicates (the representative id is written to `events.cluster_id`), rolls events up
the corporate graph, scores each resolved supplier with the tenant's risk configuration, stores a new
score only when something changed, drafts alerts, creates them de-duplicated per supplier and event,
publishes them on the tenant's live channel, and dispatches notifications. `POST /monitoring/recompute`
runs it for one tenant; `recompute_all` is the entry for a scheduled task.

Rule channels: in-app (the alert and the live stream), email to the tenant's managers and admins, and
a webhook (https only; the host is resolved and rejected if it is private, loopback, link-local, or
reserved; redirects are not followed; three attempts with exponential backoff; client errors are not
retried). Every attempt is logged in `alert_deliveries`. Alert lifecycle, comments, and the mandatory
dismissal reason are from Phase 5.

## Corrections

`POST /corrections` (any tenant role) flags a wrong link, an outdated record, or another problem on a
supplier, event, or company. The tenant sees status and the platform's response in `GET /corrections`.
Platform administrators work the queue through `GET` and `PATCH /platform/corrections`. A correction
does not change an event for other tenants by itself.

## Reports

`POST /reports/supplier/{id}` and `POST /reports/portfolio` create a report and render a PDF in a
background task under row level security. Status is `queued`, `ready`, or `failed` (with the reason).
The PDF has the report ID and timestamp, the disclaimer, a demo data notice (`DEMO_MODE`), identity,
family, events (record date, source, link, and the relation to the supplier), the score breakdown, and
source records. All dynamic text is HTML-escaped, the renderer refuses every external resource, and
downloads are tenant-scoped and limited to the report directory.

## Status and limits

- Verified by tests: the full exit scenario (messy upload, review, subsidiary event, SSE alert for the
  parent, PDF report), notification delivery, retries, the SSRF guard, concentration, corrections, merge,
  feedback opt-in, and PDF content (text extracted from the generated files).
- Webhook delivery checks the resolved address before sending, but the HTTP client resolves the host
  again when it connects, so a DNS rebinding race is not closed. Pin the address in production.
- Webhook payloads are not signed. Add an HMAC secret per rule before using webhooks with untrusted receivers.
- Resolution of an upload runs in the API process (a background task), not in a worker queue. A
  restart during processing leaves the upload in `processing`; Celery is still to be wired.
- Reports are stored on local disk (`REPORT_DIR`).
- Upload progress is updated every 100 rows; there is no push progress event.
- The supplier report layout was checked by rendering a sample to an image; the portfolio report was checked by its extracted text only.
- Merging does not move alerts or notes from the duplicate to the primary record.
