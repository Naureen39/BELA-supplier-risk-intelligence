"""PostgreSQL persistence for events, links, and scores (migration 0002 schema).

Not exercised by the offline test suite, which has no PostgreSQL server. Run `make db-test`
against a database before relying on it. Reloads are idempotent through UNIQUE (source, source_id).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from app.events.attach import EventEntityLink
from app.events.risk import SupplierScore
from app.events.schema import NormalizedEvent


def _rid(row: Any) -> int:
    """First column of a RETURNING row, for tuple or dict rows."""
    return int(next(iter(row.values())) if isinstance(row, dict) else row[0])


def upsert_events(conn: Any, events: Sequence[NormalizedEvent]) -> dict[tuple[str, str], int]:
    ids: dict[tuple[str, str], int] = {}
    for ev in events:
        row = conn.execute(
            "INSERT INTO events (source, source_id, event_type, severity, occurred_at, reported_at, "
            "title, summary, url, raw_ref, state, city, latitude, longitude, rules_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s) "
            "ON CONFLICT (source, source_id) DO UPDATE SET event_type = EXCLUDED.event_type, "
            "severity = EXCLUDED.severity, title = EXCLUDED.title, summary = EXCLUDED.summary, "
            "raw_ref = EXCLUDED.raw_ref, rules_version = EXCLUDED.rules_version RETURNING id",
            (ev.source, ev.source_id, ev.event_type, ev.severity, ev.occurred_at, ev.reported_at,
             ev.title, ev.summary, ev.url, json.dumps(ev.raw_ref), ev.state, ev.city, ev.latitude,
             ev.longitude, ev.rules_version),
        ).fetchone()
        ids[(ev.source, ev.source_id)] = int(_rid(row))
    return ids


def replace_event_entities(conn: Any, ids: dict[tuple[str, str], int],
                           links: Sequence[EventEntityLink]) -> None:
    """Rewrite entity links for the given events (keeps the transparency data in sync)."""
    for event_id in set(ids.values()):
        conn.execute("DELETE FROM event_entities WHERE event_id = %s", (event_id,))
    for link in links:
        route = {"accepted": "accepted", "exact_id": "accepted", "review": "review",
                 "nil": "nil"}[link.route.value]
        row = conn.execute(
            "INSERT INTO event_entities (event_id, company_id, role, method, score, route) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (ids[link.event_key], link.company_id, link.role, link.method,
             min(max(link.score, 0.0), 1.0), route),
        ).fetchone()
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO link_candidates (event_entity_id, rank, company_id, splink_score) "
                "VALUES (%s,%s,%s,%s)",
                [(int(_rid(row)), rank, cid, p) for rank, (cid, p) in enumerate(link.candidates, 1)],
            )


def insert_score(conn: Any, tenant_id: str, supplier_id: str, score: SupplierScore,
                 event_db_ids: dict[int, int]) -> int:
    """`event_db_ids` maps pipeline event indexes (component.event_id) to events.id."""
    row = conn.execute(
        "INSERT INTO risk_scores (tenant_id, supplier_id, score, level, config_version) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (tenant_id, supplier_id, score.score, score.level, score.config_version)).fetchone()
    score_id = int(_rid(row))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO risk_score_components (risk_score_id, event_id, category, severity_weight, "
            "recency_decay, link_confidence, relation_weight, source_reliability, event_impact) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(score_id, event_db_ids[c.event_id], c.category, c.severity_weight, c.recency_decay,
              c.link_confidence, c.relation_weight, c.source_reliability, c.capped_impact)
             for c in score.components])
    return score_id
