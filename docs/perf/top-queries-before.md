# Slowest queries by total time

| # | Calls | Mean ms | Total ms | Rows per call | Plan summary | Query |
|---|---|---|---|---|---|---|
| 1 | 30378 | 8.45 | 256645 | 51.0 | seq scan: suppliers | `SELECT s.id, s.uploaded_name, s.tier, s.status, s.confidence, s.created_at, s.resolved_company_id, co.canonica` |
| 2 | 5133 | 33.69 | 172951 | 16.0 | seq scan: companies | `SELECT id, canonical_name, cik, lei, wikidata_qid, tickers, hq_city, hq_state, is_public, similarity(normalize` |
| 3 | 40252 | 1.56 | 62599 | 3.8 | seq scan: risk_score_components | `SELECT c.event_id, c.category, c.severity_weight, c.recency_decay, c.link_confidence, c.relation_weight, c.sou` |
| 4 | 10095 | 4.75 | 47971 | 51.0 | seq scan: alerts | `SELECT a.id, a.supplier_id, s.uploaded_name AS supplier_name, a.kind, a.status, a.assignee_id, a.detail, a.rul` |
| 5 | 15195 | 0.17 | 2646 | 51.0 | seq scan: event_entities | `SELECT e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, e.summary, e.url, e.st` |
| 6 | 121043 | 0.01 | 890 | 1.0 | seq scan: api_keys | `SELECT * FROM api_keys WHERE prefix = $1` |
| 7 | 24937 | 0.03 | 683 | 3.8 | indexed | `SELECT DISTINCT ON (e.reported_at, e.id) e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_a` |
| 8 | 14967 | 0.04 | 582 | 1.0 | indexed | `SELECT max(day) AS d FROM portfolio_stats_daily` |
| 9 | 121043 | 0.00 | 453 | 0.0 | not explained (SyntaxError) | `UPDATE api_keys SET last_used_at = now() WHERE id = $1 AND (last_used_at IS NULL OR last_used_at < now() - int` |
| 10 | 40252 | 0.01 | 362 | 1.0 | indexed | `SELECT id, score, level, config_version, computed_at FROM risk_scores WHERE supplier_id = $1 ORDER BY computed` |
| 11 | 21 | 12.59 | 264 | 2307.0 | indexed | `SELECT DISTINCT ON (id) id, title, event_type, severity, state, latitude, longitude, reported_at FROM ( SELECT` |
| 12 | 21 | 11.91 | 250 | 117.0 | indexed | `SELECT date_trunc($1, reported_at)::date AS period, event_type, count(DISTINCT id) AS events FROM ( SELECT e.i` |
| 13 | 21 | 11.85 | 249 | 27.0 | seq scan: risk_scores | `SELECT coalesce(q.tier, $4) AS tier, q.event_type, count(DISTINCT q.id) AS events, max(CASE l.level WHEN $5 TH` |
| 14 | 24937 | 0.01 | 234 | 1.0 | indexed | `SELECT * FROM suppliers WHERE id = $1` |
| 15 | 21 | 10.31 | 217 | 15.0 | indexed | `SELECT state, count(DISTINCT id) AS events, sum(severity) AS weighted_events FROM (SELECT DISTINCT id, state, ` |
| 16 | 24937 | 0.01 | 205 | 0.4 | indexed | `SELECT registry_id, name, address, city, state, postal_code, latitude, longitude, industry_code, source, link_` |
| 17 | 21 | 9.41 | 198 | 2.0 | indexed | `SELECT CASE WHEN source = $4 THEN $5 ELSE $6 END AS source_class, count(DISTINCT id) AS events FROM ( SELECT e` |
| 18 | 21 | 8.19 | 172 | 1.0 | indexed | `SELECT count(DISTINCT id) AS n FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reported_at, e.title,` |
| 19 | 30877 | 0.00 | 149 | 0.2 | indexed | `SELECT parent_id, child_id FROM company_relationships WHERE parent_id = ANY($1) AND rel_type IN ($2,$3,$4)` |
| 20 | 24937 | 0.01 | 139 | 1.0 | indexed | `SELECT id, canonical_name, legal_form, cik, lei, wikidata_qid, tickers, sic_code, state_of_incorporation, hq_c` |

