"""Platform revenue analytics (plan section 9.1). Demo data. Finance and platform roles only."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from app.analytics import forecast as fc
from app.analytics import revenue as rv
from app.analytics.common import Granularity, csv_response_body, month_floor
from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.cache import cached
from app.core.errors import ApiError
from app.routers.common import audit_event, parse_uuid

router = APIRouter(prefix="/platform/revenue", tags=["revenue"])
viewer = deps.require_session(P.VIEW_REVENUE)
TTL = 300


class RevenueQuery:
    """Shared filters: date range, granularity, comparison period, and cross-filters."""

    def __init__(
        self,
        start: date | None = Query(default=None, alias="from"),
        to: date | None = None,
        granularity: Granularity = "month",
        compare: bool = False,
        plan: str | None = Query(default=None, max_length=40),
        region: str | None = Query(default=None, max_length=40),
        industry: str | None = Query(default=None, max_length=80),
        format: Literal["json", "csv"] = "json",
    ) -> None:
        if granularity != "month":
            raise ApiError(422, "Revenue is recorded monthly. Use granularity=month.", code="validation")
        if start and to and start > to:
            raise ApiError(422, "The start date must not be after the end date.", code="validation")
        self.start, self.to, self.compare, self.format = start, to, compare, format
        self.filters = rv.Filters(plan, region, industry)

    def key(self, name: str, *extra: Any) -> str:
        return (f"rev:{name}:{self.start}:{self.to}:{int(self.compare)}:{self.filters.key()}:"
                + ":".join(str(e) for e in extra))


def _series(c: Container, f: rv.Filters) -> list[dict[str, Any]]:
    def compute() -> list[dict[str, Any]]:
        with c.db.system() as conn:
            return rv.kpi_series(conn, f)

    value, _ = cached(c.cache, f"rev:series:{f.key()}", TTL, compute)
    return value  # type: ignore[no-any-return]


def _serve(c: Container, q: RevenueQuery, name: str, build: Callable[[Any], dict[str, Any]],
           csv_rows: Callable[[dict[str, Any]], list[dict[str, Any]]], *extra: Any) -> Any:
    def compute() -> dict[str, Any]:
        with c.db.system() as conn:
            body = build(conn)
            body["data_as_of"] = rv.freshness(conn)
        body["demo_data"] = True
        return body

    body, hit = cached(c.cache, q.key(name, *extra), TTL, compute)
    headers = {"X-Cache": "hit" if hit else "miss"}
    if q.format == "csv":
        return Response(csv_response_body(csv_rows(body)), media_type="text/csv", headers=headers)
    return JSONResponse(body, headers=headers)


def _month(q: RevenueQuery, series: list[dict[str, Any]], month: date | None) -> date:
    if month:
        return month
    if q.to:
        return q.to
    if not series:
        raise ApiError(404, "There is no revenue data yet.", code="not-found")
    return date.fromisoformat(series[-1]["month_start"])


@router.get("/summary", summary="Latest MRR, ARR, and customers")
def summary(p: Principal = Depends(viewer), c: Container = Depends(deps.get_container)
            ) -> dict[str, Any]:
    series = _series(c, rv.Filters())
    if not series:
        return {"demo_data": True, "month": None, "mrr": 0, "arr": 0, "customers": 0}
    last = series[-1]
    return {"demo_data": True, "month": last["month_start"], "mrr": last["mrr"], "arr": last["arr"],
            "customers": last["customers"]}


@router.get("/kpis", summary="KPI cards: value, change versus the previous period, sparkline")
def kpi_cards(q: RevenueQuery = Depends(), p: Principal = Depends(viewer),
              c: Container = Depends(deps.get_container)) -> Any:
    series = _series(c, q.filters)

    def build(_: Any) -> dict[str, Any]:
        return {**rv.kpis(series, q.start, q.to, q.compare),
                "gross_margin_assumption": rv.GROSS_MARGIN,
                "note": "CAC and payback use all marketing spend and are shown only without filters."}

    return _serve(c, q, "kpis", build, lambda b: [
        {k: i[k] for k in ("key", "label", "unit", "value", "previous", "change_pct")} for i in b["items"]])


@router.get("/mrr", summary="MRR by plan with event annotations")
def mrr(q: RevenueQuery = Depends(), p: Principal = Depends(viewer),
        c: Container = Depends(deps.get_container)) -> Any:
    def build(conn: Any) -> dict[str, Any]:
        return {"items": rv.mrr_by_plan(conn, q.filters, q.start, q.to),
                "annotations": rv.business_events(conn, q.start, q.to)}

    return _serve(c, q, "mrr", build, lambda b: b["items"])


@router.get("/movements", summary="New, expansion, contraction, and churn MRR by month")
def movements(q: RevenueQuery = Depends(), p: Principal = Depends(viewer),
              c: Container = Depends(deps.get_container)) -> Any:
    series = rv.window_months(_series(c, q.filters), q.start, q.to)

    def build(_: Any) -> dict[str, Any]:
        items = [{"month_start": r["month_start"], "start_mrr": round(r["mrr"] - r["net_new_mrr"], 2),
                  "new_mrr": r["new_mrr"], "expansion_mrr": r["expansion_mrr"],
                  "contraction_mrr": r["contraction_mrr"], "churn_mrr": r["churn_mrr"],
                  "net_new_mrr": r["net_new_mrr"], "end_mrr": r["mrr"]} for r in series]
        return {"items": items}

    return _serve(c, q, "movements", build, lambda b: b["items"])


@router.get("/mix", summary="Invoiced subscription versus overage by month")
def mix(q: RevenueQuery = Depends(), p: Principal = Depends(viewer),
        c: Container = Depends(deps.get_container)) -> Any:
    return _serve(c, q, "mix", lambda conn: {"items": rv.revenue_mix(conn, q.filters, q.start, q.to)},
                  lambda b: b["items"])


@router.get("/forecast", summary="Six month MRR projection with an 80 percent interval (estimate)")
def forecast(horizon: int = Query(default=6, ge=1, le=12), q: RevenueQuery = Depends(),
             p: Principal = Depends(viewer), c: Container = Depends(deps.get_container)) -> Any:
    series = [r for r in _series(c, q.filters) if r["mrr"] > 0]

    def build(_: Any) -> dict[str, Any]:
        pts = [(date.fromisoformat(r["month_start"]), float(r["mrr"])) for r in series]
        return fc.forecast_mrr(pts, horizon)

    return _serve(c, q, "forecast", build, lambda b: b["forecast"], horizon)


@router.get("/cohorts", summary="Revenue retention by signup cohort")
def cohorts(q: RevenueQuery = Depends(), p: Principal = Depends(viewer),
            c: Container = Depends(deps.get_container)) -> Any:
    return _serve(c, q, "cohorts", lambda conn: {"items": rv.cohorts(conn, q.filters)},
                  lambda b: b["items"])


@router.get("/breakdown", summary="ARR by plan, region, industry, or acquisition channel")
def breakdown(dimension: Literal["plan", "region", "industry", "channel"] = "region",
              month: date | None = None, q: RevenueQuery = Depends(), p: Principal = Depends(viewer),
              c: Container = Depends(deps.get_container)) -> Any:
    at = _month(q, _series(c, q.filters), month)
    return _serve(c, q, "breakdown", lambda conn: {
        "dimension": dimension, "month": month_floor(at).isoformat(),
        "items": rv.breakdown(conn, dimension, at, q.filters)}, lambda b: b["items"], dimension, at)


@router.get("/concentration", summary="Top customers by share of ARR with a cumulative line")
def concentration(month: date | None = None, q: RevenueQuery = Depends(),
                  p: Principal = Depends(viewer), c: Container = Depends(deps.get_container)) -> Any:
    at = _month(q, _series(c, q.filters), month)
    return _serve(c, q, "concentration", lambda conn: rv.concentration(conn, at, q.filters),
                  lambda b: b["items"], at)


@router.get("/unit-economics", summary="CAC, LTV, and LTV to CAC over time")
def unit_economics(q: RevenueQuery = Depends(), p: Principal = Depends(viewer),
                   c: Container = Depends(deps.get_container)) -> Any:
    series = rv.window_months(_series(c, q.filters), q.start, q.to)

    def build(_: Any) -> dict[str, Any]:
        items = [{k: r[k] for k in ("month_start", "arpa", "cac", "ltv", "ltv_to_cac",
                                    "cac_payback_months")} for r in series]
        return {"items": items, "gross_margin_assumption": rv.GROSS_MARGIN,
                "note": "Gross margin is a fixed assumption. CAC, payback, and LTV use trailing three "
                        "month averages."}

    return _serve(c, q, "unit", build, lambda b: b["items"])


@router.get("/billing-health", summary="Open and overdue invoices with aging buckets")
def billing_health(as_of: date | None = None, q: RevenueQuery = Depends(),
                   p: Principal = Depends(viewer), c: Container = Depends(deps.get_container)) -> Any:
    return _serve(c, q, "billing", lambda conn: rv.billing_health(conn, q.filters, as_of),
                  lambda b: b["items"], as_of)


@router.get("/customers", summary="Customer table with trend, usage versus limit, and health")
def customers(month: date | None = None, status: Literal["active", "churned", "all"] = "active",
              sort: Literal["name", "mrr", "monitored_suppliers", "last_activity", "health"] = "mrr",
              order: Literal["asc", "desc"] = "desc", limit: int = Query(default=50, ge=1, le=200),
              offset: int = Query(default=0, ge=0), q: RevenueQuery = Depends(),
              p: Principal = Depends(viewer), c: Container = Depends(deps.get_container)) -> Any:
    at = _month(q, _series(c, q.filters), month)

    def build(conn: Any) -> dict[str, Any]:
        rows = rv.customers(conn, at, q.filters, status)

        def sort_key(r: dict[str, Any]) -> Any:
            v = r.get("health") if sort == "health" else r.get(sort)
            if sort == "health":
                v = rv.HEALTH_ORDER.get(str(v), 9)
            return (v is None, v if v is not None else 0)

        rows.sort(key=lambda r: str(r["name"]))
        rows.sort(key=sort_key, reverse=order == "desc")
        return {"total": len(rows), "limit": limit, "offset": offset, "items": rows[offset:offset + limit]}

    return _serve(c, q, "customers", build,
                  lambda b: [{k: v for k, v in r.items() if k != "mrr_trend"} for r in b["items"]],
                  at, status, sort, order, limit, offset)


@router.get("/customers/{tenant_id}", summary="Customer drill-down: subscriptions, invoices, usage")
def customer_detail(tenant_id: str, p: Principal = Depends(viewer),
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    with c.db.system() as conn:
        out = rv.customer_detail(conn, parse_uuid(tenant_id, "customer"))
    if out is None:
        raise ApiError(404, "The customer was not found.", code="not-found")
    return {"demo_data": True, **out}


@router.post("/refresh", summary="Rebuild the revenue views now")
def refresh(p: Principal = Depends(viewer), c: Container = Depends(deps.get_container)
            ) -> dict[str, Any]:
    with c.db.system() as conn:
        counts = rv.refresh_views(conn)
    c.cache.invalidate()
    audit_event(c, p, "revenue.views_refreshed", "analytics", None, {"rows": counts})
    return {"refreshed": counts}
