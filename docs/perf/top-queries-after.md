# Slowest queries by total time

| # | Calls | Mean ms | Total ms | Rows per call | Plan summary | Query |
|---|---|---|---|---|---|---|
| 1 | 3760 | 3.67 | 13813 | 15.9 | indexed | `SELECT id, canonical_name, cik, lei, wikidata_qid, tickers, hq_city, hq_state, is_public, similarity(normalize` |
| 2 | 21963 | 0.13 | 2910 | 51.1 | seq scan: suppliers | `SELECT s.id, s.uploaded_name, s.tier, s.status, s.confidence, s.created_at, s.resolved_company_id, co.canonica` |
| 3 | 11028 | 0.18 | 2012 | 51.0 | seq scan: event_entities | `SELECT e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, e.summary, e.url, e.st` |
| 4 | 36 | 50.33 | 1812 | 4873.0 | indexed | `SELECT DISTINCT ON (id) id, title, event_type, severity, state, latitude, longitude, reported_at FROM ( SELECT` |
| 5 | 36 | 36.02 | 1297 | 36.0 | seq scan: risk_scores | `SELECT coalesce(q.tier, $4) AS tier, q.event_type, count(DISTINCT q.id) AS events, max(CASE l.level WHEN $5 TH` |
| 6 | 7406 | 0.17 | 1235 | 51.0 | seq scan: alerts | `SELECT a.id, a.supplier_id, s.uploaded_name AS supplier_name, a.kind, a.status, a.assignee_id, a.detail, a.rul` |
| 7 | 36 | 29.65 | 1067 | 12562.0 | seq scan: suppliers | `SELECT s.id, s.resolved_company_id AS cid, rs.level FROM suppliers s LEFT JOIN LATERAL (SELECT level FROM risk` |
| 8 | 36 | 29.42 | 1059 | 15.0 | indexed | `SELECT state, count(DISTINCT id) AS events, sum(severity) AS weighted_events FROM (SELECT DISTINCT id, state, ` |
| 9 | 36 | 25.91 | 933 | 117.0 | indexed | `SELECT date_trunc($1, reported_at)::date AS period, event_type, count(DISTINCT id) AS events FROM ( SELECT e.i` |
| 10 | 36 | 24.13 | 869 | 2.0 | indexed | `SELECT CASE WHEN source = $4 THEN $5 ELSE $6 END AS source_class, count(DISTINCT id) AS events FROM ( SELECT e` |
| 11 | 36 | 23.14 | 833 | 1.0 | indexed | `SELECT count(DISTINCT id) AS n FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reported_at, e.title,` |
| 12 | 18466 | 0.04 | 671 | 3.7 | indexed | `SELECT DISTINCT ON (e.reported_at, e.id) e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_a` |
| 13 | 88567 | 0.01 | 666 | 1.0 | seq scan: api_keys | `SELECT * FROM api_keys WHERE prefix = $1` |
| 14 | 11093 | 0.04 | 413 | 1.0 | indexed | `SELECT max(day) AS d FROM portfolio_stats_daily` |
| 15 | 88567 | 0.00 | 342 | 0.0 | not explained (SyntaxError) | `UPDATE api_keys SET last_used_at = now() WHERE id = $1 AND (last_used_at IS NULL OR last_used_at < now() - int` |
| 16 | 36 | 8.64 | 311 | 20.0 | not explained (SyntaxError) | `SELECT s.id AS supplier_id, s.uploaded_name AS name, s.tier, l.score, l.level, (SELECT jsonb_build_object($1, ` |
| 17 | 36 | 8.38 | 302 | 4.0 | seq scan: risk_scores, suppliers | `SELECT l.level, count(*) AS n FROM suppliers s JOIN (SELECT DISTINCT ON (r.supplier_id) r.supplier_id, r.score` |
| 18 | 36 | 7.21 | 259 | 3.0 | seq scan: suppliers | `SELECT status, count(*) AS n FROM suppliers WHERE duplicate_of IS NULL GROUP BY status` |
| 19 | 18466 | 0.01 | 225 | 1.0 | indexed | `SELECT * FROM suppliers WHERE id = $1` |
| 20 | 41 | 4.27 | 175 | 1.0 | seq scan: suppliers | `SELECT count(*) AS n FROM suppliers WHERE duplicate_of IS NULL AND status IN ($1,$2)` |

