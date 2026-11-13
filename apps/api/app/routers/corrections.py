"""Correction requests: tenants flag wrong links or outdated records; the platform reviews them."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.errors import ApiError
from app.routers.common import audit_event, jsonable, keyset, page, parse_uuid

router = APIRouter(tags=["corrections"])
viewer = deps.require(P.VIEW)
platform_admin = deps.require_session(P.PLATFORM)


class CorrectionIn(BaseModel):
    kind: Literal["wrong_link", "outdated_record", "other"]
    description: str = Field(min_length=1, max_length=2000)
    supplier_id: str | None = None
    event_id: int | None = None
    company_id: int | None = None

    model_config = {"json_schema_extra": {"examples": [{
        "kind": "wrong_link", "description": "This event names a different company with a similar name.",
        "event_id": 1, "supplier_id": None}]}}


@router.post("/corrections", status_code=201, summary="Flag a wrong link or an outdated record")
def create(body: CorrectionIn, p: Principal = Depends(viewer), t: str = Depends(deps.require_tenant),
           conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    if not (body.supplier_id or body.event_id or body.company_id):
        raise ApiError(422, "Reference a supplier, an event, or a company.", code="validation")
    sid = parse_uuid(body.supplier_id, "supplier") if body.supplier_id else None
    if sid and not conn.execute("SELECT 1 FROM suppliers WHERE id = %s", (sid,)).fetchone():
        raise ApiError(404, "The supplier was not found.", code="not-found")
    if body.event_id and not conn.execute("SELECT 1 FROM events WHERE id = %s", (body.event_id,)).fetchone():
        raise ApiError(404, "The event was not found.", code="not-found")
    if body.company_id and not conn.execute("SELECT 1 FROM companies WHERE id = %s",
                                            (body.company_id,)).fetchone():
        raise ApiError(404, "The company was not found.", code="not-found")
    row = conn.execute(
        "INSERT INTO corrections (tenant_id, supplier_id, event_id, company_id, kind, description, created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id, status, created_at",
        (t, sid, body.event_id, body.company_id, body.kind, body.description, p.user_id)).fetchone()
    audit_event(c, p, "correction.created", "correction", str(row["id"]), {"kind": body.kind})
    return jsonable(row)


@router.get("/corrections", summary="Corrections raised by this tenant, with their status")
def mine(cursor: str | None = None, limit: int = 50, status: str | None = None,
         p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB,
         c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT id, kind, description, status, response, supplier_id, event_id, company_id, created_at, "
        "decided_at FROM corrections WHERE (%s::text IS NULL OR status = %s) "
        "AND (%s::text IS NULL OR (created_at, id) < (%s::timestamptz, %s::uuid)) "
        "ORDER BY created_at DESC, id DESC LIMIT %s",
        (status, status, pos and pos[0], pos and pos[0], pos and pos[1], lim + 1)).fetchall()
    return page(c, rows, lim, ("created_at", "id"))


@router.get("/platform/corrections", summary="Corrections from all tenants (platform review queue)")
def platform_list(cursor: str | None = None, limit: int = 50, status: str = "open",
                  p: Principal = Depends(platform_admin), conn: Any = deps.TENANT_DB,
                  c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT co.id, co.tenant_id, co.kind, co.description, co.status, co.supplier_id, co.event_id, "
        "co.company_id, co.created_at, e.title AS event_title, c.canonical_name AS company_name "
        "FROM corrections co LEFT JOIN events e ON e.id = co.event_id "
        "LEFT JOIN companies c ON c.id = co.company_id WHERE co.status = %s "
        "AND (%s::text IS NULL OR (co.created_at, co.id) > (%s::timestamptz, %s::uuid)) "
        "ORDER BY co.created_at, co.id LIMIT %s",
        (status, pos and pos[0], pos and pos[0], pos and pos[1], lim + 1)).fetchall()
    return page(c, rows, lim, ("created_at", "id"))


class CorrectionDecision(BaseModel):
    status: Literal["accepted", "rejected", "closed"]
    response: str = Field(min_length=1, max_length=2000)


@router.patch("/platform/corrections/{correction_id}", summary="Respond to a correction")
def platform_decide(correction_id: str, body: CorrectionDecision, p: Principal = Depends(platform_admin),
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    cid = parse_uuid(correction_id, "correction")
    with c.db.system() as conn:
        row = conn.execute(
            "UPDATE corrections SET status = %s, response = %s, decided_by = %s, decided_at = now() "
            "WHERE id = %s AND status = 'open' RETURNING id, tenant_id", (body.status, body.response,
                                                                         p.user_id, cid)).fetchone()
    if not row:
        raise ApiError(404, "The open correction was not found.", code="not-found")
    audit_event(c, p, "correction.decided", "correction", cid, {"status": body.status})
    return {"id": cid, "status": body.status}
