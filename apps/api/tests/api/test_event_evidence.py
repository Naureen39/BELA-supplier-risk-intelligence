"""Event detail: evidence with marked company names, and the suppliers an event reaches."""

from __future__ import annotations

import uuid

from conftest import Api, World, seed_catalog


def _news_event(world: World, company_id: int, summary: str) -> int:
    with world.container.db.system() as conn:
        ev = conn.execute(
            "INSERT INTO events (source, source_id, event_type, severity, reported_at, title, summary, state) "
            "VALUES ('news', %s, 'plant_incident', 3, now(), 'Fire reported', %s, 'TX') RETURNING id",
            (uuid.uuid4().hex, summary)).fetchone()["id"]
        conn.execute("INSERT INTO event_entities (event_id, company_id, role, method, score, route) "
                     "VALUES (%s,%s,'mentioned','hybrid',0.9,'accepted')", (ev, company_id))
    return int(ev)


def test_news_evidence_marks_the_company_name(world: World) -> None:
    ids = seed_catalog(world)
    child = ids["Northgate Metals of Texas LLC|TX"]
    text = "A fire at the Houston site of Northgate Metals of Texas LLC was contained."
    ev = _news_event(world, child, text)
    body = Api(world).as_role("a", "viewer").get(f"/events/{ev}").json()
    e = body["evidence"]
    assert e["kind"] == "news" and e["text"] == text
    [span] = e["spans"]
    assert text[span["start"]:span["end"]] == "Northgate Metals of Texas LLC" and span["company_id"] == child


def test_event_reaches_a_parent_supplier_with_the_path(world: World) -> None:
    ids = seed_catalog(world)
    parent, child = ids["Northgate Metals Corporation|PA"], ids["Northgate Metals of Texas LLC|TX"]
    ev = _news_event(world, child, "Incident at Northgate Metals of Texas LLC.")
    mgr = Api(world).as_role("a", "manager")
    sid = mgr.post("/suppliers", json={"name": "Northgate Metals Corporation", "state": "PA"}).json()["id"]
    reached = mgr.get(f"/events/{ev}").json()["reaches_suppliers"]
    assert [(r["supplier_id"], r["relation"]) for r in reached] == [(sid, "subsidiary")]
    assert reached[0]["path"] == ["Northgate Metals of Texas LLC", "Northgate Metals Corporation"]
    # An event at the parent reaches a supplier that is the subsidiary.
    ev2 = _news_event(world, parent, "News about Northgate Metals Corporation.")
    sub = mgr.post("/suppliers", json={"name": "Northgate Metals of Texas", "state": "TX"}).json()["id"]
    rows = {r["supplier_id"]: r["relation"] for r in mgr.get(f"/events/{ev2}").json()["reaches_suppliers"]}
    assert rows == {sid: "direct", sub: "parent"}


def test_regulator_evidence_shows_record_fields_and_other_tenants_see_no_suppliers(world: World) -> None:
    ids = seed_catalog(world)
    company = ids["Harborline Foods, Inc.|OH"]
    ev = _news_event(world, company, "Harborline Foods, Inc. issued a notice.")
    with world.container.db.system() as conn:
        conn.execute("UPDATE events SET source = 'osha', raw_ref = %s::jsonb WHERE id = %s",
                     ('{"status": "contested"}', ev))
    Api(world).as_role("a", "manager").post("/suppliers", json={"name": "Harborline Foods", "state": "OH"})
    other = Api(world).as_role("b", "manager").get(f"/events/{ev}").json()
    assert other["evidence"]["kind"] == "record" and other["evidence"]["fields"] == {"status": "contested"}
    assert other["reaches_suppliers"] == []  # tenant B has no suppliers: row level security
