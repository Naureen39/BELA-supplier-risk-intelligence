from __future__ import annotations

import asyncio
import io
import json
import os
import uuid
from typing import Any

import pytest
from conftest import Api, World, seed_catalog, seed_event

CSV = (
    b"Supplier Name,State,City,Tax ID,Tier\n"
    b"HARBORLINE FOODS INC,OH,Columbus,12-3456789,1\n"
    b"Cobalt Ridge Logistics,,,,2\n"
    b"Zyxwv Quantum Bakery,CA,,,3\n"
    b",,,,\n"
    b"=HYPERLINK(\"http://x\"),,,,3\n"
)


def upload(api: Api, data: bytes = CSV, key: str | None = None, **form: Any) -> Any:
    headers = {"Idempotency-Key": key} if key else {}
    return api.post("/uploads", files={"file": ("suppliers.csv", io.BytesIO(data), "text/csv")},
                    data=form, headers=headers)


def test_upload_resolves_routes_and_reports_partial_failures(world: World) -> None:
    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    r = upload(api)
    assert r.status_code == 202, r.text
    up = api.get(f"/uploads/{r.json()['id']}").json()
    assert up["status"] == "complete" and up["row_count"] == 4
    assert up["errors"] == [{"row": 5, "reason": "missing supplier name"}]
    assert up["auto_resolved"] >= 1 and up["needs_review"] >= 1 and up["unresolved"] >= 1
    assert up["auto_resolved"] + up["needs_review"] + up["unresolved"] == 4
    items = {s["uploaded_name"]: s for s in api.get("/suppliers").json()["items"]}
    assert items["HARBORLINE FOODS INC"]["company_name"].startswith("Harborline")
    assert items["Cobalt Ridge Logistics"]["status"] == "needs_review"  # identical twin names
    assert items["Zyxwv Quantum Bakery"]["status"] == "unresolved"
    assert items["HARBORLINE FOODS INC"]["has_sensitive_identifiers"] is True
    assert "12-3456789" not in json.dumps(items)


def test_sensitive_identifiers_are_encrypted_at_rest(world: World) -> None:
    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    upload(api)
    with world.container.db.system() as conn:
        row = conn.execute("SELECT identifiers_encrypted, attributes FROM suppliers "
                           "WHERE identifiers_encrypted IS NOT NULL").fetchone()
        assert b"12-3456789" not in bytes(row["identifiers_encrypted"])
        assert "12-3456789" not in json.dumps(row["attributes"])
        plain = conn.execute("SELECT pgp_sym_decrypt(identifiers_encrypted, %s) AS p FROM suppliers "
                             "WHERE identifiers_encrypted IS NOT NULL",
                             (world.container.cipher.raw_key,)).fetchone()["p"]
    assert "12-3456789" in plain


def test_upload_validation_and_limits(world: World) -> None:
    api = Api(world).as_role("a", "analyst")
    assert upload(api, b"foo,bar\n1,2\n").status_code == 422  # no name column
    assert upload(api, b"\xff\xfe\x00bad").status_code == 422  # not UTF-8
    assert upload(api, b"name\n").status_code == 422  # no rows
    mapped = upload(api, b"Vendor X,Region\nAcme Corp,OH\n", mapping=json.dumps({"name": "Vendor X"}))
    assert mapped.status_code == 202 and mapped.json()["mapping"]["name"] == "Vendor X"
    wrong_type = api.post("/uploads", files={"file": ("x.exe", io.BytesIO(b"name\na\n"), "text/csv")})
    assert wrong_type.status_code == 415
    api.world.container.settings.__class__  # noqa: B018
    many = ("name\n" + "Acme\n" * 10_001).encode()
    assert upload(api, many).status_code == 422
    viewer = Api(world).as_role("a", "viewer")
    assert upload(viewer).status_code == 403


def test_upload_idempotency_key_returns_same_upload(world: World) -> None:
    api = Api(world).as_role("a", "analyst")
    first = upload(api, b"name\nAcme Corp\n", key="k-1")
    again = upload(api, b"name\nAcme Corp\nOther Co\n", key="k-1")
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"] and again.json()["idempotent_replay"] is True
    with world.container.db.system() as conn:
        assert conn.execute("SELECT count(*) AS n FROM suppliers").fetchone()["n"] == 1


