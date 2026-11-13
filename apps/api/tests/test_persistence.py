"""Phase 3 and 4 persistence code against a real PostgreSQL (first time it runs on a database)."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
from alembic import command
from alembic.config import Config
from app.events.attach import EventEntityLink
from app.events.risk import RiskConfig, ScoredEvent, score_supplier
from app.events.schema import EntityRef, NormalizedEvent
from app.events.store import insert_score, replace_event_entities, upsert_events
from app.resolution.models import Mention, MentionLink, Resolution, Route, ScoredCandidate
from app.resolution.store import persist_mention_links, update_facility_links
from conftest import API_DIR


def _company(conn: psycopg.Connection, name: str) -> int:
    return conn.execute(
        "INSERT INTO companies (canonical_name, normalized_name) VALUES (%s,%s) RETURNING id",
        (name, name.lower())).fetchone()[0]


def _event(sid: str, title: str = "OSHA citation record") -> NormalizedEvent:
    return NormalizedEvent(source="osha", source_id=sid, source_class="regulator",
                           event_type="workplace_safety", severity=3,
                           reported_at=datetime(2026, 1, 1, tzinfo=UTC), title=title,
                           entities=[EntityRef("Acme", "operator")], state="OH",
                           raw_ref={"penalty": 20000})


def test_event_upsert_links_candidates_and_scores(db_url: str) -> None:
    with psycopg.connect(db_url.replace("+psycopg", "")) as conn:
        cid = _company(conn, "Acme Corp")
        ids = upsert_events(conn, [_event("1"), _event("2")])
        assert upsert_events(conn, [_event("1", "Updated title")]) == {("osha", "1"): ids[("osha", "1")]}
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 2
        assert conn.execute("SELECT title FROM events WHERE source_id = '1'").fetchone()[0] == "Updated title"

        link = EventEntityLink(("osha", "1"), "Acme", "operator", cid, "hybrid", 0.95, Route.ACCEPTED,
                               [(cid, 0.95)])
        replace_event_entities(conn, ids, [link])
        replace_event_entities(conn, ids, [link])  # rewrite is idempotent
        assert conn.execute("SELECT count(*), max(route) FROM event_entities").fetchone() == (1, "accepted")
        assert conn.execute("SELECT count(*) FROM link_candidates").fetchone()[0] == 1

        tenant = conn.execute("INSERT INTO tenants (name) VALUES ('T') RETURNING id").fetchone()[0]
        sup = conn.execute("INSERT INTO suppliers (tenant_id, uploaded_name) VALUES (%s,'Acme') RETURNING id",
                           (tenant,)).fetchone()[0]
        score = score_supplier([ScoredEvent(0, "workplace_safety", 3, "regulator",
                                            datetime(2026, 1, 1, tzinfo=UTC), 0.95, "direct")],
                               datetime(2026, 1, 2, tzinfo=UTC), RiskConfig())
        sid = insert_score(conn, str(tenant), str(sup), score, {0: ids[("osha", "1")]})
        row = conn.execute("SELECT score, level FROM risk_scores WHERE id = %s", (sid,)).fetchone()
        assert float(row[0]) == score.score and row[1] == score.level
        assert conn.execute("SELECT count(*) FROM risk_score_components").fetchone()[0] == 1


def test_mention_and_facility_persistence(db_url: str) -> None:
    with psycopg.connect(db_url.replace("+psycopg", "")) as conn:
        cid = _company(conn, "Acme Corp")
        art = conn.execute("INSERT INTO articles (url, title) VALUES ('https://n.example/a','t') RETURNING id"
                           ).fetchone()[0]
        m = Mention("a", 0, 4, "Acme", "Acme had a fire.", "Q1", 0.9, 0.8)
        cand = ScoredCandidate(cid, "Acme Corp", {"bela"}, 0.8, blink_score=None, splink_weight=2.0)
        link = MentionLink(m, cid, Route.ACCEPTED, "bela", 0.9, [cand], model_versions={"nel": "x"})
        nil = MentionLink(m, None, Route.NIL, "no_candidates", 0.0, [])
        ids = persist_mention_links(conn, art, [link, nil])
        assert len(ids) == 2
        assert conn.execute("SELECT decision, route FROM mentions ORDER BY id").fetchall() == [
            ("accepted", "bela"), ("nil", "no_candidates")]
        assert conn.execute("SELECT rank, company_id FROM link_candidates").fetchall() == [(1, cid)]

        conn.execute("INSERT INTO facilities (registry_id, name, normalized_name, source) "
                     "VALUES ('R1','Acme Plant','acme plant','epa'), ('R2','Other','other','epa')")
        ok = Resolution("R1", cid, Route.ACCEPTED, "hybrid", 0.97, 0.5, [], "v1")
        held = Resolution("R2", cid, Route.REVIEW, "hybrid", 0.7, 0.1, [], "v1")
        assert update_facility_links(conn, [("R1", ok), ("R2", held)]) == 1
        assert conn.execute("SELECT registry_id, company_id FROM facilities WHERE company_id IS NOT NULL"
                            ).fetchall() == [("R1", cid)]


def test_migration_0004_downgrades_cleanly(db_url: str) -> None:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    command.downgrade(cfg, "0003")
    with psycopg.connect(db_url.replace("+psycopg", "")) as conn:
        assert conn.execute("SELECT to_regclass('password_reset_tokens')").fetchone()[0] is None
        assert conn.execute("SELECT count(*) FROM pg_policies").fetchone()[0] == 0
    command.upgrade(cfg, "head")