## 1. SELECT id, canonical_name, cik, lei, wikidata_qid, tickers, hq_city, hq_state, is_public, similarity(normalized_name, $1) AS score FROM ( (SELECT id, canonical_

Calls 3760, mean 3.67 ms.

```
Limit
  ->  Sort
        Sort Key: (similarity(t.normalized_name, $1)) DESC, t.id
        ->  Subquery Scan on t
              ->  HashAggregate
                    Group Key: companies.id, companies.canonical_name, companies.normalized_name, companies.cik, companies.lei, companies.wikidata_qid, companies.tickers, companies.hq_city, companies.hq_state, companies.is_public
                    ->  Append
                          ->  Bitmap Heap Scan on companies
                                Recheck Cond: (normalized_name % $2)
                                ->  Bitmap Index Scan on companies_norm_trgm
                                      Index Cond: (normalized_name % $2)
                          ->  Limit
                                ->  Bitmap Heap Scan on companies companies_1
                                      Recheck Cond: (normalized_name ~~ ($3 || $6))
                                      ->  Bitmap Index Scan on companies_norm_trgm
                                            Index Cond: (normalized_name ~~ ($3 || $6))
                          ->  Bitmap Heap Scan on companies companies_2
                                Recheck Cond: (tickers @> ARRAY[upper($4)])
                                ->  Bitmap Index Scan on companies_tickers
                                      Index Cond: (tickers @> ARRAY[upper($4)])
```

## 2. SELECT s.id, s.uploaded_name, s.tier, s.status, s.confidence, s.created_at, s.resolved_company_id, co.canonical_name AS company_name, rs.score AS risk_score, rs

Calls 21963, mean 0.13 ms.

```
Nested Loop Left Join
  Join Filter: $16
  ->  Nested Loop Left Join
        ->  Limit
              ->  Sort
                    Sort Key: s.created_at DESC, s.id DESC
                    ->  Seq Scan on suppliers s
                          Filter: (($2 OR (duplicate_of IS NULL)) AND (($3 IS NULL) OR (status = $4)) AND (($5 IS NULL) OR (tier = $6)) AND (tenant_id = $1) AND (($9 IS NULL) OR (ROW(created_at, id) < ROW($10, $11))) AND (($7 IS NULL) OR (uploaded_name ~~* (($13 || $8) || $14))))
        ->  Index Scan using companies_pkey on companies co
              Index Cond: (id = s.resolved_company_id)
  ->  Limit
        ->  Incremental Sort
              Sort Key: r.computed_at DESC, r.id DESC
              Presorted Key: r.computed_at
              ->  Index Scan using risk_scores_supplier on risk_scores r
                    Index Cond: (supplier_id = s.id)
```

## 3. SELECT e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, e.summary, e.url, e.state, e.city, e.cluster_id FROM events e WHERE EXIS

Calls 11028, mean 0.18 ms.

```
Limit
  ->  Sort
        Sort Key: e.reported_at DESC, e.id DESC
        ->  Nested Loop
              ->  HashAggregate
                    Group Key: ee.event_id
                    ->  Seq Scan on event_entities ee
                          Filter: ((($1 IS NULL) OR (company_id = $2)) AND (route = $17))
              ->  Index Scan using events_pkey on events e
                    Index Cond: (id = ee.event_id)
                    Filter: ((($3 IS NULL) OR (source = $4)) AND (($5 IS NULL) OR (event_type = $6)) AND (severity >= $7) AND (($8 IS NULL) OR (state = $9)) AND (($10 IS NULL) OR (reported_at >= $11)) AND (($12 IS NULL) OR (ROW(reported_at, id) < ROW($13, $14))))
```

## 4. SELECT DISTINCT ON (id) id, title, event_type, severity, state, latitude, longitude, reported_at FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.repor

Calls 36, mean 50.33 ms.