def test_review_queue_decisions_and_conflicts(world: World) -> None:
    ids = seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    upload(api, b"name\nCobalt Ridge Logistics\nCobalt Ridge Logistics Co\n")
    reviews = api.get("/reviews").json()["items"]
    assert len(reviews) == 2 and len(reviews[0]["candidates"]) >= 2
    assert api.patch(f"/reviews/{reviews[0]['id']}", json={"action": "accept"}).status_code == 200
    other = ids["Cobalt Ridge Logistics Co.|NV"]
    r = api.patch(f"/reviews/{reviews[1]['id']}", json={"action": "choose_other", "company_id": other})
    assert r.json()["company_id"] == other
    assert api.patch(f"/reviews/{reviews[1]['id']}", json={"action": "accept"}).status_code == 409
    assert api.patch(f"/reviews/{uuid.uuid4()}", json={"action": "accept"}).status_code == 404
    bad = api.patch(f"/reviews/{reviews[0]['id']}", json={"action": "choose_other", "company_id": 999999})
    assert bad.status_code in (409, 422)
    assert api.get("/reviews").json()["items"] == []
    done = {s["uploaded_name"]: s for s in api.get("/suppliers?status=resolved").json()["items"]}
    assert len(done) == 2


def test_supplier_events_include_parent_roll_up_path(world: World) -> None:
    ids = seed_catalog(world)
    child, parent = ids["Northgate Metals of Texas LLC|TX"], ids["Northgate Metals Corporation|PA"]
    seed_event(world, child, title="OSHA citation record for the Texas subsidiary")
    seed_event(world, ids["Cobalt Ridge Logistics Co.|NV"], title="unrelated")
    seed_event(world, parent, route="review", title="held for platform review")
    api = Api(world).as_role("a", "analyst")
    sup = api.post("/suppliers", json={"name": "Northgate Metals Corporation", "state": "PA",
                                       "city": "Pittsburgh"}).json()
    assert sup["resolution"]["company_id"] == parent
    events = api.get(f"/suppliers/{sup['id']}/events").json()
    assert [e["title"] for e in events["items"]] == ["OSHA citation record for the Texas subsidiary"]
    assert events["items"][0]["relation"] == "subsidiary_event_to_parent"
    assert events["items"][0]["path"] == [child, parent] and "not statements of fault" in events["disclaimer"]


def test_events_feed_hides_unreviewed_links(world: World) -> None:
    ids = seed_catalog(world)
    visible = seed_event(world, ids["Harborline Foods, Inc.|OH"], title="visible")
    hidden = seed_event(world, ids["Harborline Foods, Inc.|OH"], route="review", title="hidden")
    api = Api(world).as_role("a", "viewer")
    titles = [e["title"] for e in api.get("/events").json()["items"]]
    assert titles == ["visible"]
    assert api.get(f"/events/{hidden}").status_code == 404
    detail = api.get(f"/events/{visible}").json()
    assert detail["entities"][0]["candidates"][0]["rank"] == 1
    assert api.get("/events?min_severity=4").json()["items"] == []


def test_companies_family_graph_and_search(world: World) -> None:
    ids = seed_catalog(world)
    parent, child = ids["Northgate Metals Corporation|PA"], ids["Northgate Metals of Texas LLC|TX"]
    api = Api(world).as_role("a", "viewer")
    found = api.get("/companies/search?q=northgate metals").json()["items"]
    assert {f["id"] for f in found} >= {parent, child}
    assert api.get("/companies/search?q=HLF").status_code == 200
    fam = api.get(f"/companies/{parent}/family").json()
    assert fam["subsidiaries"][0]["child_id"] == child and fam["subsidiaries"][0]["source"] == "gleif"
    assert api.get(f"/companies/{child}/family").json()["parents"][0]["parent_id"] == parent
    g = api.get(f"/graph/neighbors?company_id={parent}&depth=2").json()
    assert {n["id"] for n in g["nodes"]} == {parent, child} and g["edges"][0]["source"] == "gleif"
    path = api.get(f"/graph/path?source={parent}&target={child}").json()
    assert path["found"] and [n["id"] for n in path["path"]] == [parent, child]
    other = ids["Harborline Foods, Inc.|OH"]
    assert api.get(f"/graph/path?source={parent}&target={other}").json()["found"] is False
    assert api.get("/companies/999999").status_code == 404
    assert api.get(f"/graph/neighbors?company_id={parent}&depth=9").status_code == 422


