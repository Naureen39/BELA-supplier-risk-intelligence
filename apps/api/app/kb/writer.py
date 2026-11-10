"""Write a built canonical company set into PostgreSQL."""

from __future__ import annotations

import json
from collections.abc import Iterable

import psycopg

from app.kb.canonical import CanonicalBuilder, Conflict, Relationship
from app.kb.normalize import normalize_name
from app.kb.staging import SourceFacility

_DEPENDENT_TABLES = ("event_entities", "link_candidates", "suppliers", "risk_score_components")


def connect(url: str) -> psycopg.Connection:
    """Open a psycopg connection from a SQLAlchemy-style URL."""
    return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"))


def assert_safe_to_rebuild(conn: psycopg.Connection) -> None:
    """The knowledge base is rebuilt from sources; refuse if downstream data depends on it."""
    for table in _DEPENDENT_TABLES:
        row = conn.execute(f"SELECT EXISTS (SELECT 1 FROM {table})").fetchone()
        if row and row[0]:
            raise RuntimeError(f"{table} holds rows that reference companies; rebuild refused")


def reset_knowledge(conn: psycopg.Connection) -> None:
    assert_safe_to_rebuild(conn)
    conn.execute(
        "TRUNCATE canonical_conflicts, entity_embeddings, source_records, facilities, "
        "company_relationships, company_aliases, companies RESTART IDENTITY CASCADE"
    )


def write_companies(conn: psycopg.Connection, builder: CanonicalBuilder) -> dict[int, int]:
    """Insert companies, aliases, and source links. Returns builder index -> database id."""
    ids = {c.index: c.index + 1 for c in builder.companies}
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO companies (id, canonical_name, normalized_name, legal_form, cik, lei, "
            "wikidata_qid, tickers, sic_code, state_of_incorporation, hq_city, hq_state, "
            "hq_country, is_public, status, description) OVERRIDING SYSTEM VALUE "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [
                (
                    ids[c.index], c.name, c.normalized, c.legal_form, c.cik, c.lei, c.qid,
                    c.tickers, c.sic, c.state, c.city, c.state, c.country, c.is_public,
                    c.status, c.description,
                )
                for c in builder.companies
            ],
        )
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('companies','id'), "
            "GREATEST((SELECT COALESCE(max(id),1) FROM companies),1))"
        )
        cur.executemany(
            "INSERT INTO company_aliases (company_id, alias, alias_type, normalized, source) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            [
                (ids[c.index], alias, alias_type, norm, "canonical_build")
                for c in builder.companies
                for (norm, alias_type), alias in c.aliases.items()
            ],
        )
        cur.executemany(
            "INSERT INTO source_records (source, source_key, name, state, company_id, method, score) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            [
                (k.source, k.source_key, k.name, k.state, ids[k.canonical], k.method, k.score)
                for k in builder.links
            ],
        )
    return ids


def write_relationships(
    conn: psycopg.Connection, relationships: Iterable[Relationship], ids: dict[int, int]
) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO company_relationships (parent_id, child_id, rel_type, ownership_share, "
            "source, as_of) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            [
                (ids[r.parent], ids[r.child], r.rel_type, r.share, r.source, r.as_of)
                for r in relationships
            ],
        )


def write_conflicts(
    conn: psycopg.Connection, conflicts: Iterable[Conflict], ids: dict[int, int]
) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO canonical_conflicts (kind, company_ids, details) VALUES (%s,%s,%s)",
            [
                (c.kind, [ids[i] for i in c.canonical], json.dumps(c.details))
                for c in conflicts
            ],
        )


def write_facilities(
    conn: psycopg.Connection, builder: CanonicalBuilder, facilities: Iterable[SourceFacility],
    ids: dict[int, int],
) -> None:
    """Insert facilities; link to a company only on exact normalized name plus state."""
    rows = []
    for f in facilities:
        target = builder.find_exact(f.name, f.state)
        rows.append(
            (
                f.registry_id, f.name, normalize_name(f.name), f.address, f.city, f.state,
                f.postal_code, f.latitude, f.longitude, f.industry_code, f.source,
                ids[target] if target is not None else None,
                "exact_name_state" if target is not None else None,
                1.0 if target is not None else None,
            )
        )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO facilities (registry_id, name, normalized_name, address, city, state, "
            "postal_code, latitude, longitude, industry_code, source, company_id, link_method, "
            "link_confidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (registry_id) DO NOTHING",
            rows,
        )
