"""Platform administration: tenants, platform review queue, revenue."""

from __future__ import annotations

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, EmailStr, Field

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.errors import ApiError
from app.routers.common import audit_event, jsonable, keyset, page

router = APIRouter(prefix="/platform", tags=["platform"])
platform_admin = deps.require_session(P.PLATFORM)
revenue_viewer = deps.require_session(P.VIEW_REVENUE)


class TenantIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    industry: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=40)
    admin_email: EmailStr


@router.get("/tenants", summary="All tenants")
def tenants(p: Principal = Depends(platform_admin), conn: Any = deps.TENANT_DB
            ) -> dict[str, Any]:
    rows = conn.execute("SELECT id, name, industry, region, require_mfa, created_at, churned_at "
                        "FROM tenants ORDER BY created_at DESC").fetchall()
    return {"items": [jsonable(r) for r in rows]}


@router.post("/tenants", status_code=201, summary="Create a tenant with its first administrator")
def tenant_create(body: TenantIn, background: BackgroundTasks, p: Principal = Depends(platform_admin),
                  c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    with c.db.system() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)",
                        (body.admin_email,)).fetchone():
            raise ApiError(409, "A user with this email already exists.", code="conflict")
        t = conn.execute("INSERT INTO tenants (name, industry, region) VALUES (%s,%s,%s) RETURNING id",
                         (body.name, body.industry, body.region)).fetchone()
        conn.execute("INSERT INTO users (tenant_id, email, password_hash, role) "
                     "VALUES (%s,%s,%s,'tenant_admin')",
                     (t["id"], body.admin_email, c.passwords.hash(secrets.token_urlsafe(32))))
    background.add_task(c.auth.forgot_password, body.admin_email)
    audit_event(c, p, "tenant.created", "tenant", str(t["id"]))
    return {"id": str(t["id"]), "name": body.name, "invitation": "queued"}


@router.get("/review-queue", summary="Low-confidence regulator links awaiting platform review")
def review_queue(cursor: str | None = None, limit: int = 50, p: Principal = Depends(platform_admin),
                 conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
                 ) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT ee.id, ee.route, ee.method, ee.score, ee.role, e.title, e.source, e.reported_at, "
        "(SELECT jsonb_agg(jsonb_build_object('company_id', lc.company_id, 'rank', lc.rank, "
        "'name', co.canonical_name) ORDER BY lc.rank) FROM link_candidates lc "
        "JOIN companies co ON co.id = lc.company_id WHERE lc.event_entity_id = ee.id) AS candidates "
        "FROM event_entities ee JOIN events e ON e.id = ee.event_id "
        "WHERE ee.route IN ('review','nil') AND (%s::bigint IS NULL OR ee.id > %s::bigint) "
        "ORDER BY ee.id LIMIT %s", (pos and pos[0], pos and pos[0], lim + 1)).fetchall()
    return page(c, rows, lim, ("id",))


class ReviewDecision(BaseModel):
    decision: Literal["accept", "reject"]
    company_id: int | None = None


@router.patch("/review-queue/{entity_id}", summary="Decide a queued link")
def review_decide(entity_id: int, body: ReviewDecision, p: Principal = Depends(platform_admin),
                  c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    if body.decision == "accept" and body.company_id is None:
        raise ApiError(422, "company_id is required to accept a link.", code="validation")
    with c.db.system() as conn:  # writes to global tables use the system connection
        row = conn.execute(
            "UPDATE event_entities SET company_id = %s, route = %s, method = 'platform_review', "
            "score = 1 WHERE id = %s AND route IN ('review','nil') RETURNING id",
            (body.company_id if body.decision == "accept" else None,
             "accepted" if body.decision == "accept" else "nil", entity_id)).fetchone()
    if not row:
        raise ApiError(404, "The queue item was not found.", code="not-found")
    audit_event(c, p, "platform.review_decided", "event_entity", str(entity_id),
                {"decision": body.decision, "company_id": body.company_id})
    return {"id": entity_id, "decision": body.decision}


@router.get("/revenue/mrr", summary="Monthly recurring revenue by plan")
def revenue_mrr(start: Annotated[str | None, Query(alias="from")] = None, to: str | None = None,
                p: Principal = Depends(revenue_viewer), conn: Any = deps.TENANT_DB
                ) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT month_start, plan_code, sum(mrr) AS mrr, count(DISTINCT tenant_id) AS customers "
        "FROM mrr_monthly WHERE (%s::date IS NULL OR month_start >= %s::date) AND "
        "(%s::date IS NULL OR month_start <= %s::date) GROUP BY 1, 2 ORDER BY 1, 2",
        (start, start, to, to)).fetchall()
    return {"demo_data": True, "items": [jsonable(r) for r in rows]}


@router.get("/revenue/summary", summary="Latest MRR, ARR, and customers")
def revenue_summary(p: Principal = Depends(revenue_viewer), conn: Any = deps.TENANT_DB
                    ) -> dict[str, Any]:
    row = conn.execute(
        "SELECT month_start, sum(mrr) AS mrr, count(DISTINCT tenant_id) AS customers "
        "FROM mrr_monthly WHERE month_start = (SELECT max(month_start) FROM mrr_monthly) "
        "GROUP BY month_start").fetchone()
    if not row:
        return {"demo_data": True, "month": None, "mrr": 0, "arr": 0, "customers": 0}
    mrr = float(row["mrr"])
    return {"demo_data": True, "month": row["month_start"], "mrr": mrr, "arr": mrr * 12,
            "customers": int(row["customers"])}
