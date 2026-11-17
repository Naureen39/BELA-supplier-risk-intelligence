"""Reports, data sources, analytics, and billing (tenant views)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Response

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.errors import ApiError
from app.routers.common import audit_event, jsonable, parse_uuid
from app.services.reports import generate_report

router = APIRouter(tags=["reports", "sources", "billing"])
manager = deps.require(P.MANAGE_RULES)
tenant_admin = deps.require_session(P.MANAGE_USERS)
DISCLAIMER = "Risk signals are leads for human review and not statements of fault."


# ------------------------------------------------------------------ reports
def _report_view(row: dict[str, Any]) -> dict[str, Any]:
    out = jsonable(row, drop=("tenant_id", "storage_path"))
    out["download_url"] = f"/api/v1/reports/{row['id']}/download" if row["status"] == "ready" else None
    out["disclaimer"] = DISCLAIMER
    return out


@router.get("/reports", summary="Generated and queued reports")
def reports_list(p: Principal = Depends(manager), conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"items": [_report_view(r) for r in rows]}


@router.post("/reports/supplier/{supplier_id}", status_code=202, summary="Request a supplier report (PDF)")
def report_supplier(supplier_id: str, background: BackgroundTasks, p: Principal = Depends(manager),
                    t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    sid = parse_uuid(supplier_id, "supplier")
    if not conn.execute("SELECT 1 FROM suppliers WHERE id = %s", (sid,)).fetchone():
        raise ApiError(404, "The supplier was not found.", code="not-found")
    row = conn.execute("INSERT INTO reports (tenant_id, kind, supplier_id, created_by) "
                       "VALUES (%s,'supplier',%s,%s) RETURNING *", (t, sid, p.user_id)).fetchone()
    audit_event(c, p, "report.requested", "report", str(row["id"]), {"kind": "supplier"})
    background.add_task(generate_report, c, t, str(row["id"]))
    return _report_view(row)


@router.post("/reports/portfolio", status_code=202, summary="Request a portfolio report (PDF)")
def report_portfolio(background: BackgroundTasks, p: Principal = Depends(manager),
                     t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                     c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    row = conn.execute("INSERT INTO reports (tenant_id, kind, created_by) "
                       "VALUES (%s,'portfolio',%s) RETURNING *", (t, p.user_id)).fetchone()
    audit_event(c, p, "report.requested", "report", str(row["id"]), {"kind": "portfolio"})
    background.add_task(generate_report, c, t, str(row["id"]))
    return _report_view(row)


@router.get("/reports/{report_id}", summary="Report status")
def report_get(report_id: str, p: Principal = Depends(manager), conn: Any = deps.TENANT_DB
               ) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM reports WHERE id = %s", (parse_uuid(report_id, "report"),)).fetchone()
    if not row:
        raise ApiError(404, "The report was not found.", code="not-found")
    return _report_view(row)


@router.get("/reports/{report_id}/download", summary="Download the PDF")
def report_download(report_id: str, p: Principal = Depends(manager), conn: Any = deps.TENANT_DB,
                    c: Container = Depends(deps.get_container)) -> Response:
    row = conn.execute("SELECT id, status, storage_path FROM reports WHERE id = %s",
                       (parse_uuid(report_id, "report"),)).fetchone()
    if not row:
        raise ApiError(404, "The report was not found.", code="not-found")
    if row["status"] != "ready" or not row["storage_path"]:
        raise ApiError(409, f"The report is {row['status']}.", code="not-ready")
    path = Path(row["storage_path"]).resolve()
    if Path(c.settings.report_dir).resolve() not in path.parents or not path.is_file():
        raise ApiError(404, "The report file is not available.", code="not-found")
    audit_event(c, p, "report.downloaded", "report", str(row["id"]))
    return Response(path.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="report_{row["id"]}.pdf"'})


# ------------------------------------------------------------------ sources
LICENSES = {
    "sec_edgar": "Public filings. SEC fair access policy applies.",
    "gleif": "GLEIF LEI data terms of use (CC0 1.0).",
    "wikidata": "CC0 1.0.",
    "epa_echo": "US government data. Records before November 2000 have unknown quality.",
    "osha": "US Department of Labor data.", "nhtsa": "US government data.",
    "cpsc": "US government API.", "openfda": "US government data.",
    "news": "Metadata and snippets only. Publishers keep copyright.",
}
COVERAGE_NOTE = ("Structured regulator and filing data is mostly US sources (SEC, EPA, OSHA, NHTSA, "
                 "CPSC, FDA). News coverage can be global.")


@router.get("/sources", summary="Data source freshness, counts, and license notes")
def sources(p: Principal = Depends(manager), conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    counts = {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"]
              for t in ("companies", "company_aliases", "company_relationships", "facilities", "articles")}
    ev = conn.execute("SELECT source, count(*) AS records, max(reported_at) AS latest "
                      "FROM events GROUP BY source ORDER BY source").fetchall()
    return {"counts": counts, "event_sources": [jsonable(r) for r in ev], "licenses": LICENSES,
            "coverage_note": COVERAGE_NOTE}


# ------------------------------------------------------------------ billing
@router.get("/billing/plan", summary="Current plan and supplier usage (demo data)")
def billing_plan(p: Principal = Depends(tenant_admin), conn: Any = deps.TENANT_DB
                 ) -> dict[str, Any]:
    sub = conn.execute(
        "SELECT s.plan_code, pl.name, s.billing_cycle, s.price, s.started_on, pl.supplier_limit, "
        "pl.overage_per_100 FROM subscriptions s JOIN plans pl ON pl.code = s.plan_code "
        "WHERE s.ended_on IS NULL ORDER BY s.started_on DESC LIMIT 1").fetchone()
    used = conn.execute("SELECT count(*) AS n FROM suppliers").fetchone()["n"]
    return {"demo_data": True, "plan": jsonable(sub) if sub else None, "monitored_suppliers": used}


@router.get("/billing/invoices", summary="Invoices (demo data)")
def billing_invoices(p: Principal = Depends(tenant_admin), conn: Any = deps.TENANT_DB
                     ) -> dict[str, Any]:
    rows = conn.execute("SELECT id, period_month, issued_on, due_on, status, total FROM invoices "
                        "ORDER BY period_month DESC").fetchall()
    return {"demo_data": True, "items": [jsonable(r) for r in rows]}