## 1. SELECT s.id, s.uploaded_name, s.tier, s.status, s.confidence, s.created_at, s.resolved_company_id, co.canonical_name AS company_name, rs.score AS risk_score, rs

Calls 30378, mean 8.45 ms.

```
Limit
  ->  Sort
        Sort Key: s.created_at DESC, s.id DESC
        ->  Nested Loop Left Join
              Join Filter: $15
              Filter: (($8 IS NULL) OR (r.level = $9))
              ->  Nested Loop Left Join
                    ->  Seq Scan on suppliers s
                          Filter: (($1 OR (duplicate_of IS NULL)) AND (($2 IS NULL) OR (status = $3)) AND (($4 IS NULL) OR (tier = $5)) AND (($10 IS NULL) OR (ROW(created_at, id) < ROW($11, $12))) AND (($6 IS NULL) OR (uploaded_name ~~* (($16 || $7) || $17))))
                    ->  Index Scan using companies_pkey on companies co
                          Index Cond: (id = s.resolved_company_id)
              ->  Limit
                    ->  Incremental Sort
                          Sort Key: r.computed_at DESC, r.id DESC
                          Presorted Key: r.computed_at
                          ->  Index Scan using risk_scores_supplier on risk_scores r
                                Index Cond: (supplier_id = s.id)
```

## 2. SELECT id, canonical_name, cik, lei, wikidata_qid, tickers, hq_city, hq_state, is_public, similarity(normalized_name, $1) AS score FROM companies WHERE normaliz

Calls 5133, mean 33.69 ms.

```
Limit
  ->  Sort
        Sort Key: (similarity(normalized_name, $1)) DESC, id
        ->  Seq Scan on companies
              Filter: ((normalized_name % $2) OR (normalized_name ~~ ($3 || $6)) OR (upper($4) = ANY (tickers)))
```

## 3. SELECT c.event_id, c.category, c.severity_weight, c.recency_decay, c.link_confidence, c.relation_weight, c.source_reliability, c.event_impact, e.title, e.source

Calls 40252, mean 1.56 ms.

```
Sort
  Sort Key: c.event_impact DESC
  ->  Nested Loop
        ->  Seq Scan on risk_score_components c
              Filter: (risk_score_id = $1)
        ->  Index Scan using events_pkey on events e
              Index Cond: (id = c.event_id)
```

## 4. SELECT a.id, a.supplier_id, s.uploaded_name AS supplier_name, a.kind, a.status, a.assignee_id, a.detail, a.rule_id, a.created_at, a.updated_at FROM alerts a JOI

Calls 10095, mean 4.75 ms.

```
Limit
  ->  Sort
        Sort Key: a.created_at DESC, a.id DESC
        ->  Nested Loop
              ->  Seq Scan on alerts a
                    Filter: ((($1 IS NULL) OR (status = $2)) AND (($3 IS NULL) OR (assignee_id = $4)) AND (($5 IS NULL) OR (supplier_id = $6)) AND (($7 IS NULL) OR (ROW(created_at, id) < ROW($8, $9))))
              ->  Index Scan using suppliers_pkey on suppliers s
                    Index Cond: (id = a.supplier_id)
```

## 5. SELECT e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, e.summary, e.url, e.state, e.city, e.cluster_id FROM events e WHERE EXIS

Calls 15195, mean 0.17 ms.

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

## 6. SELECT * FROM api_keys WHERE prefix = $1

Calls 121043, mean 0.01 ms.

```
Seq Scan on api_keys
  Filter: (prefix = $1)
```