def _alert(world: World, tenant_id: str, supplier_id: str, dedup: str = "k1") -> str:
    with world.container.db.system() as conn:
        return str(conn.execute(
            "INSERT INTO alerts (tenant_id, supplier_id, kind, detail, dedup_key) "
            "VALUES (%s,%s,'high_severity_event','test',%s) RETURNING id",
            (tenant_id, supplier_id, dedup)).fetchone()["id"])


def test_alert_lifecycle_rules_and_history(world: World) -> None:
    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    sid = api.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"}).json()["id"]
    aid = _alert(world, world.tenant_a, sid)
    assert api.get("/alerts").json()["items"][0]["id"] == aid
    assert api.patch(f"/alerts/{aid}", json={"status": "dismissed"}).status_code == 422  # reason needed
    assert api.patch(f"/alerts/{aid}", json={"status": "in_review",
                                             "assignee_id": world.users[("a", "manager")]}).status_code == 200
    assert api.post(f"/alerts/{aid}/comments", json={"comment": "Checking the source record."}).status_code == 201
    assert api.patch(f"/alerts/{aid}", json={"status": "dismissed", "reason": "Different company"}).status_code == 200
    assert api.patch(f"/alerts/{aid}", json={"status": "escalated"}).status_code == 409
    history = [h["change"] for h in api.get(f"/alerts/{aid}/history").json()["items"]]
    assert history == ["status:in_review", "assigned", "comment", "status:dismissed"]
    assert api.patch(f"/alerts/{aid}", json={"assignee_id": world.users[("b", "analyst")]}).status_code == 422
    viewer = Api(world).as_role("a", "viewer")
    assert viewer.patch(f"/alerts/{aid}", json={"status": "in_review"}).status_code == 403
    assert viewer.get("/alerts?status=dismissed").json()["items"][0]["id"] == aid
    other = Api(world).as_role("b", "analyst")
    assert other.patch(f"/alerts/{aid}", json={"status": "in_review"}).status_code == 404

    mgr = Api(world).as_role("a", "manager")
    rule = mgr.post("/rules", json={"name": "Severe PA", "min_severity": 3, "states": ["pa"],
                                    "channels": ["in_app", "webhook"], "webhook_url": "https://hooks.example/x"})
    assert rule.status_code == 201 and rule.json()["states"] == ["PA"]
    assert mgr.post("/rules", json={"name": "bad", "channels": ["webhook"]}).status_code == 422
    assert mgr.post("/rules", json={"name": "bad", "webhook_url": "http://insecure"}).status_code == 422
    assert mgr.patch(f"/rules/{rule.json()['id']}", json={"is_active": False}).json()["is_active"] is False
    assert Api(world).as_role("b", "manager").get("/rules").json()["items"] == []


