# Event pipeline and risk scoring (Phase 4)

Code: `apps/api/app/events/`. Rules: `apps/api/app/events/config/event_rules_v1.yaml`.
Tests: `apps/api/tests/events/`.

## Flow

regulator rows or news articles -> normalized events -> entity links (resolution engine) -> dedup
clusters -> roll-up to suppliers -> risk score -> alerts.

| Step | Module | Notes |
|---|---|---|
| Regulator normalizers | `normalizers/{epa,osha,nhtsa,cpsc,fda}.py` | Stable `source_id` per record, so reloads are idempotent. Field names, thresholds, and severity bands come from the versioned rules file |
| File ingest | `ingest.py` | CSV, tab-delimited (NHTSA), and JSON readers; prints skip reasons and missing mapped fields |
| News classification | `classifier.py` | Local LLM under a JSON schema (event type, severity 1 to 4); keyword fallback marks events `degraded`. Snippet capped at 300 characters |
| Deduplication | `dedup.py` | Same resolved company, event type, state, and window (7 days). Regulator plus news merge on those alone; two news items also need similar titles. Unresolved events never merge. The regulator record represents a cluster |
| Attach | `attach.py` | Resolution engine per entity. Only accepted or exact-identifier links are visible to tenants; review and NIL links form the platform review queue |
| Risk score | `risk.py` | Formula and defaults from the plan, tenant edits validated inside `BOUNDS`, every factor returned per event, sub-scores per category |
| Monitoring | `monitor.py` | Threshold-crossing and severe-event alerts, de-duplicated per supplier and event, tenant rule filters |
| Pipeline | `pipeline.py` | In-memory orchestration used by the end-to-end test |
| Persistence | `store.py` | SQL for events, entity links, candidates, scores. Not run: no PostgreSQL server was available |
| Label evaluation | `evaluation.py` | Per-class precision and recall, severity accuracy; refuses to run without a gold file |

## Wording rule

Event titles state what the record says (for example "OSHA citation record for X: serious
classification, penalty $20,000"). They never state that a company broke a law or caused an
incident. A test checks the normalizer titles for fault wording.

## Score

`event_impact = severity_weight * recency_decay * link_confidence * relation_weight * source_reliability`
`supplier_risk = 100 * (1 - product(1 - min(event_impact, 0.6)))`

Defaults: severity weights 0.10, 0.25, 0.45, 0.60; half-life 180 days (regulator) and 30 days
(news); relation weights direct 1.0, subsidiary to parent 0.7, parent to subsidiary 0.5, sibling
0.2, depth at most 2; reliability regulator 1.0, news 0.7. Levels: critical 70 and above, high 50
to 69, medium 30 to 49, low below 30. An incident that reaches a supplier by several paths, or in
several sources, counts once.

## Status

| Item | State |
|---|---|
| Normalizers, rules, dedup, scoring, monitoring, end-to-end flow | Implemented and unit tested on fixtures |
| Regulator field names | Written from the public data dictionaries as understood at the time; **not checked against real downloaded files**. Run `python -m app.events.ingest` on a real file and read the `missing_field` counts |
| NHTSA column order | Assumed from RCL.txt; confirm on a real file |
| Local LLM labeling | Client tested against a mock server only. Accuracy is **not measured**: the 200-sentence gold set (`data/gold/events.jsonl`) does not exist yet |
| Severity bands and thresholds | Initial values, unvalidated against real data |
| Dedup thresholds (7 days, title similarity 0.35) | Initial values; the embedding-similarity option is available through the `similarity` argument but not wired to bge-m3 |
| Scheduled recomputation | Logic implemented (`recompute`); the Celery beat tasks belong to Phase 5 job wiring |
| Alert persistence, `alert_events` lifecycle | Not implemented here; alerts are drafts with a dedup key |
