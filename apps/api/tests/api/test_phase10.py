"""Phase 10: retries, the dead letter queue, graceful degradation, company search, and the new indexes."""

from __future__ import annotations

import httpx
import psycopg
import pytest
from app.core.resilience import dead_letter, retry_call
from app.resolution.clients import ServiceUnavailable
from app.services import notify
from app.services import resolution as svc
from conftest import Api, World, seed_catalog
from test_phase6 import Hooks, _setup_alert, run


def _dead(world: World) -> list[dict]:
    with world.container.db.system() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM dead_letters ORDER BY id").fetchall()]


# ---------------------------------------------------------------------------- retry helper
def test_retry_call_backs_off_and_gives_up() -> None:
    delays: list[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("down")
        return "ok"

    assert retry_call(flaky, attempts=3, base_delay=1.0, sleep=delays.append) == "ok"
    assert len(delays) == 2 and 1.0 <= delays[0] <= 1.25 and 2.0 <= delays[1] <= 2.5  # doubles, with jitter
    calls["n"] = -10
    with pytest.raises(ConnectionError):
        retry_call(flaky, attempts=2, sleep=lambda s: None)
    with pytest.raises(ValueError):  # errors outside retry_on are not retried
        retry_call(lambda: (_ for _ in ()).throw(ValueError("bad")), retry_on=(ConnectionError,), sleep=lambda s: None)


def test_dead_letter_counts_repeats_of_the_same_open_item(world: World) -> None:
    dead_letter(world.container.db, "upload", "Boom", reference="u1", payload={"upload_id": "u1"})
    dead_letter(world.container.db, "upload", "Boom again", reference="u1")
    [row] = _dead(world)
    assert row["attempts"] == 2 and row["error"] == "Boom again" and row["status"] == "open"


# ---------------------------------------------------------------------------- uploads
def test_failed_upload_is_dead_lettered_and_a_retry_finishes_it(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_catalog(world)
    mgr = Api(world, raise_server_exceptions=False).as_role("a", "manager")  # a background task failure is logged, not raised
    resolver = svc.get_resolver(world.container)
    real = resolver.resolve

    def broken(record):  # type: ignore[no-untyped-def]
        raise RuntimeError("model crashed")

    monkeypatch.setattr(resolver, "resolve", broken)
    csv_body = b"name,state\nHarborline Foods,OH\nCobalt Ridge Logistics,TN\n"
    up = mgr.post("/uploads", files={"file": ("s.csv", csv_body, "text/csv")})
    assert up.status_code == 202
    uid = up.json()["id"]
    assert mgr.get(f"/uploads/{uid}").json()["status"] == "failed"
    [row] = _dead(world)
    assert row["kind"] == "upload" and row["reference"] == uid and row["error"] == "RuntimeError"

    monkeypatch.setattr(resolver, "resolve", real)
    pa = Api(world).as_role("platform", "platform_admin")
    assert pa.get("/platform/dead-letters").json()["items"][0]["kind"] == "upload"
    done = pa.post(f"/platform/dead-letters/{row['id']}", json={"action": "retry"})
    assert done.status_code == 200 and done.json()["status"] == "retried"
    assert mgr.get(f"/uploads/{uid}").json()["status"] == "complete"
    assert pa.post(f"/platform/dead-letters/{row['id']}", json={"action": "retry"}).status_code == 404  # already resolved
    assert pa.get("/platform/dead-letters?status=retried").json()["items"][0]["id"] == row["id"]


def test_dead_letter_queue_is_platform_only_and_can_discard(world: World) -> None:
    dead_letter(world.container.db, "email", "SMTPError", reference="a:b", payload={"to": ["x@example.org"], "subject": "s", "body": "b"})
    for role in ("viewer", "analyst", "manager", "tenant_admin"):
        assert Api(world).as_role("a", role).get("/platform/dead-letters").status_code == 403, role
    assert Api(world).as_role("platform", "finance_analyst").get("/platform/dead-letters").status_code == 403
    pa = Api(world).as_role("platform", "platform_admin")
    [item] = pa.get("/platform/dead-letters").json()["items"]
    assert pa.post(f"/platform/dead-letters/{item['id']}", json={"action": "discard"}).json()["status"] == "discarded"
    assert pa.get("/platform/dead-letters").json()["items"] == []
    with world.container.db.tenant(world.tenant_a) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT 1 FROM dead_letters")  # no tenant access, even through SQL


# ---------------------------------------------------------------------------- webhooks
def test_exhausted_webhook_is_dead_lettered_and_redelivered(world: World) -> None:
    _setup_alert(world, ["webhook"])
    hooks = Hooks(status=503)
    n = notify.Notifier(world.container, hooks.client(), url_check=lambda u: None, sleep=lambda s: None)
    from app.services import monitoring

    run(monitoring.recompute_tenant(world.container, world.tenant_a, notifier=n))
    [row] = _dead(world)
    assert row["kind"] == "webhook" and row["payload"]["url"] == "https://hooks.example/x" and row["error"] == "status 503"
    good = Hooks(status=200)
    notify.Notifier(world.container, good.client(), url_check=lambda u: None, sleep=lambda s: None).redeliver_webhook(
        row["payload"]["url"], row["payload"]["body"])
    assert good.calls[0]["supplier"] == "Harborline Foods"
    with pytest.raises(notify.UnsafeUrl):  # the safety check applies to redelivery too
        notify.Notifier(world.container, good.client()).redeliver_webhook("https://127.0.0.1/x", {})


# ---------------------------------------------------------------------------- degradation and outages
def test_database_outage_answers_503_with_retry_after(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = Api(world).as_role("a", "manager")

    def down(*a, **k):  # type: ignore[no-untyped-def]
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(world.container.db, "tenant", down)
    r = mgr.get("/suppliers")
    assert r.status_code == 503 and r.headers["Retry-After"] == "5" and r.json()["type"].endswith("/unavailable")
    assert "connection" not in r.text  # no internal detail


def test_unavailable_model_service_flags_reduced_confidence_and_keeps_the_record_reviewable(world: World) -> None:
    seed_catalog(world)
    resolver = svc.get_resolver(world.container)

    class Down:
        name = "vector"

        def retrieve(self, record, k):  # type: ignore[no-untyped-def]
            raise ServiceUnavailable("embedding service is down")

    resolver.retrievers.append(Down())
    mgr = Api(world).as_role("a", "manager")
    r = mgr.post("/resolve", json={"name": "Harborline Food", "state": "OH"}).json()
    assert r["degraded"] is True and any("reduced confidence" in n for n in r["notes"])
    assert r["route"] in ("review", "nil")  # never an automatic accept while degraded
    sid = mgr.post("/suppliers", json={"name": "Harborline Food", "state": "OH"}).json()["id"]
    assert mgr.get(f"/suppliers/{sid}/profile").json()["supplier"]["resolution_detail"]["degraded"] is True


# ---------------------------------------------------------------------------- company search and indexes
def test_company_search_finds_by_similarity_prefix_and_ticker(world: World) -> None:
    ids = seed_catalog(world)
    with world.container.db.system() as conn:
        conn.execute("UPDATE companies SET tickers = ARRAY['HRBL'] WHERE id = %s", (ids["Harborline Foods, Inc.|OH"],))
    api = Api(world).as_role("a", "viewer")
    by = lambda q: [i["canonical_name"] for i in api.get(f"/companies/search?q={q}").json()["items"]]  # noqa: E731
    assert by("Harborlin")[0] == "Harborline Foods, Inc."  # prefix
    assert by("harborline fods")[0] == "Harborline Foods, Inc."  # similarity with a typo
    assert by("hrbl")[0] == "Harborline Foods, Inc."  # ticker
    assert by("zzzz nothing") == []
    scores = [i["score"] for i in api.get("/companies/search?q=northgate").json()["items"]]
    assert scores == sorted(scores, reverse=True) and len(scores) == 2


def test_performance_indexes_exist_and_are_used(world: World) -> None:
    with world.container.db.system() as conn:
        names = {r["indexname"] for r in conn.execute("SELECT indexname FROM pg_indexes").fetchall()}
        assert {"risk_score_components_score", "link_candidates_entity", "companies_tickers",
                "companies_norm_prefix", "resolution_reviews_open"} <= names
        conn.execute("SET enable_seqscan = off")
        plan = "\n".join(next(iter(r.values())) for r in conn.execute(
            "EXPLAIN SELECT * FROM risk_score_components WHERE risk_score_id = 1").fetchall())
        assert "risk_score_components_score" in plan


def test_http_client_type_is_available_for_webhook_tests() -> None:
    assert isinstance(httpx.Client, type)


# ---------------------------------------------------------------------------- retention
def test_retention_purges_old_data_and_keeps_current_data(world: World, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from pathlib import Path

    from app.services.retention import purge_all

    ids = seed_catalog(world)
    mgr = Api(world).as_role("a", "manager")
    sid = mgr.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"}).json()["id"]
    old_file = tmp_path / "old.pdf"
    old_file.write_bytes(b"%PDF-")
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(b"keep")
    with world.container.db.system() as conn:
        conn.execute("UPDATE tenants SET retention_days = 30 WHERE id = %s", (world.tenant_a,))
        for days in (100, 1):
            conn.execute("INSERT INTO risk_scores (tenant_id, supplier_id, score, level, config_version, computed_at) "
                         "VALUES (%s,%s,10,'low','v1', now() - make_interval(days => %s))", (world.tenant_a, sid, days))
        conn.execute("INSERT INTO risk_scores (tenant_id, supplier_id, score, level, config_version, computed_at) "
                     "VALUES (%s,%s,20,'low','v1', now() - interval '200 days')", (world.tenant_a, sid))
        for age, key in ((100, "old"), (1, "new")):
            conn.execute("INSERT INTO alerts (tenant_id, supplier_id, kind, detail, dedup_key, created_at) "
                         "VALUES (%s,%s,'high_severity_event',%s,%s, now() - make_interval(days => %s))", (world.tenant_a, sid, key, key, age))
        conn.execute("INSERT INTO reports (tenant_id, kind, status, storage_path, created_at) VALUES (%s,'portfolio','ready',%s, now() - interval '90 days')",
                     (world.tenant_a, str(old_file)))
        conn.execute("INSERT INTO reports (tenant_id, kind, status, storage_path, created_at) VALUES (%s,'portfolio','ready',%s, now() - interval '90 days')",
                     (world.tenant_a, str(outside)))
        conn.execute("INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at) VALUES (%s, gen_random_uuid(), 'h1', now() - interval '30 days')",
                     (world.users[("a", "manager")],))
    dry = purge_all(world.container.db, tmp_path, dry=True)
    assert dry["tenants"][world.tenant_a]["alerts"] == 1 and old_file.exists()  # a dry run changes nothing
    done = purge_all(world.container.db, tmp_path)
    counts = done["tenants"][world.tenant_a]
    assert counts["alerts"] == 1 and counts["reports"] == 2 and counts["risk_scores"] == 2
    assert not old_file.exists() and outside.exists()  # files outside the report directory are never touched
    assert done["global"]["refresh_tokens"] >= 1
    with world.container.db.system() as conn:
        left = conn.execute("SELECT score FROM risk_scores WHERE supplier_id = %s", (sid,)).fetchall()
        assert [float(r["score"]) for r in left] == [10.0]  # the newest score survives
        assert conn.execute("SELECT detail FROM alerts").fetchone()["detail"] == "new"
    assert ids  # the catalog was seeded for the supplier above
    assert Path(tmp_path).exists()