```
Unique
  ->  Sort
        Sort Key: e.id, e.reported_at DESC
        ->  Nested Loop
              ->  Nested Loop
                    ->  Bitmap Heap Scan on events e
                          Recheck Cond: ((reported_at >= $1) AND (reported_at < $2))
                          Filter: ((latitude IS NOT NULL) AND (longitude IS NOT NULL) AND (($3 IS NULL) OR (($3 = $5) AND (source <> $6)) OR (source = $3)))
                          ->  Bitmap Index Scan on events_reported
                                Index Cond: ((reported_at >= $1) AND (reported_at < $2))
                    ->  Index Scan using event_entities_event on event_entities ee
                          Index Cond: (event_id = e.id)
                          Filter: (route = $4)
              ->  Index Scan using suppliers_company on suppliers s
                    Index Cond: (resolved_company_id = ee.company_id)
                    Filter: (duplicate_of IS NULL)
```

## 5. SELECT coalesce(q.tier, $4) AS tier, q.event_type, count(DISTINCT q.id) AS events, max(CASE l.level WHEN $5 THEN $6 WHEN $7 THEN $8 WHEN $9 THEN $10 WHEN $11 TH

Calls 36, mean 36.02 ms.

```
GroupAggregate
  Group Key: (COALESCE(s.tier, $4)), e.event_type
  ->  Sort
        Sort Key: (COALESCE(s.tier, $4)), e.event_type, e.id
        ->  Merge Left Join
              Merge Cond: (s.id = r.supplier_id)
              ->  Sort
                    Sort Key: s.id
                    ->  Nested Loop
                          ->  Nested Loop
                                ->  Bitmap Heap Scan on events e
                                      Recheck Cond: ((reported_at >= $1) AND (reported_at < $2))
                                      Filter: (($3 IS NULL) OR (($3 = $14) AND (source <> $15)) OR (source = $3))
                                      ->  Bitmap Index Scan on events_reported
                                            Index Cond: ((reported_at >= $1) AND (reported_at < $2))
                                ->  Index Scan using event_entities_event on event_entities ee
                                      Index Cond: (event_id = e.id)
                                      Filter: (route = $13)
                          ->  Index Scan using suppliers_company on suppliers s
                                Index Cond: (resolved_company_id = ee.company_id)
                                Filter: (duplicate_of IS NULL)
              ->  Unique
                    ->  Sort
                          Sort Key: r.supplier_id, r.computed_at DESC, r.id DESC
                          ->  Seq Scan on risk_scores r
```

## 6. SELECT a.id, a.supplier_id, s.uploaded_name AS supplier_name, a.kind, a.status, a.assignee_id, a.detail, a.rule_id, a.created_at, a.updated_at FROM alerts a JOI

Calls 7406, mean 0.17 ms.

```
Limit
  ->  Sort
        Sort Key: a.created_at DESC, a.id DESC
        ->  Nested Loop
              ->  Seq Scan on alerts a
                    Filter: (((tenant_id = $1) OR ($2 IS NULL)) AND (($3 IS NULL) OR (status = $4)) AND (($5 IS NULL) OR (assignee_id = $6)) AND (($7 IS NULL) OR (supplier_id = $8)) AND (($9 IS NULL) OR (ROW(created_at, id) < ROW($10, $11))))
              ->  Index Scan using suppliers_pkey on suppliers s
                    Index Cond: (id = a.supplier_id)
```

## 7. SELECT s.id, s.resolved_company_id AS cid, rs.level FROM suppliers s LEFT JOIN LATERAL (SELECT level FROM risk_scores r WHERE r.supplier_id = s.id ORDER BY comp

Calls 36, mean 29.65 ms.

```
Nested Loop Left Join
  Join Filter: $2
  ->  Seq Scan on suppliers s
        Filter: ((resolved_company_id IS NOT NULL) AND (duplicate_of IS NULL))
  ->  Limit
        ->  Incremental Sort
              Sort Key: r.computed_at DESC, r.id DESC
              Presorted Key: r.computed_at
              ->  Index Scan using risk_scores_supplier on risk_scores r
                    Index Cond: (supplier_id = s.id)
```

