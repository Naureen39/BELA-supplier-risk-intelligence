"""Suppliers, uploads, resolution reviews, and the single-record resolve endpoint."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.csvsafe import to_csv
from app.core.errors import ApiError
from app.repo.family import related_companies
from app.routers.common import audit_event, jsonable, keyset, page, parse_uuid
from app.services import resolution as svc

router = APIRouter(tags=["suppliers"])
viewer = deps.require(P.VIEW)
operator = deps.require(P.UPLOAD_REVIEW)
DISCLAIMER = "Risk signals are leads for human review and not statements of fault."


# ------------------------------------------------------------------ resolve
class ResolveIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    state: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=300)
    website: str | None = Field(default=None, max_length=200)
    cik: int | None = None
    lei: str | None = Field(default=None, max_length=30)
    ticker: str | None = Field(default=None, max_length=12)

    model_config = {"json_schema_extra": {"examples": [
        {"name": "NORTHGATE METALS CORP", "state": "PA", "city": "Pittsburgh"}]}}


@router.post("/resolve", summary="Resolve one supplier record to a canonical company")
def resolve(body: ResolveIn, p: Principal = Depends(operator), _l: None = Depends(deps.limit_principal),
            c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    from app.resolution.models import QueryRecord

    rec = QueryRecord("api", **body.model_dump())
    return svc.resolution_view(svc.get_resolver(c).resolve(rec))


# ------------------------------------------------------------------ uploads
def _upload_view(row: dict[str, Any]) -> dict[str, Any]:
    return jsonable(row, drop=("tenant_id",))


@router.post("/uploads", status_code=202, summary="Upload a supplier list (CSV)")
async def upload(background: BackgroundTasks, request: Request, response: Response,
                 file: UploadFile = File(...), mapping: str | None = Form(default=None),
                 idempotency_key: str | None = Header(default=None, max_length=100),
                 p: Principal = Depends(operator), t: str = Depends(deps.require_tenant),
                 c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    name = (file.filename or "").lower()
    if not name.endswith(".csv") or (file.content_type or "") not in (
            "text/csv", "application/csv", "application/vnd.ms-excel", "text/plain",
            "application/octet-stream"):
        raise ApiError(415, "Upload a .csv file.", code="unsupported-media")
    raw = await file.read(c.settings.max_upload_bytes + 1)
    if len(raw) > c.settings.max_upload_bytes:
        raise ApiError(413, "The file is too large.", code="too-large")
    try:
        explicit = json.loads(mapping) if mapping else None
        if explicit is not None and not isinstance(explicit, dict):
            raise ValueError
        rows, errors, used = svc.parse_csv(raw, explicit, c.settings.max_upload_rows)
    except json.JSONDecodeError as exc:
        raise ApiError(422, "The column mapping must be a JSON object.", code="validation") from exc
    except ValueError as exc:
        raise ApiError(422, str(exc), code="invalid-upload") from exc

    with c.db.tenant(t) as conn:
        if idempotency_key:
            existing = conn.execute("SELECT * FROM supplier_uploads WHERE idempotency_key = %s",
                                    (idempotency_key,)).fetchone()
            if existing:
                response.status_code = 200
                return _upload_view(existing) | {"idempotent_replay": True}
        up = conn.execute(
            "INSERT INTO supplier_uploads (tenant_id, uploaded_by, filename, idempotency_key, status, "
            "row_count, errors) VALUES (%s,%s,%s,%s,'processing',%s,%s::jsonb) RETURNING *",
            (t, p.user_id, (file.filename or "upload.csv")[:200], idempotency_key, len(rows),
             json.dumps(errors))).fetchone()
        with conn.cursor() as cur:
            for r in rows:
                sensitive = {k: r.pop(k) for k in svc.SENSITIVE if r.get(k)}
                attrs = {k: v for k, v in r.items() if v and k not in svc.SENSITIVE and k != "tier"}
                cur.execute(
                    "INSERT INTO suppliers (tenant_id, upload_id, uploaded_name, attributes, tier, "
                    "identifiers_encrypted) VALUES (%s,%s,%s,%s::jsonb,%s,"
                    "CASE WHEN %s::text IS NULL THEN NULL ELSE pgp_sym_encrypt(%s::text, %s) END)",
                    (t, up["id"], r["name"], json.dumps(attrs), r.get("tier"),
                     json.dumps(sensitive) if sensitive else None,
                     json.dumps(sensitive) if sensitive else None, c.cipher.raw_key))
    audit_event(c, p, "upload.created", "upload", str(up["id"]),
                {"rows": len(rows), "errors": len(errors)})
    background.add_task(svc.process_upload, c, t, str(up["id"]))
    return _upload_view(up) | {"mapping": used}


@router.get("/uploads/{upload_id}", summary="Upload progress and result summary")
def upload_get(upload_id: str, p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB
               ) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM supplier_uploads WHERE id = %s",
                       (parse_uuid(upload_id, "upload"),)).fetchone()
    if not row:
        raise ApiError(404, "The upload was not found.", code="not-found")
    return _upload_view(row)


# ------------------------------------------------------------------ suppliers
_SUPPLIER_SELECT = (
    "SELECT s.id, s.uploaded_name, s.tier, s.status, s.confidence, s.created_at, "
    "s.resolved_company_id, co.canonical_name AS company_name, rs.score AS risk_score, "
    "rs.level AS risk_level, (s.identifiers_encrypted IS NOT NULL) AS has_sensitive_identifiers "
    "FROM suppliers s LEFT JOIN companies co ON co.id = s.resolved_company_id "
    "LEFT JOIN LATERAL (SELECT score, level FROM risk_scores r WHERE r.supplier_id = s.id "
    "ORDER BY computed_at DESC, id DESC LIMIT 1) rs ON true ")


@router.get("/suppliers", summary="List suppliers")
def suppliers(cursor: str | None = None, limit: int = 50, status: str | None = None,
              tier: str | None = None, q: str | None = None, risk_level: str | None = None,
              format: Literal["json", "csv"] = "json", p: Principal = Depends(viewer),
              conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
              ) -> Any:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        _SUPPLIER_SELECT + "WHERE (%s::text IS NULL OR s.status = %s) AND (%s::text IS NULL OR s.tier = %s) "
        "AND (%s::text IS NULL OR s.uploaded_name ILIKE '%%' || %s || '%%') "
        "AND (%s::text IS NULL OR rs.level = %s) "
        "AND (%s::text IS NULL OR (s.created_at, s.id) < (%s::timestamptz, %s::uuid)) "
        "ORDER BY s.created_at DESC, s.id DESC LIMIT %s",
        (status, status, tier, tier, q, q, risk_level, risk_level, pos and pos[0], pos and pos[0],
         pos and pos[1], lim + 1)).fetchall()
    if format == "csv":
        body = to_csv(["id", "supplier", "canonical_company_id", "canonical_company", "status",
                       "confidence", "tier", "risk_score", "risk_level"],
                      [[str(r["id"]), r["uploaded_name"], r["resolved_company_id"], r["company_name"],
                        r["status"], r["confidence"], r["tier"], r["risk_score"], r["risk_level"]]
                       for r in rows[:lim]])
        return Response(body, media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="suppliers.csv"'})
    return page(c, rows, lim, ("created_at", "id")) | {"disclaimer": DISCLAIMER}


class SupplierIn(ResolveIn):
    tier: str | None = Field(default=None, max_length=40)


@router.post("/suppliers", status_code=201, summary="Add one supplier and resolve it")
def supplier_create(body: SupplierIn, p: Principal = Depends(operator),
                    t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    attrs = {k: v for k, v in body.model_dump().items() if v is not None and k not in ("name", "tier")}
    res = svc.get_resolver(c).resolve(svc.to_query("new", {"name": body.name, **attrs}))
    status = svc.status_for(res.route)
    row = conn.execute(
        "INSERT INTO suppliers (tenant_id, uploaded_name, attributes, tier, status, resolved_company_id, "
        "confidence, resolution_detail) VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb) RETURNING id",
        (t, body.name, json.dumps(attrs), body.tier, status,
         res.company_id if status == "auto_resolved" else None, min(max(res.probability, 0), 1),
         json.dumps({"method": res.method, "route": res.route.value}))).fetchone()
    if status == "needs_review":
        conn.execute("INSERT INTO resolution_reviews (tenant_id, supplier_id, candidates) "
                     "VALUES (%s,%s,%s::jsonb)",
                     (t, row["id"], json.dumps(svc.resolution_view(res)["candidates"])))
    audit_event(c, p, "supplier.created", "supplier", str(row["id"]))
    return {"id": str(row["id"]), "status": status, "resolution": svc.resolution_view(res)}


class SupplierPatch(BaseModel):
    tier: str | None = Field(default=None, max_length=40)


@router.patch("/suppliers/{supplier_id}", summary="Update supplier tier")
def supplier_patch(supplier_id: str, body: SupplierPatch, p: Principal = Depends(operator),
                   conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
                   ) -> dict[str, Any]:
    sid = parse_uuid(supplier_id, "supplier")
    row = conn.execute("UPDATE suppliers SET tier = %s WHERE id = %s RETURNING id, tier",
                       (body.tier, sid)).fetchone()
    if not row:
        raise ApiError(404, "The supplier was not found.", code="not-found")
    audit_event(c, p, "supplier.updated", "supplier", sid, {"tier": body.tier})
    return jsonable(row)


def _supplier(conn: Any, supplier_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT id, uploaded_name, resolved_company_id FROM suppliers WHERE id = %s",
                       (parse_uuid(supplier_id, "supplier"),)).fetchone()
    if not row:
        raise ApiError(404, "The supplier was not found.", code="not-found")
    return dict(row)


@router.get("/suppliers/{supplier_id}/risk", summary="Risk score with every component")
def supplier_risk(supplier_id: str, p: Principal = Depends(viewer),
                  conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    sup = _supplier(conn, supplier_id)
    score = conn.execute("SELECT id, score, level, config_version, computed_at FROM risk_scores "
                         "WHERE supplier_id = %s ORDER BY computed_at DESC, id DESC LIMIT 1",
                         (sup["id"],)).fetchone()
    if not score:
        return {"supplier_id": str(sup["id"]), "score": None, "components": [],
                "disclaimer": DISCLAIMER}
    comps = conn.execute(
        "SELECT c.event_id, c.category, c.severity_weight, c.recency_decay, c.link_confidence, "
        "c.relation_weight, c.source_reliability, c.event_impact, e.title, e.source, e.url, "
        "e.reported_at FROM risk_score_components c JOIN events e ON e.id = c.event_id "
        "WHERE c.risk_score_id = %s ORDER BY c.event_impact DESC", (score["id"],)).fetchall()
    return {"supplier_id": str(sup["id"]), "score": float(score["score"]), "level": score["level"],
            "config_version": score["config_version"], "computed_at": score["computed_at"],
            "components": [jsonable(r) for r in comps], "disclaimer": DISCLAIMER}


@router.get("/suppliers/{supplier_id}/events", summary="Events that reach this supplier")
def supplier_events(supplier_id: str, cursor: str | None = None, limit: int = 50,
                    p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB,
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    sup = _supplier(conn, supplier_id)
    if sup["resolved_company_id"] is None:
        return {"items": [], "next_cursor": None, "disclaimer": DISCLAIMER}
    related = related_companies(conn, int(sup["resolved_company_id"]))
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT DISTINCT ON (e.reported_at, e.id) e.id, e.source, e.event_type, e.severity, "
        "e.occurred_at, e.reported_at, e.title, e.url, e.state, ee.company_id AS via_company_id "
        "FROM events e JOIN event_entities ee ON ee.event_id = e.id "
        "WHERE ee.company_id = ANY(%s) AND ee.route = 'accepted' "
        "AND (%s::text IS NULL OR (e.reported_at, e.id) < (%s::timestamptz, %s::bigint)) "
        "ORDER BY e.reported_at DESC, e.id DESC LIMIT %s",
        (list(related), pos and pos[0], pos and pos[0], pos and pos[1], lim + 1)).fetchall()
    out = page(c, rows, lim, ("reported_at", "id"))
    for item in out["items"]:
        rel, path = related[item["via_company_id"]]
        item["relation"], item["path"] = rel, list(path)
    return out | {"disclaimer": DISCLAIMER}


# ------------------------------------------------------------------ reviews
@router.get("/reviews", summary="Resolution review queue")
def reviews(cursor: str | None = None, limit: int = 50, status: str = "open",
            p: Principal = Depends(operator), conn: Any = deps.TENANT_DB,
            c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT r.id, r.status, r.candidates, r.created_at, s.id AS supplier_id, s.uploaded_name, "
        "s.attributes FROM resolution_reviews r JOIN suppliers s ON s.id = r.supplier_id "
        "WHERE r.status = %s AND (%s::text IS NULL OR (r.created_at, r.id) > (%s::timestamptz, %s::uuid)) "
        "ORDER BY r.created_at, r.id LIMIT %s",
        (status, pos and pos[0], pos and pos[0], pos and pos[1], lim + 1)).fetchall()
    return page(c, rows, lim, ("created_at", "id"))


class ReviewDecision(BaseModel):
    action: Literal["accept", "reject", "choose_other", "mark_unresolved"]
    company_id: int | None = None


@router.patch("/reviews/{review_id}", summary="Decide a review")
def review_decide(review_id: str, body: ReviewDecision, p: Principal = Depends(operator),
                  conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
                  ) -> dict[str, Any]:
    rid = parse_uuid(review_id, "review")
    rev = conn.execute("SELECT * FROM resolution_reviews WHERE id = %s FOR UPDATE", (rid,)).fetchone()
    if not rev:
        raise ApiError(404, "The review was not found.", code="not-found")
    if rev["status"] != "open":
        raise ApiError(409, "This review has already been decided.", code="conflict")
    chosen: int | None = None
    if body.action == "accept":
        if not rev["candidates"]:
            raise ApiError(409, "There is no candidate to accept.", code="conflict")
        chosen = int(rev["candidates"][0]["company_id"])
    elif body.action == "choose_other":
        if body.company_id is None or not conn.execute(
                "SELECT 1 FROM companies WHERE id = %s", (body.company_id,)).fetchone():
            raise ApiError(422, "Choose an existing company.", code="validation")
        chosen = body.company_id
    status = {"accept": "accepted", "choose_other": "chose_other", "reject": "rejected",
              "mark_unresolved": "unresolved"}[body.action]
    conn.execute("UPDATE resolution_reviews SET status = %s, chosen_company_id = %s, reviewer_id = %s, "
                 "decided_at = now() WHERE id = %s", (status, chosen, p.user_id, rid))
    conn.execute("UPDATE suppliers SET status = %s, resolved_company_id = %s, confidence = %s, "
                 "resolution_detail = resolution_detail || %s::jsonb WHERE id = %s",
                 ("resolved" if chosen else "unresolved", chosen, 1.0 if chosen else 0.0,
                  json.dumps({"human_decision": body.action}), rev["supplier_id"]))
    audit_event(c, p, "review.decided", "review", rid, {"action": body.action, "company_id": chosen})
    return {"id": rid, "status": status, "company_id": chosen}


