"""Tenant analytics: portfolio, quality, and usage with date range, granularity, comparison, cache,
and CSV export (plan sections 6 and 9.2). Row level security scopes every query to the caller."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from app.analytics import tenant as an
from app.analytics.common import Granularity, csv_response_body, require_rows_for_csv, window
from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.cache import cached

router = APIRouter(prefix="/analytics", tags=["analytics"])
manager = deps.require(P.MANAGE_RULES)
TTL = 60


def _respond(body: dict[str, Any], hit: bool, fmt: str, csv_rows: list[dict[str, Any]] | None) -> Any:
    headers = {"X-Cache": "hit" if hit else "miss"}
    if fmt == "csv":
        return Response(csv_response_body(csv_rows or []), media_type="text/csv", headers=headers)
    return JSONResponse(body, headers=headers)


@router.get("/portfolio", summary="Portfolio risk, events, concentration, and top suppliers")
def portfolio(start: date | None = Query(default=None, alias="from"), to: date | None = None,
              granularity: Granularity = "week", compare: bool = False,
              source: str | None = Query(default=None, max_length=40),
              format: Literal["json", "csv"] = "json", section: str | None = None,
              p: Principal = Depends(manager), t: str = Depends(deps.require_tenant),
              conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)) -> Any:
    win = window(start, to, an.default_end(conn))
    key = f"tp:{t}:{win.start}:{win.end}:{granularity}:{int(compare)}:{source}"
    body, hit = cached(c.cache, key, TTL, lambda: an.portfolio(conn, win, granularity, compare, source))
    rows = None
    if format == "csv":
        rows = require_rows_for_csv(section, {
            "kpis": body["kpis"], "risk_index_trend": body["risk_index_trend"]["items"],
            "suppliers_by_level": body["suppliers_by_level_trend"], "events_by_type": body["events_by_type"],
            "event_source_mix": body["event_source_mix"], "risk_by_state": body["risk_by_state"],
            "category_heatmap": body["category_heatmap"],
            "top_risk_suppliers": [{k: v for k, v in r.items() if k not in ("last_event", "sparkline")}
                                   for r in body["top_risk_suppliers"]],
            "concentration": body["concentration_by_parent"].get("groups", [])})
    return _respond(body, hit, format, rows)


@router.get("/quality", summary="Resolution quality, review workload, latency, routing, freshness")
def quality(start: date | None = Query(default=None, alias="from"), to: date | None = None,
            granularity: Granularity = "week", compare: bool = False,
            format: Literal["json", "csv"] = "json", section: str | None = None,
            p: Principal = Depends(manager), t: str = Depends(deps.require_tenant),
            conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)) -> Any:
    win = window(start, to, an.default_end(conn))
    path = c.settings.eval_metrics_path
    key = f"tq:{t}:{win.start}:{win.end}:{granularity}:{int(compare)}"
    body, hit = cached(c.cache, key, TTL, lambda: an.quality(conn, win, granularity, compare, path))
    rows = None
    if format == "csv":
        rows = require_rows_for_csv(section, {
            "resolution_quality": body["resolution_quality"], "review_workload": body["review_workload"],
            "latency_throughput": body["latency_throughput"], "data_freshness": body["data_freshness"],
            "routing": body["routing"]["links"],
            "hybrid_vs_baselines": (body["hybrid_vs_baselines"] or {}).get("systems", [])})
    return _respond(body, hit, format, rows)


@router.get("/usage", summary="Daily usage (demo data)")
def usage(start: date | None = Query(default=None, alias="from"), to: date | None = None,
          granularity: Granularity = "day", compare: bool = False,
          format: Literal["json", "csv"] = "json", p: Principal = Depends(manager),
          t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
          c: Container = Depends(deps.get_container)) -> Any:
    win = window(start, to, an.default_end(conn), default_days=30)
    key = f"tu:{t}:{win.start}:{win.end}:{granularity}:{int(compare)}"
    body, hit = cached(c.cache, key, TTL, lambda: an.usage(conn, win, granularity, compare))
    return _respond(body, hit, format, body["items"])