## 8. SELECT state, count(DISTINCT id) AS events, sum(severity) AS weighted_events FROM (SELECT DISTINCT id, state, severity FROM ( SELECT e.id, e.source, e.event_typ

Calls 36, mean 29.42 ms.

```
Sort
  Sort Key: (sum(q.severity)) DESC, q.state
  ->  GroupAggregate
        Group Key: q.state
        ->  Sort
              Sort Key: q.state, q.id
              ->  Subquery Scan on q
                    ->  Unique
                          ->  Sort
                                Sort Key: e.id, e.state, e.severity
                                ->  Nested Loop
                                      ->  Nested Loop
                                            ->  Bitmap Heap Scan on events e
                                                  Recheck Cond: ((reported_at >= $1) AND (reported_at < $2))
                                                  Filter: ((state IS NOT NULL) AND (($3 IS NULL) OR (($3 = $5) AND (source <> $6)) OR (source = $3)))
                                                  ->  Bitmap Index Scan on events_reported
                                                        Index Cond: ((reported_at >= $1) AND (reported_at < $2))
                                            ->  Index Scan using event_entities_event on event_entities ee
                                                  Index Cond: (event_id = e.id)
                                                  Filter: (route = $4)
                                      ->  Index Scan using suppliers_company on suppliers s
                                            Index Cond: (resolved_company_id = ee.company_id)
                                            Filter: (duplicate_of IS NULL)
```

## 9. SELECT date_trunc($1, reported_at)::date AS period, event_type, count(DISTINCT id) AS events FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reported_

Calls 36, mean 25.91 ms.

```
GroupAggregate
  Group Key: ((date_trunc($1, e.reported_at))::date), e.event_type
  ->  Sort
        Sort Key: ((date_trunc($1, e.reported_at))::date), e.event_type, e.id
        ->  Nested Loop
              ->  Nested Loop
                    ->  Bitmap Heap Scan on events e
                          Recheck Cond: ((reported_at >= $2) AND (reported_at < $3))
                          Filter: (($4 IS NULL) OR (($4 = $6) AND (source <> $7)) OR (source = $4))
                          ->  Bitmap Index Scan on events_reported
                                Index Cond: ((reported_at >= $2) AND (reported_at < $3))
                    ->  Index Scan using event_entities_event on event_entities ee
                          Index Cond: (event_id = e.id)
                          Filter: (route = $5)
              ->  Index Scan using suppliers_company on suppliers s
                    Index Cond: (resolved_company_id = ee.company_id)
                    Filter: (duplicate_of IS NULL)
```

## 10. SELECT CASE WHEN source = $4 THEN $5 ELSE $6 END AS source_class, count(DISTINCT id) AS events FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reporte

Calls 36, mean 24.13 ms.

```
Sort
  Sort Key: (count(DISTINCT e.id)) DESC
  ->  GroupAggregate
        Group Key: (CASE WHEN (e.source = $4) THEN $5 ELSE $6 END)
        ->  Sort
              Sort Key: (CASE WHEN (e.source = $4) THEN $5 ELSE $6 END), e.id
              ->  Nested Loop
                    ->  Nested Loop
                          ->  Bitmap Heap Scan on events e
                                Recheck Cond: ((reported_at >= $1) AND (reported_at < $2))
                                Filter: (($3 IS NULL) OR (($3 = $8) AND (source <> $9)) OR (source = $3))
                                ->  Bitmap Index Scan on events_reported
                                      Index Cond: ((reported_at >= $1) AND (reported_at < $2))
                          ->  Index Scan using event_entities_event on event_entities ee
                                Index Cond: (event_id = e.id)
                                Filter: (route = $7)
                    ->  Index Scan using suppliers_company on suppliers s
                          Index Cond: (resolved_company_id = ee.company_id)
                          Filter: (duplicate_of IS NULL)
```

## 11. SELECT count(DISTINCT id) AS n FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reported_at, e.title, e.state, e.latitude, e.longitude, s.id AS supplie

Calls 36, mean 23.14 ms.

