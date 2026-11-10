# Canonical company knowledge base

Phase 2 deliverable. Schema lives in `apps/api/migrations/versions/` (Alembic, revisions 0001 to 0003).
Run `make migrate` then `make etl`.

## Tables

| Group | Tables |
|---|---|
| Tenancy and security | tenants, users, user_mfa, refresh_tokens, api_keys, audit_log (append-only trigger) |
| Company knowledge | companies, company_aliases, company_relationships, facilities, entity_embeddings, source_records, canonical_conflicts |
| Events and NLP | articles, article_embeddings, mentions, events, event_entities, link_candidates |
| Portfolio | supplier_uploads, suppliers, resolution_reviews, risk_scores, risk_score_components, alert_rules, alerts, alert_events, reports |
| Business | plans, subscriptions, invoices, invoice_lines, usage_daily, portfolio_stats_daily, platform_stats_daily, marketing_spend, business_events; materialized views mrr_monthly, cohort_retention |

Row Level Security policies on tenant tables are added in the API phase (phase 5) together with the
per-request `SET LOCAL app.tenant_id` mechanism.

## Canonical build rules (`app/kb/canonical.py`)

1. Identifier match (CIK, LEI, Wikidata QID).
2. Exact normalized name plus state.
3. High similarity names (token sort ratio of 92 or more, compatible state) are never merged
   automatically. They are written to `canonical_conflicts` as `fuzzy_candidate` for review and the
   record starts a new company.

Every source record is stored in `source_records` with method and score. Conflicts recorded:
`identifier_conflict`, `fuzzy_candidate`, `relationship_cycle`, `parent_conflict`.

Source order matters only for which display name wins: EDGAR, Wikidata, GLEIF, Exhibit 21.
Facilities link to a company only on exact normalized name plus state; the remainder is resolved
by the phase 3 engine.

## Normalization (`app/kb/normalize.py`)

NFKC, case folding, "&" to "and", legal suffix removal (cleanco), punctuation removal, abbreviation
expansion (intl, mfg, and similar), leading "the" removal. "st" is not expanded (saint or street).
Address parsing uses usaddress; `token_sort_key` gives an order-insensitive key.

## Embeddings

`BgeM3Embedder` (BAAI/bge-m3, 1024 dimensions, fp16 on GPU) writes names, aliases, and short
descriptions to `entity_embeddings` (HNSW, cosine, m=16, ef_construction=64). Install
`sentence-transformers` to use it. `HashedNgramEmbedder` is a test stand-in; numbers measured with it
are not bge-m3 results.

## Data quality

`app/kb/quality.py` runs pandera schema checks and SQL assertions (non-empty names, valid state
codes, unique CIK and LEI, unique source keys, relationship sanity, vector dimension 1024, coordinate
ranges) and prints identifier coverage, facility link rate, and conflict counts. `make etl` exits
non-zero when a check fails.

## Verification status

Verified on fixtures and a local PostgreSQL 17 with pgvector 0.8: migrations upgrade and downgrade,
ETL, quality checks, index use for key queries (trigram, exact name and state, CIK, family lookup,
HNSW), and vector search recall at 5 on 1,000 synthetic names using the stand-in embedder.
Not yet measured: coverage on the real downloads and bge-m3 recall at 5. Those require `make data`
and a GPU or patience on CPU.
