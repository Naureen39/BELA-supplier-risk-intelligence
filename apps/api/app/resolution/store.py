"""Persist link results: `mentions` and `link_candidates` (transparency panel data).

Written against the Phase 2 schema (migration 0002). Not exercised by the offline test suite, which
has no PostgreSQL server; run `make db-test` against a database before relying on it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.resolution.models import MentionLink, Resolution


def persist_mention_links(conn: Any, article_id: int, links: Sequence[MentionLink]) -> list[int]:
    """Insert mentions and every candidate considered. Returns mention ids."""
    ids: list[int] = []
    model_version = None
    for link in links:
        m = link.mention
        model_version = ",".join(f"{k}={v}" for k, v in sorted(link.model_versions.items())) or None
        decision = {"accepted": "accepted", "exact_id": "accepted", "review": "review",
                    "nil": "nil"}[link.route.value]
        row = conn.execute(
            "INSERT INTO mentions (article_id, span_start, span_end, surface, qid, md_score, "
            "el_score, route, decision, model_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING id",
            (article_id, m.start, m.end, m.surface, m.qid, m.md_score, m.el_score, link.method,
             decision, model_version),
        ).fetchone()
        mention_id = int(row[0])
        ids.append(mention_id)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO link_candidates (mention_id, rank, company_id, bela_score, "
                "blink_score, splink_score, llm_label) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [
                    (mention_id, rank, c.company_id,
                     m.el_score if "bela" in c.sources else None, c.blink_score,
                     c.splink_weight or None,
                     link.llm_label if c.company_id == link.company_id else None)
                    for rank, c in enumerate(link.candidates, start=1)
                ],
            )
    _ = model_version
    return ids


def update_facility_links(conn: Any, results: Sequence[tuple[str, Resolution]]) -> int:
    """Set `facilities.company_id` for accepted resolutions. Review and NIL results are left
    unlinked so records are never silently attached. `results` holds (registry_id, resolution)."""
    updated = 0
    for registry_id, res in results:
        if res.route.value not in ("accepted", "exact_id") or res.company_id is None:
            continue
        conn.execute(
            "UPDATE facilities SET company_id = %s, link_method = %s, link_confidence = %s "
            "WHERE registry_id = %s",
            (res.company_id, res.method, res.probability, registry_id),
        )
        updated += 1
    return updated
