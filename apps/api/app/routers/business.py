"""Reports, data sources, analytics, and billing (tenant views)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.csvsafe import to_csv
from app.core.errors import ApiError
from app.routers.common import audit_event, jsonable, parse_uuid

router = APIRouter(tags=["reports", "sources", "analytics", "billing"])
manager = deps.require(P.MANAGE_RULES)
tenant_admin = deps.require_session(P.MANAGE_USERS)
DISCLAIMER = "Risk signals are leads for human review and not statements of fault."


# ------------------------------------------------------------------ reports
def _report_view(row: dict[str, Any]) -> dict[str, Any]:
    out = jsonable(row, drop=("tenant_id",))
    out["status"] = "ready" if row["storage_path"] else "queued"
    out["disclaimer"] = DISCLAIMER
    return out


@router.post("/reports/supplier/{supplier_id}", status_code=202, summary="Request a supplier report")
def report_supplier(supplier_id: str, p: Principal = Depends(manager),
                    t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    sid = parse_uuid(supplier_id, "supplier")
    if not conn.execute("SELECT 1 FROM suppliers WHERE id = %s", (sid,)).fetchone():
        raise ApiError(404, "The supplier was not found.", code="not-found")
    row = conn.execute("INSERT INTO reports (tenant_id, kind, supplier_id, created_by) "
                       "VALUES (%s,'supplier',%s,%s) RETURNING *", (t, sid, p.user_id)).fetchone()
    audit_event(c, p, "report.requested", "report", str(row["id"]), {"kind": "supplier"})
    return _report_view(row)


@router.post("/reports/portfolio", status_code=202, summary="Request a portfolio report")
def report_portfolio(p: Principal = Depends(manager), t: str = Depends(deps.require_tenant),
                     conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
                     ) -> dict[str, Any]:
    row = conn.execute("INSERT INTO reports (tenant_id, kind, created_by) "
                       "VALUES (%s,'portfolio',%s) RETURNING *", (t, p.user_id)).fetchone()
    audit_event(c, p, "report.requested", "report", str(row["id"]), {"kind": "portfolio"})
    return _report_view(row)


@router.get("/reports/{report_id}", summary="Report status")
def report_get(report_id: str, p: Principal = Depends(manager), conn: Any = deps.TENANT_DB
               ) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM reports WHERE id = %s", (parse_uuid(report_id, "report"),)).fetchone()
    if not row:
        raise ApiError(404, "The report was not found.", code="not-found")
    return _report_view(row)


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


# ------------------------------------------------------------------ analytics
@router.get("/analytics/portfolio", summary="Portfolio risk summary")
def analytics_portfolio(days: int = 30, p: Principal = Depends(manager),
                        conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    days = min(max(days, 1), 3650)
    by_status = conn.execute("SELECT status, count(*) AS n FROM suppliers GROUP BY status").fetchall()
    levels = conn.execute(
        "SELECT rs.level, count(*) AS n FROM suppliers s JOIN LATERAL (SELECT level FROM risk_scores r "
        "WHERE r.supplier_id = s.id ORDER BY computed_at DESC, id DESC LIMIT 1) rs ON true "
        "GROUP BY rs.level").fetchall()
    events = conn.execute(
        "SELECT e.event_type, count(DISTINCT e.id) AS n FROM events e JOIN event_entities ee ON ee.event_id = e.id "
        "JOIN suppliers s ON s.resolved_company_id = ee.company_id WHERE ee.route = 'accepted' "
        "AND e.reported_at >= now() - make_interval(days => %s) GROUP BY e.event_type ORDER BY n DESC",
        (days,)).fetchall()
    open_alerts = conn.execute("SELECT count(*) AS n FROM alerts WHERE status IN ('new','in_review')"
                               ).fetchone()["n"]
    return {"days": days, "suppliers_by_status": {r["status"]: r["n"] for r in by_status},
            "suppliers_by_level": {r["level"]: r["n"] for r in levels},
            "events_by_type": {r["event_type"]: r["n"] for r in events}, "open_alerts": open_alerts,
            "disclaimer": DISCLAIMER}


@router.get("/analytics/quality", summary="Resolution quality and review workload")
def analytics_quality(p: Principal = Depends(manager), conn: Any = deps.TENANT_DB
                      ) -> dict[str, Any]:
    status = conn.execute("SELECT status, count(*) AS n FROM suppliers GROUP BY status").fetchall()
    reviews = conn.execute("SELECT status, count(*) AS n FROM resolution_reviews GROUP BY status").fetchall()
    median = conn.execute(
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM decided_at - created_at) / 60) "
        "AS minutes FROM resolution_reviews WHERE decided_at IS NOT NULL").fetchone()["minutes"]
    total = sum(r["n"] for r in status) or 1
    auto = sum(r["n"] for r in status if r["status"] == "auto_resolved")
    return {"resolution_status": {r["status"]: r["n"] for r in status},
            "reviews": {r["status"]: r["n"] for r in reviews},
            "auto_resolution_rate": auto / total,
            "median_review_minutes": float(median) if median is not None else None}


@router.get("/analytics/usage", summary="Daily usage (demo data)")
def analytics_usage(start: date | None = None, end: date | None = None,
                    format: Literal["json", "csv"] = "json", p: Principal = Depends(manager),
                    conn: Any = deps.TENANT_DB) -> Any:
    rows = conn.execute(
        "SELECT day, monitored_suppliers, resolutions, events_matched, alerts, api_calls FROM usage_daily "
        "WHERE (%s::date IS NULL OR day >= %s::date) AND (%s::date IS NULL OR day <= %s::date) "
        "ORDER BY day", (start, start, end, end)).fetchall()
    if format == "csv":
        cols = ["day", "monitored_suppliers", "resolutions", "events_matched", "alerts", "api_calls"]
        return Response(to_csv(cols, [[r[k] for k in cols] for r in rows]), media_type="text/csv")
    return {"demo_data": True, "items": [jsonable(r) for r in rows]}


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