## 7. SELECT DISTINCT ON (e.reported_at, e.id) e.id, e.source, e.event_type, e.severity, e.occurred_at, e.reported_at, e.title, e.summary, e.url, e.state, ee.company_

Calls 24937, mean 0.03 ms.

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

## 8. SELECT max(day) AS d FROM portfolio_stats_daily

Calls 14967, mean 0.04 ms.

```
Result
  InitPlan 1
    ->  Limit
          ->  Index Only Scan Backward using portfolio_stats_day on portfolio_stats_daily
```

## 9. UPDATE api_keys SET last_used_at = now() WHERE id = $1 AND (last_used_at IS NULL OR last_used_at < now() - interval $2)

Calls 121043, mean 0.00 ms.

```
not explained (SyntaxError)
```

## 10. SELECT id, score, level, config_version, computed_at FROM risk_scores WHERE supplier_id = $1 ORDER BY computed_at DESC, id DESC LIMIT $2

Calls 40252, mean 0.01 ms.

```
Limit
  ->  Incremental Sort
        Sort Key: computed_at DESC, id DESC
        Presorted Key: computed_at
        ->  Index Scan using risk_scores_supplier on risk_scores
              Index Cond: (supplier_id = $1)
```

## 11. SELECT DISTINCT ON (id) id, title, event_type, severity, state, latitude, longitude, reported_at FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.repor

Calls 21, mean 12.59 ms.

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

## 12. SELECT date_trunc($1, reported_at)::date AS period, event_type, count(DISTINCT id) AS events FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reported_

Calls 21, mean 11.91 ms.

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

## 13. SELECT coalesce(q.tier, $4) AS tier, q.event_type, count(DISTINCT q.id) AS events, max(CASE l.level WHEN $5 THEN $6 WHEN $7 THEN $8 WHEN $9 THEN $10 WHEN $11 TH

Calls 21, mean 11.85 ms.

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

## 14. SELECT * FROM suppliers WHERE id = $1

Calls 24937, mean 0.01 ms.

```
Index Scan using suppliers_pkey on suppliers
  Index Cond: (id = $1)
```

## 15. SELECT state, count(DISTINCT id) AS events, sum(severity) AS weighted_events FROM (SELECT DISTINCT id, state, severity FROM ( SELECT e.id, e.source, e.event_typ

Calls 21, mean 10.31 ms.

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

## 16. SELECT registry_id, name, address, city, state, postal_code, latitude, longitude, industry_code, source, link_confidence FROM facilities WHERE company_id = $1 O

Calls 24937, mean 0.01 ms.

```
Limit
  ->  Sort
        Sort Key: state, city, name
        ->  Index Scan using facilities_company on facilities
              Index Cond: (company_id = $1)
```

## 17. SELECT CASE WHEN source = $4 THEN $5 ELSE $6 END AS source_class, count(DISTINCT id) AS events FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reporte

Calls 21, mean 9.41 ms.

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

## 18. SELECT count(DISTINCT id) AS n FROM ( SELECT e.id, e.source, e.event_type, e.severity, e.reported_at, e.title, e.state, e.latitude, e.longitude, s.id AS supplie

Calls 21, mean 8.19 ms.

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

## 19. SELECT parent_id, child_id FROM company_relationships WHERE parent_id = ANY($1) AND rel_type IN ($2,$3,$4)

Calls 30877, mean 0.00 ms.

```
Index Only Scan using company_relationships_parent_id_child_id_rel_type_source_key on company_relationships
  Index Cond: ((parent_id = ANY ($1)) AND (rel_type = ANY (ARRAY[$2, $3, $4])))
```

## 20. SELECT id, canonical_name, legal_form, cik, lei, wikidata_qid, tickers, sic_code, state_of_incorporation, hq_city, hq_state, hq_country, is_public, status, desc

Calls 24937, mean 0.01 ms.

```
Index Scan using companies_pkey on companies
  Index Cond: (id = $1)
```
