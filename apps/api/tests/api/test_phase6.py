"""Phase 6 workflows: uploads, review comparison, profile, corrections, notifications, reports."""

from __future__ import annotations

import asyncio
import io
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.services import monitoring, notify
from conftest import Api, World, seed_catalog, seed_event
from test_workflows import CSV, upload

needs_pdf = pytest.mark.skipif(
    not os.environ.get("DYLD_FALLBACK_LIBRARY_PATH") and not Path("/usr/lib/libpango-1.0.so.0").exists()
    and not Path("/usr/lib/x86_64-linux-gnu/libpango-1.0.so.0").exists()
    and not Path("/usr/lib/aarch64-linux-gnu/libpango-1.0.so.0").exists(),
    reason="WeasyPrint needs Pango (set DYLD_FALLBACK_LIBRARY_PATH on macOS)")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# ------------------------------------------------------------------ uploads
def test_template_preview_export_and_error_report(world: World) -> None:
    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    tpl = api.get("/uploads/template")
    assert tpl.headers["content-type"].startswith("text/csv") and tpl.text.startswith("supplier_name,")
    pv = api.post("/uploads/preview", files={"file": ("s.csv", io.BytesIO(CSV), "text/csv")})
    assert pv.status_code == 200
    body = pv.json()
    assert body["mapping"]["name"] == "Supplier Name" and body["valid_rows"] == 4 and body["invalid_rows"] == 1
    assert "state" in body["mapping"] and body["sample"][0]["name"] == "HARBORLINE FOODS INC"
    with world.container.db.system() as conn:
        assert conn.execute("SELECT count(*) AS n FROM suppliers").fetchone()["n"] == 0  # nothing stored
    bad = api.post("/uploads/preview", files={"file": ("s.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert bad.status_code == 422 and "name column" in bad.json()["detail"]

    up = upload(api).json()
    exp = api.get(f"/uploads/{up['id']}/export")
    lines = exp.text.splitlines()
    assert lines[0].startswith("supplier_name,status,confidence,canonical_company_id,canonical_name")
    row = [ln for ln in lines if ln.startswith("HARBORLINE")][0]
    assert "Harborline Foods, Inc." in row and ",1001," in row  # canonical id and CIK
    assert any("'=HYPERLINK" in ln for ln in lines)  # formula neutralised
    err = api.get(f"/uploads/{up['id']}/errors")
    assert err.text.splitlines()[1] == "5,missing supplier name"
    assert Api(world).as_role("b", "analyst").get(f"/uploads/{up['id']}/export").status_code == 404
    assert Api(world).as_role("a", "viewer").post(
        "/uploads/preview", files={"file": ("s.csv", io.BytesIO(CSV), "text/csv")}).status_code == 403


# ------------------------------------------------------------------ review comparison
def test_review_detail_side_by_side_and_decisions(world: World) -> None:
    ids = seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    upload(api, b"name\nCobalt Ridge Logistics\nZyxwv Co\n")
    rev = api.get("/reviews").json()["items"][0]
    detail = api.get(f"/reviews/{rev['id']}").json()
    assert detail["uploaded"]["name"] == "Cobalt Ridge Logistics" and set(detail["actions"]) >= {"accept", "not_in_database"}
    by_state = {c["details"]["hq_state"]: c for c in detail["candidates"]}
    assert by_state["NV"]["comparison"]["city"]["agreement"] == "unknown"  # nothing uploaded to compare
    assert by_state["NV"]["comparison"]["name"]["similarity"] > 0.9
    assert by_state["NV"]["comparison"]["state"]["candidate"] == "NV"
    assert "splink_weight" in by_state["NV"]["scores"]
    other = ids["Cobalt Ridge Logistics Co.|NV"]
    done = api.patch(f"/reviews/{rev['id']}", json={"action": "choose_other", "company_id": other})
    assert done.json()["company_id"] == other
    sup = api.get("/suppliers?status=resolved").json()["items"][0]
    assert sup["resolved_company_id"] == other
    assert api.get(f"/reviews/{uuid.uuid4()}").status_code == 404


def test_not_in_database_and_bulk_accept(world: World) -> None:
    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    upload(api, b"name,state\nNorthgate Metals,\nHarborline Food,\nCobalt Ridge Logistics,\n")
    items = api.get("/reviews").json()["items"]
    assert len(items) >= 2
    first = items[0]
    r = api.patch(f"/reviews/{first['id']}", json={"action": "not_in_database"})
    assert r.status_code == 200
    sup = [s for s in api.get("/suppliers?status=unresolved").json()["items"] if s["id"] == first["supplier_id"]]
    assert sup, "supplier is marked unresolved"
    with world.container.db.system() as conn:
        detail = conn.execute("SELECT resolution_detail FROM suppliers WHERE id = %s", (first["supplier_id"],)).fetchone()
        assert detail["resolution_detail"]["not_in_database"] is True
    strict = api.post("/reviews/bulk-accept", json={"min_probability": 1.0, "min_margin": 0.99}).json()
    assert strict["accepted"] == 0
    loose = api.post("/reviews/bulk-accept", json={"min_probability": 0.5, "min_margin": 0.0}).json()
    assert loose["accepted"] >= 1
    assert api.post("/reviews/bulk-accept", json={"min_probability": 0.1}).status_code == 422
    assert Api(world).as_role("a", "viewer").post("/reviews/bulk-accept", json={"min_probability": 0.9}).status_code == 403


def test_feedback_is_stored_only_with_opt_in_and_without_tenant_ids(world: World) -> None:
    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    upload(api, b"name\nCobalt Ridge Logistics\n")
    api.patch(f"/reviews/{api.get('/reviews').json()['items'][0]['id']}", json={"action": "reject"})
    with world.container.db.system() as conn:
        assert conn.execute("SELECT count(*) AS n FROM training_feedback").fetchone()["n"] == 0
        conn.execute("UPDATE tenants SET share_feedback_for_training = true WHERE id = %s", (world.tenant_a,))
    upload(api, b"name\nCobalt Ridge Logistics Co\n")
    api.patch(f"/reviews/{api.get('/reviews').json()['items'][0]['id']}", json={"action": "not_in_database"})
    with world.container.db.system() as conn:
        rows = conn.execute("SELECT * FROM training_feedback").fetchall()
    assert len(rows) == 1 and rows[0]["label"] == "nil" and rows[0]["query"]["name"] == "Cobalt Ridge Logistics Co"
    assert world.tenant_a not in json.dumps(rows[0], default=str) and "tenant_id" not in rows[0]


def test_merge_duplicates_and_unmerge(world: World) -> None:
    seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    a = api.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"}).json()["id"]
    b = api.post("/suppliers", json={"name": "HARBORLINE FOODS INC", "state": "OH"}).json()["id"]
    assert api.post(f"/suppliers/{b}/merge", json={"into_supplier_id": b}).status_code == 422
    assert api.post(f"/suppliers/{b}/merge", json={"into_supplier_id": a}).json()["duplicate_of"] == a
    assert [s["id"] for s in api.get("/suppliers").json()["items"]] == [a]
    assert len(api.get("/suppliers?include_duplicates=true").json()["items"]) == 2
    c = api.post("/suppliers", json={"name": "Harborline Foods Co", "state": "OH"}).json()["id"]
    assert api.post(f"/suppliers/{a}/merge", json={"into_supplier_id": c}).status_code == 200
    assert api.post(f"/suppliers/{c}/merge", json={"into_supplier_id": b}).status_code == 409
    assert api.post(f"/suppliers/{b}/unmerge").status_code == 200
    assert api.post(f"/suppliers/{a}/merge", json={"into_supplier_id": str(uuid.uuid4())}).status_code == 404
    assert Api(world).as_role("b", "analyst").post(f"/suppliers/{a}/merge", json={"into_supplier_id": c}).status_code == 404


# ------------------------------------------------------------------ profile, graph, corrections
def test_supplier_profile_has_every_section(world: World) -> None:
    ids = seed_catalog(world)
    parent, child = ids["Northgate Metals Corporation|PA"], ids["Northgate Metals of Texas LLC|TX"]
    with world.container.db.system() as conn:
        conn.execute("INSERT INTO company_aliases (company_id, alias, alias_type, normalized, source) "
                     "VALUES (%s,'Northgate Metal Works','former','northgate metal works','edgar')", (parent,))
        conn.execute("INSERT INTO facilities (registry_id, name, normalized_name, city, state, latitude, "
                     "longitude, source, company_id, link_confidence) VALUES ('110001','Northgate Plant',"
                     "'northgate plant','Houston','TX',29.7,-95.3,'epa_echo',%s,0.95)", (parent,))
        conn.execute("INSERT INTO source_records (source, source_key, name, company_id, method, score) "
                     "VALUES ('sec_edgar','1003','Northgate Metals Corporation',%s,'cik',1.0)", (parent,))
    seed_event(world, child, title="OSHA citation record for the Texas subsidiary")
    api = Api(world).as_role("a", "analyst")
    sid = api.post("/suppliers", json={"name": "Northgate Metals Corporation", "state": "PA",
                                       "city": "Pittsburgh"}).json()["id"]
    run(monitoring.recompute_tenant(world.container, world.tenant_a))
    prof = api.get(f"/suppliers/{sid}/profile").json()
    assert prof["company"]["canonical_name"] == "Northgate Metals Corporation"
    assert prof["company"]["aliases"][0]["alias"] == "Northgate Metal Works"
    sub = [n for n in prof["family"]["nodes"] if n["direction"] == "down"][0]
    assert sub["id"] == child and sub["in_portfolio"] is False and prof["family"]["edges"][0]["source"] == "gleif"
    assert prof["facilities"][0]["latitude"] == 29.7
    assert prof["events"][0]["relation"] == "subsidiary_event_to_parent"
    assert prof["sources"][0]["url"].startswith("https://www.sec.gov/")
    assert prof["risk"]["level"] in ("low", "medium", "high", "critical") and prof["risk"]["components"]
    assert "not statements of fault" in prof["disclaimer"]
    assert Api(world).as_role("b", "viewer").get(f"/suppliers/{sid}/profile").status_code == 404


def test_concentration_by_ultimate_parent_with_portfolio_overlay(world: World) -> None:
    ids = seed_catalog(world)
    api = Api(world).as_role("a", "analyst")
    for name, st in (("Northgate Metals Corporation", "PA"), ("Northgate Metals of Texas LLC", "TX"),
                     ("Harborline Foods", "OH")):
        api.post("/suppliers", json={"name": name, "state": st})
    g = api.get("/graph/concentration").json()
    assert g["total_suppliers"] == 3
    top = g["groups"][0]
    assert top["company_id"] == ids["Northgate Metals Corporation|PA"] and top["suppliers"] == 2
    assert round(top["share_of_suppliers"], 3) == round(2 / 3, 3) and g["groups"][-1]["cumulative_share"] == 1.0
    nb = api.get(f"/graph/neighbors?company_id={ids['Northgate Metals Corporation|PA']}&depth=1").json()
    assert all(n["in_portfolio"] for n in nb["nodes"])
    assert Api(world).as_role("b", "viewer").get("/graph/concentration").json()["groups"] == []


def test_corrections_flow_to_platform_queue(world: World) -> None:
    ids = seed_catalog(world)
    ev = seed_event(world, ids["Harborline Foods, Inc.|OH"])
    viewer = Api(world).as_role("a", "viewer")
    assert viewer.post("/corrections", json={"kind": "other", "description": "x"}).status_code == 422
    r = viewer.post("/corrections", json={"kind": "wrong_link", "event_id": ev,
                                          "company_id": ids["Harborline Foods, Inc.|OH"],
                                          "description": "A different company with a similar name."})
    assert r.status_code == 201 and r.json()["status"] == "open"
    assert viewer.post("/corrections", json={"kind": "other", "description": "x", "event_id": 99999}).status_code == 404
    assert Api(world).as_role("b", "viewer").get("/corrections").json()["items"] == []
    pa = Api(world).as_role("platform", "platform_admin")
    queue = pa.get("/platform/corrections").json()["items"]
    assert queue[0]["event_title"] == "OSHA citation record" and queue[0]["tenant_id"] == world.tenant_a
    assert Api(world).as_role("a", "manager").get("/platform/corrections").status_code == 403
    done = pa.patch(f"/platform/corrections/{queue[0]['id']}", json={"status": "accepted",
                                                                      "response": "Link corrected."})
    assert done.status_code == 200
    mine = viewer.get("/corrections").json()["items"][0]
    assert mine["status"] == "accepted" and mine["response"] == "Link corrected."
    assert pa.patch(f"/platform/corrections/{queue[0]['id']}", json={"status": "closed", "response": "x"}).status_code == 404
    # The event itself is untouched by a tenant-raised correction.
    assert viewer.get("/events").json()["items"][0]["id"] == ev


# ------------------------------------------------------------------ notifications
class Hooks:
    def __init__(self, status: int = 200) -> None:
        self.calls: list[dict[str, Any]] = []
        self.status = status

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.calls.append(json.loads(request.content))
            return httpx.Response(self.status)

        return httpx.Client(transport=httpx.MockTransport(handler))


def _setup_alert(world: World, channels: list[str], url: str | None = "https://hooks.example/x") -> str:
    ids = seed_catalog(world)
    mgr = Api(world).as_role("a", "manager")
    mgr.post("/rules", json={"name": "Severe", "min_severity": 3, "channels": channels, "webhook_url": url})
    mgr.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"})
    seed_event(world, ids["Harborline Foods, Inc.|OH"], severity=3)
    return ids["Harborline Foods, Inc.|OH"].__str__()


def deliveries(world: World) -> list[tuple[str, str, str]]:
    with world.container.db.system() as conn:
        return [(r["channel"], r["status"], r["detail"]) for r in conn.execute(
            "SELECT channel, status, detail FROM alert_deliveries ORDER BY id").fetchall()]


def test_email_and_webhook_notifications_are_delivered_and_logged(world: World) -> None:
    _setup_alert(world, ["in_app", "email", "webhook"])
    hooks = Hooks()
    n = notify.Notifier(world.container, hooks.client(), url_check=lambda u: None)
    result = run(monitoring.recompute_tenant(world.container, world.tenant_a, notifier=n))
    assert result["alerts_created"] == 1
    d = deliveries(world)
    assert [x[:2] for x in d] == [("in_app", "sent"), ("email", "sent"), ("webhook", "sent")]
    to = {m[0] for m in world.mailer.outbox}
    assert to == {"manager@a.example", "tenant_admin@a.example"}  # only the tenant's managers
    assert "not statements of fault" in world.mailer.outbox[0][2]
    assert hooks.calls[0]["supplier"] == "Harborline Foods" and "not statements of fault" in hooks.calls[0]["notice"]
    again = run(monitoring.recompute_tenant(world.container, world.tenant_a, notifier=n))
    assert again["alerts_created"] == 0 and len(hooks.calls) == 1  # no duplicate notification


def test_webhook_retries_on_server_errors_and_blocks_unsafe_hosts(world: World) -> None:
    _setup_alert(world, ["webhook"])
    sleeps: list[float] = []
    hooks = Hooks(status=503)
    n = notify.Notifier(world.container, hooks.client(), url_check=lambda u: None, sleep=sleeps.append)
    run(monitoring.recompute_tenant(world.container, world.tenant_a, notifier=n))
    assert len(hooks.calls) == 3 and sleeps == [0.5, 1.0] and deliveries(world) == [("webhook", "failed", "status 503")]


def test_ssrf_guard_rejects_private_and_non_https_urls() -> None:
    for url in ("http://example.com/x", "https://127.0.0.1/x", "https://10.0.0.5/x", "https://[::1]/x",
                "https://169.254.169.254/latest", "https://localhost/x", "ftp://x"):
        with pytest.raises(notify.UnsafeUrl):
            notify.assert_public_https(url)


def test_unsafe_webhook_is_blocked_end_to_end(world: World) -> None:
    _setup_alert(world, ["webhook"], url="https://127.0.0.1/hook")
    hooks = Hooks()
    run(monitoring.recompute_tenant(world.container, world.tenant_a, notifier=notify.Notifier(world.container, hooks.client())))
    assert hooks.calls == [] and deliveries(world)[0][1] == "failed" and "blocked" in deliveries(world)[0][2]


# ------------------------------------------------------------------ monitoring
def test_recompute_scores_dedups_clusters_and_updates_on_change(world: World) -> None:
    ids = seed_catalog(world)
    api = Api(world).as_role("a", "manager")
    sid = api.post("/suppliers", json={"name": "Northgate Metals Corporation", "state": "PA",
                                       "city": "Pittsburgh"}).json()["id"]
    r = api.post("/monitoring/recompute").json()
    assert r == {"suppliers": 1, "scores_written": 1, "alerts_created": 0}
    assert api.get(f"/suppliers/{sid}/risk").json()["score"] == 0.0
    child = ids["Northgate Metals of Texas LLC|TX"]
    seed_event(world, child, title="regulator record")
    news = seed_event(world, child, title="regulator record coverage")
    with world.container.db.system() as conn:  # the second item is a news item about the same incident
        conn.execute("UPDATE events SET source = 'news', source_id = 'n1' WHERE id = %s", (news,))
    r2 = api.post("/monitoring/recompute").json()
    assert r2["scores_written"] == 1 and r2["alerts_created"] >= 1
    risk = api.get(f"/suppliers/{sid}/risk").json()
    assert risk["score"] > 0 and len(risk["components"]) == 1  # one incident, counted once
    assert risk["components"][0]["relation_weight"] == 0.7 and risk["components"][0]["source_reliability"] == 1.0
    assert api.post("/monitoring/recompute").json()["scores_written"] == 0  # unchanged, no new score row
    assert Api(world).as_role("a", "analyst").post("/monitoring/recompute").status_code == 403
    assert run(monitoring.recompute_all(world.container, datetime.now(UTC)))[world.tenant_a]["suppliers"] == 1


# ------------------------------------------------------------------ reports
@needs_pdf
def test_supplier_and_portfolio_pdf_reports(world: World, tmp_path: Path) -> None:
    ids = seed_catalog(world)
    seed_event(world, ids["Northgate Metals of Texas LLC|TX"], title="OSHA citation record <script>x</script>")
    c = world.container
    object.__setattr__(c.settings, "report_dir", str(tmp_path))
    mgr = Api(world).as_role("a", "manager")
    sid = mgr.post("/suppliers", json={"name": "Northgate Metals Corporation", "state": "PA",
                                       "city": "Pittsburgh"}).json()["id"]
    mgr.post("/monitoring/recompute")
    rep = mgr.post(f"/reports/supplier/{sid}").json()
    status = mgr.get(f"/reports/{rep['id']}").json()
    assert status["status"] == "ready", status
    pdf = mgr.get(f"/reports/{rep['id']}/download")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    from pypdf import PdfReader

    text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    for needle in ("Supplier risk report", "Northgate Metals Corporation", rep["id"], "not statements of fault",
                   "Demo data", "Score breakdown", "OSHA citation record"):
        assert needle in text, needle
    assert "<script>x</script>" in text  # escaped, so it is printed as text and never interpreted
    assert "violated" not in text.lower()
    port = mgr.post("/reports/portfolio").json()
    ptext = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(mgr.get(f"/reports/{port['id']}/download").content)).pages)
    assert "Portfolio risk report" in ptext and "Concentration by ultimate parent" in ptext
    assert len(mgr.get("/reports").json()["items"]) == 2
    assert Api(world).as_role("b", "manager").get(f"/reports/{rep['id']}/download").status_code == 404
    assert Api(world).as_role("a", "viewer").get(f"/reports/{rep['id']}/download").status_code == 403


def test_report_failure_is_recorded_and_download_is_conflict(world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import pdf

    def boom(_: str) -> bytes:
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(pdf, "render_pdf", boom)
    object.__setattr__(world.container.settings, "report_dir", str(tmp_path))
    mgr = Api(world).as_role("a", "manager")
    rep = mgr.post("/reports/portfolio").json()
    st = mgr.get(f"/reports/{rep['id']}").json()
    assert st["status"] == "failed" and "renderer unavailable" in st["error"] and st["download_url"] is None
    assert mgr.get(f"/reports/{rep['id']}/download").status_code == 409


def test_pdf_renderer_never_fetches_external_resources() -> None:
    from app.services.pdf import _deny

    with pytest.raises(ValueError):
        _deny("http://169.254.169.254/latest/meta-data")


# ------------------------------------------------------------------ exit criterion
@needs_pdf
def test_end_to_end_upload_review_subsidiary_event_sse_and_report(world: World, tmp_path: Path) -> None:
    """Upload a messy file, review the uncertain matches, an event arrives for a subsidiary, the
    parent supplier's alert reaches the live stream, and the report exports."""
    ids = seed_catalog(world)
    parent = ids["Northgate Metals Corporation|PA"]
    object.__setattr__(world.container.settings, "report_dir", str(tmp_path))
    mgr = Api(world).as_role("a", "manager")
    mgr.post("/rules", json={"name": "Severe events", "min_severity": 3})

    messy = (b"Vendor,ST,City,Tax ID\n"
             b"NORTHGATE METALS CORP.,PA,Pittsburgh,98-7654321\n"
             b"Cobalt Ridge Logistics,,,\n"
             b"Harborline Foods Inc,OH,Columbus,\n"
             b"Harborline Foods Inc,OH,Columbus,\n"
             b"Unknown Widgets Intl,CA,,\n"
             b",,,\n")
    up = upload(mgr, messy, mapping=json.dumps({"state": "ST", "name": "Vendor"}))
    assert up.status_code == 202
    summary = mgr.get(f"/uploads/{up.json()['id']}").json()
    assert summary["status"] == "complete" and summary["row_count"] == 5 and len(summary["errors"]) == 1
    assert summary["needs_review"] >= 1 and summary["auto_resolved"] >= 1

    for rev in mgr.get("/reviews").json()["items"]:  # resolve the uncertain matches
        detail = mgr.get(f"/reviews/{rev['id']}").json()
        action = {"action": "accept"} if "Cobalt" not in detail["uploaded"]["name"] else {
            "action": "choose_other", "company_id": ids["Cobalt Ridge Logistics Co.|NV"]}
        assert mgr.patch(f"/reviews/{rev['id']}", json=action).status_code == 200
    dupes = [s for s in mgr.get("/suppliers").json()["items"] if s["uploaded_name"] == "Harborline Foods Inc"]
    if len(dupes) == 2:
        mgr.post(f"/suppliers/{dupes[1]['id']}/merge", json={"into_supplier_id": dupes[0]["id"]})
    parent_sup = [s for s in mgr.get("/suppliers").json()["items"]
                  if s["resolved_company_id"] == parent][0]
    mgr.post("/monitoring/recompute")
    assert mgr.get(f"/suppliers/{parent_sup['id']}/risk").json()["score"] == 0.0

    # An event arrives for the Texas subsidiary while a client is listening on the live stream.
    from app.events_bus import alert_channel
    from app.routers.alerts import sse_events

    async def scenario() -> list[str]:
        out: list[str] = []
        gen = sse_events(world.container, world.tenant_a, heartbeat=5)

        async def listen() -> None:
            async for chunk in gen:
                out.append(chunk)
                if chunk.startswith("event: alert"):
                    return

        task = asyncio.create_task(listen())
        await asyncio.sleep(0.1)
        seed_event(world, ids["Northgate Metals of Texas LLC|TX"], title="OSHA citation record, Texas plant")
        await monitoring.recompute_tenant(world.container, world.tenant_a)
        await asyncio.wait_for(task, 3)
        await gen.aclose()
        return out

    chunks = asyncio.run(scenario())
    msg = json.loads(chunks[-1].split("data: ", 1)[1])
    assert msg["supplier_id"] == parent_sup["id"] and msg["kind"] in ("high_severity_event", "threshold_crossing")
    assert alert_channel(world.tenant_a).startswith("alerts:")
    assert any(a["id"] == msg["id"] for a in mgr.get("/alerts").json()["items"])
    risk = mgr.get(f"/suppliers/{parent_sup['id']}/risk").json()
    assert risk["score"] > 0 and risk["components"][0]["relation_weight"] == 0.7

    rep = mgr.post(f"/reports/supplier/{parent_sup['id']}").json()
    pdf = mgr.get(f"/reports/{rep['id']}/download")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    exported = mgr.get(f"/uploads/{up.json()['id']}/export").text
    assert "Northgate Metals Corporation" in exported and "98-7654321" not in exported


def test_field_comparison_flags_agreement_and_conflict() -> None:
    from app.services.review import compare

    cand = {"name": "Cobalt Ridge Logistics Co.", "details": {
        "hq_state": "NV", "hq_city": "Reno", "hq_country": "US", "cik": 5, "lei": None, "tickers": ["CRL"],
        "parent_name": "Cobalt Holdings", "industry": "trucking", "sic_code": "4210"}}
    same = compare({"state": "Nevada", "city": "RENO", "country": "us", "cik": 5, "ticker": "crl"},
                   "COBALT RIDGE LOGISTICS CO", cand)
    assert [same[k]["agreement"] for k in ("state", "city", "country", "cik", "ticker")] == ["match"] * 5
    assert same["name"]["similarity"] == 1.0 and same["parent"]["candidate"] == "Cobalt Holdings"
    diff = compare({"state": "TN", "city": "Memphis", "cik": 9}, "Cobalt Ridge", cand)
    assert [diff[k]["agreement"] for k in ("state", "city", "cik", "lei")] == ["mismatch", "mismatch", "mismatch", "unknown"]