```
Aggregate
  ->  Sort
        Sort Key: e.id
        ->  Nested Loop
              ->  Nested Loop
                    ->  Bitmap Heap Scan on events e
                          Recheck Cond: ((reported_at >= $1) AND (reported_at < $2))
                          Filter: (($3 IS NULL) OR (($3 = $5) AND (source <> $6)) OR (source = $3))
                          ->  Bitmap Index Scan on events_reported
                                Index Cond: ((reported_at >= $1) AND (reported_at < $2))
                    ->  Index Scan using event_entities_event on event_entities ee
                          Index Cond: (event_id = e.id)
                          Filter: (route = $4)
              ->  Index Scan using suppliers_company on suppliers s
                    Index Cond: (resolved_company_id = ee.company_id)
                    Filter: (duplicate_of IS NULL)
```

## 12. SELECT DISTINCT ON (e.reported_at, e.id) e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, e.summary, e.url, e.state, ee.company_

Calls 18466, mean 0.04 ms.

```
Limit
  ->  Unique
        ->  Sort
              Sort Key: e.reported_at DESC, e.id DESC
              ->  Nested Loop
                    ->  Bitmap Heap Scan on event_entities ee
                          Recheck Cond: (company_id = ANY ($1))
                          Filter: (route = $3)
                          ->  Bitmap Index Scan on event_entities_company
                                Index Cond: (company_id = ANY ($1))
                    ->  Index Scan using events_pkey on events e
                          Index Cond: (id = ee.event_id)
```

## 13. SELECT * FROM api_keys WHERE prefix = $1

Calls 88567, mean 0.01 ms.

```
Seq Scan on api_keys
  Filter: (prefix = $1)
```

## 14. SELECT max(day) AS d FROM portfolio_stats_daily

Calls 11093, mean 0.04 ms.

```
Result
  InitPlan 1
    ->  Limit
          ->  Index Only Scan Backward using portfolio_stats_day on portfolio_stats_daily
```

## 15. UPDATE api_keys SET last_used_at = now() WHERE id = $1 AND (last_used_at IS NULL OR last_used_at < now() - interval $2)

Calls 88567, mean 0.00 ms.

```
not explained (SyntaxError)
```

## 16. SELECT s.id AS supplier_id, s.uploaded_name AS name, s.tier, l.score, l.level, (SELECT jsonb_build_object($1, e.title, $2, e.reported_at, $3, e.event_type) FROM

Calls 36, mean 8.64 ms.

```
not explained (SyntaxError)
```

## 17. SELECT l.level, count(*) AS n FROM suppliers s JOIN (SELECT DISTINCT ON (r.supplier_id) r.supplier_id, r.score, r.level, r.computed_at FROM risk_scores r ORDER 

Calls 36, mean 8.38 ms.

```
HashAggregate
  Group Key: l.level
  ->  Hash Join
        Hash Cond: (s.id = l.supplier_id)
        ->  Seq Scan on suppliers s
              Filter: (duplicate_of IS NULL)
        ->  Hash
              ->  Subquery Scan on l
                    ->  Unique
                          ->  Sort
                                Sort Key: r.supplier_id, r.computed_at DESC, r.id DESC
                                ->  Seq Scan on risk_scores r
```

## 18. SELECT status, count(*) AS n FROM suppliers WHERE duplicate_of IS NULL GROUP BY status

Calls 36, mean 7.21 ms.

```
HashAggregate
  Group Key: status
  ->  Seq Scan on suppliers
        Filter: (duplicate_of IS NULL)
```

## 19. SELECT * FROM suppliers WHERE id = $1

Calls 18466, mean 0.01 ms.

```
Index Scan using suppliers_pkey on suppliers
  Index Cond: (id = $1)
```

## 20. SELECT count(*) AS n FROM suppliers WHERE duplicate_of IS NULL AND status IN ($1,$2)

Calls 41, mean 4.27 ms.

```
Aggregate
  ->  Seq Scan on suppliers
        Filter: ((duplicate_of IS NULL) AND (status = ANY (ARRAY[$1, $2])))
```