def test_pagination_cursors(world: World) -> None:
    api = Api(world).as_role("a", "analyst")
    for i in range(5):
        assert api.post("/suppliers", json={"name": f"Pager Supplier {i}"}).status_code == 201
    seen, cursor = [], None
    for _ in range(5):
        r = api.get("/suppliers", params={"limit": 2, **({"cursor": cursor} if cursor else {})}).json()
        seen += [s["uploaded_name"] for s in r["items"]]
        cursor = r["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == [f"Pager Supplier {i}" for i in range(5)] and len(set(seen)) == 5
    assert api.get("/suppliers?cursor=garbage").status_code == 400
    assert api.get("/suppliers", params={"limit": 100000}).status_code == 200


def test_csv_export_neutralizes_formulas(world: World) -> None:
    api = Api(world).as_role("a", "analyst")
    upload(api, b'name\n"=HYPERLINK(""http://x"")"\n+cmd\nSafe Co\n')
    r = api.get("/suppliers?format=csv")
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.splitlines()
    assert any("'=HYPERLINK" in ln for ln in lines) and any("'+cmd" in ln for ln in lines)
    assert not any(ln.split(",")[1].startswith(("=", "+")) for ln in lines[1:])


def test_admin_users_and_session_revocation(world: World) -> None:
    admin = Api(world).as_role("a", "tenant_admin")
    r = admin.post("/admin/users", json={"email": "new.analyst@a.example", "role": "analyst"})
    assert r.status_code == 201
    assert admin.post("/admin/users", json={"email": "NEW.analyst@a.example", "role": "viewer"}).status_code == 409
    assert admin.post("/admin/users", json={"email": "x@a.example", "role": "platform_admin"}).status_code == 422
    assert any(m[0] == "new.analyst@a.example" for m in world.mailer.outbox)  # invitation
    victim = Api(world).as_role("a", "viewer")
    uid = world.users[("a", "viewer")]
    assert victim.get("/suppliers").status_code == 200
    assert admin.patch(f"/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert victim.get("/suppliers").status_code == 401  # access token dies with the account
    me = world.users[("a", "tenant_admin")]
    assert admin.patch(f"/admin/users/{me}", json={"role": "viewer"}).status_code == 409
    assert admin.patch(f"/admin/users/{world.users[('b', 'viewer')]}", json={"role": "analyst"}).status_code == 404
    assert len(admin.get("/admin/users").json()["items"]) == 5  # tenant A only


def test_role_change_takes_effect_immediately(world: World) -> None:
    analyst = Api(world).as_role("a", "analyst")
    assert analyst.post("/resolve", json={"name": "Acme"}).status_code == 200
    with world.container.db.system() as conn:
        conn.execute("UPDATE users SET role = 'viewer' WHERE id = %s", (world.users[("a", "analyst")],))
    assert analyst.post("/resolve", json={"name": "Acme"}).status_code == 403


def test_risk_config_versions_and_bounds(world: World) -> None:
    admin = Api(world).as_role("a", "tenant_admin")
    assert admin.get("/admin/risk-config").json()["config"]["impact_cap"] == 0.6
    ok = admin.put("/admin/risk-config", json={"impact_cap": 0.5, "half_life_news_days": 21})
    assert ok.status_code == 200 and ok.json()["version"] == 2
    assert admin.put("/admin/risk-config", json={"impact_cap": 0.95}).status_code == 422
    assert admin.put("/admin/risk-config", json={"severity_weights": [0.5, 0.2, 0.3, 0.1]}).status_code == 422
    assert admin.get("/admin/risk-config").json()["config"]["half_life_news_days"] == 21
    assert [h["version"] for h in admin.get("/admin/risk-config/history").json()["items"]] == [2]
    assert Api(world).as_role("b", "tenant_admin").get("/admin/risk-config").json()["version"] == 1


def test_tenant_settings_and_mfa_enforcement(world: World) -> None:
    admin = Api(world).as_role("a", "tenant_admin")
    assert admin.patch("/tenants/current", json={"require_mfa": True, "retention_days": 365}).status_code == 200
    assert admin.get("/tenants/current").json()["retention_days"] == 365
    assert admin.patch("/tenants/current", json={"retention_days": 1}).status_code == 422
    r = Api(world).login("a", "viewer")  # tenant now requires MFA for everyone
    assert r.json()["status"] == "mfa_enrollment_required"
    assert Api(world).as_role("b", "analyst").get("/tenants/current").json()["name"] == "Tenant B"


def test_audit_log_chain_visibility_and_tamper_detection(world: World) -> None:
    admin = Api(world).as_role("a", "tenant_admin")
    admin.post("/admin/api-keys", json={"name": "k", "scopes": ["view"]})
    admin.patch("/tenants/current", json={"retention_days": 400})
    other = Api(world).as_role("b", "tenant_admin")
    other.patch("/tenants/current", json={"retention_days": 500})
    entries = admin.get("/admin/audit").json()["items"]
    assert entries and all(e["tenant_id"] == world.tenant_a for e in entries)  # no cross-tenant view
    actions = {e["action"] for e in entries}
    assert {"api_key.created", "tenant.settings_changed", "auth.mfa_verified"} <= actions
    assert "key" not in json.dumps([e["detail"] for e in entries if e["action"] == "api_key.created"][0])
    assert admin.get("/admin/audit?action=api_key.created").json()["items"][0]["action"] == "api_key.created"
    ok = admin.get("/admin/audit/verify").json()
    assert ok["ok"] is True and ok["rows_checked"] >= 6
    with world.container.db.system() as conn:
        conn.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change")
        conn.execute("UPDATE audit_log SET action = 'forged' WHERE seq = (SELECT min(seq) + 1 FROM audit_log)")
        conn.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change")
    bad = admin.get("/admin/audit/verify").json()
    assert bad["ok"] is False and bad["first_bad_seq"] is not None
    assert Api(world).as_role("a", "manager").get("/admin/audit").status_code == 403


def test_audit_log_is_append_only_for_the_app_role(world: World) -> None:
    import psycopg
    from app.core import audit

    audit.record(world.container.db, action="test.event")
    with world.container.db.system() as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("UPDATE audit_log SET action = 'x'")
    with world.container.db.system() as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM audit_log")


def test_reports_sources_analytics_billing(world: World) -> None:
    ids = seed_catalog(world)
    seed_event(world, ids["Harborline Foods, Inc.|OH"])
    with world.container.db.system() as conn:
        conn.execute("INSERT INTO plans (code, name, monthly_price, supplier_limit) VALUES ('starter','Starter',499,250)")
        conn.execute("INSERT INTO subscriptions (tenant_id, plan_code, billing_cycle, price, started_on) "
                     "VALUES (%s,'starter','monthly',499,'2026-01-01')", (world.tenant_a,))
        conn.execute("INSERT INTO invoices (tenant_id, period_month, issued_on, due_on, status, total) "
                     "VALUES (%s,'2026-09-01','2026-09-01','2026-09-30','paid',499)", (world.tenant_a,))
    mgr = Api(world).as_role("a", "manager")
    sid = mgr.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"}).json()["id"]
    rep = mgr.post(f"/reports/supplier/{sid}")
    assert rep.status_code == 202 and rep.json()["status"] == "queued" and "fault" in rep.json()["disclaimer"]
    assert mgr.get(f"/reports/{rep.json()['id']}").json()["kind"] == "supplier"
    assert mgr.post(f"/reports/supplier/{uuid.uuid4()}").status_code == 404
    assert Api(world).as_role("b", "manager").get(f"/reports/{rep.json()['id']}").status_code == 404
    src = mgr.get("/sources").json()
    assert src["counts"]["companies"] == 5 and src["event_sources"][0]["source"] == "osha"
    assert "US" in src["coverage_note"]
    port = mgr.get("/analytics/portfolio").json()
    assert port["suppliers_by_status"] and port["events_by_type"] == {"workplace_safety": 1}
    assert "auto_resolution_rate" in mgr.get("/analytics/quality").json()
    assert mgr.get("/analytics/usage").json()["demo_data"] is True
    admin = Api(world).as_role("a", "tenant_admin")
    plan = admin.get("/billing/plan").json()
    assert plan["demo_data"] and plan["plan"]["plan_code"] == "starter" and plan["monitored_suppliers"] == 1
    assert admin.get("/billing/invoices").json()["items"][0]["status"] == "paid"
    assert Api(world).as_role("b", "tenant_admin").get("/billing/invoices").json()["items"] == []


def test_platform_tenants_review_queue_and_revenue(world: World) -> None:
    ids = seed_catalog(world)
    seed_event(world, ids["Harborline Foods, Inc.|OH"], route="review", title="needs platform review")
    pa = Api(world).as_role("platform", "platform_admin")
    created = pa.post("/platform/tenants", json={"name": "Tenant C", "admin_email": "boss@c.example"})
    assert created.status_code == 201 and len(pa.get("/platform/tenants").json()["items"]) == 3
    assert pa.post("/platform/tenants", json={"name": "T", "admin_email": "boss@c.example"}).status_code == 409
    assert any(m[0] == "boss@c.example" for m in world.mailer.outbox)
    queue = pa.get("/platform/review-queue").json()["items"]
    assert queue[0]["title"] == "needs platform review" and queue[0]["candidates"][0]["rank"] == 1
    assert pa.patch(f"/platform/review-queue/{queue[0]['id']}", json={"decision": "accept"}).status_code == 422
    done = pa.patch(f"/platform/review-queue/{queue[0]['id']}",
                    json={"decision": "accept", "company_id": ids["Harborline Foods, Inc.|OH"]})
    assert done.status_code == 200 and pa.get("/platform/review-queue").json()["items"] == []
    assert Api(world).as_role("a", "analyst").get("/events").json()["items"][0]["title"] == "needs platform review"
    with world.container.db.system() as conn:
        conn.execute("INSERT INTO plans (code, name, monthly_price, supplier_limit) VALUES ('pro','Pro',1999,2500)")
        conn.execute("INSERT INTO subscriptions (tenant_id, plan_code, billing_cycle, price, started_on) "
                     "VALUES (%s,'pro','monthly',1999,'2023-11-01')", (world.tenant_a,))
        conn.execute("REFRESH MATERIALIZED VIEW mrr_monthly")
    fin = Api(world).as_role("platform", "finance_analyst")
    summary = fin.get("/platform/revenue/summary").json()
    assert summary["demo_data"] and summary["mrr"] == 1999 and summary["arr"] == 1999 * 12
    assert fin.get("/platform/revenue/mrr?from=2026-01-01").json()["items"]
    assert fin.get("/suppliers").status_code == 403


def test_health_and_readiness(world: World) -> None:
    api = Api(world)
    assert api.get("/health").json() == {"status": "ok"} and api.get("/health/ready").json()["status"] == "ready"


def test_sse_delivers_only_the_tenants_alerts(world: World) -> None:
    from app.events_bus import alert_channel
    from app.routers.alerts import sse_events

    c = world.container

    async def run() -> list[str]:
        out: list[str] = []
        gen = sse_events(c, world.tenant_a, heartbeat=0.05)

        async def consume() -> None:
            async for chunk in gen:
                out.append(chunk)
                if "alert" in chunk and chunk.startswith("event"):
                    return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.15)  # lets a heartbeat through
        await c.broker.publish(alert_channel(world.tenant_b), {"id": "other-tenant"})
        await c.broker.publish(alert_channel(world.tenant_a), {"id": "mine"})
        await asyncio.wait_for(task, 2)
        await gen.aclose()
        return out

    chunks = asyncio.run(run())
    assert chunks[0].startswith(": connected") and any("keep-alive" in x for x in chunks)
    assert chunks[-1] == 'event: alert\ndata: {"id": "mine"}\n\n'
    assert not any("other-tenant" in x for x in chunks)


def test_sse_endpoint_requires_auth_and_view(world: World) -> None:
    assert Api(world).get("/stream/alerts").status_code == 401
    assert Api(world).as_role("platform", "finance_analyst").get("/stream/alerts").status_code == 403


@pytest.mark.skipif(not os.environ.get("VALKEY_URL"), reason="VALKEY_URL not set")
def test_valkey_rate_limiter_and_pubsub() -> None:
    from app.core.ratelimit import ValkeyRateLimiter
    from app.events_bus import ValkeyBroker

    async def run() -> tuple[list[bool], dict[str, Any]]:
        url = os.environ["VALKEY_URL"]
        key = f"t-{uuid.uuid4().hex}"
        lim = ValkeyRateLimiter(url)
        hits = [(await lim.hit(key, 2, 30))[0] for _ in range(4)]
        broker = ValkeyBroker(url)
        got: list[dict[str, Any]] = []

        async def listen() -> None:
            async for m in broker.subscribe(f"ch-{key}"):
                got.append(m)
                return

        task = asyncio.create_task(listen())
        await asyncio.sleep(0.3)
        await broker.publish(f"ch-{key}", {"ok": 1})
        await asyncio.wait_for(task, 3)
        await broker.close()
        return hits, got[0]

    hits, msg = asyncio.run(run())
    assert hits == [True, True, False, False] and msg == {"ok": 1}


def test_alert_creation_is_deduplicated_and_published(world: World) -> None:
    from app.events.monitor import AlertDraft
    from app.events_bus import alert_channel
    from app.services.alerts import create_alerts

    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    sid = api.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"}).json()["id"]
    draft = AlertDraft(sid, "high_severity_event", 7, None, "workplace_safety severity 3")
    c = world.container

    async def run() -> tuple[list[str], list[str], dict[str, Any]]:
        got: list[dict[str, Any]] = []

        async def listen() -> None:
            async for m in c.broker.subscribe(alert_channel(world.tenant_a)):
                got.append(m)
                return

        task = asyncio.create_task(listen())
        await asyncio.sleep(0.05)
        first = await create_alerts(c, world.tenant_a, [(sid, draft)])
        second = await create_alerts(c, world.tenant_a, [(sid, draft)])
        await asyncio.wait_for(task, 2)
        return first, second, got[0]

    first, second, msg = asyncio.run(run())
    assert len(first) == 1 and second == [] and msg["id"] == first[0]
    assert api.get("/alerts").json()["items"][0]["id"] == first[0]
    # A supplier from another tenant cannot receive the alert.
    other = asyncio.run(create_alerts(c, world.tenant_b, [(sid, AlertDraft(sid, "threshold_crossing", None, None, "x"))]))
    assert other == []
