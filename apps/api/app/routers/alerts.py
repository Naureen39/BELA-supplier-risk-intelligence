"""Alerts, alert rules, and the live alert stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.errors import ApiError
from app.events_bus import alert_channel
from app.routers.common import audit_event, jsonable, keyset, page, parse_uuid

router = APIRouter(tags=["alerts"])
viewer = deps.require(P.VIEW)
actor = deps.require(P.ALERT_ACTION)
manager = deps.require(P.MANAGE_RULES)

TRANSITIONS: dict[str, set[str]] = {
    "new": {"in_review", "acknowledged", "dismissed", "escalated"},
    "in_review": {"acknowledged", "dismissed", "escalated"},
    "acknowledged": {"in_review", "dismissed", "escalated"},
    "escalated": {"in_review", "acknowledged", "dismissed"},
    "dismissed": {"in_review"},
}


@router.get("/alerts", summary="Alert queue")
def alerts(cursor: str | None = None, limit: int = 50, status: str | None = None,
           assignee: str | None = None, supplier_id: str | None = None,
           p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB,
           c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    sid = parse_uuid(supplier_id, "supplier") if supplier_id else None
    aid = parse_uuid(assignee, "assignee") if assignee else None
    rows = conn.execute(
        "SELECT a.id, a.supplier_id, s.uploaded_name AS supplier_name, a.kind, a.status, a.assignee_id, "
        "a.detail, a.rule_id, a.created_at, a.updated_at FROM alerts a JOIN suppliers s ON s.id = a.supplier_id "
        "WHERE (%s::text IS NULL OR a.status = %s) AND (%s::uuid IS NULL OR a.assignee_id = %s::uuid) "
        "AND (%s::uuid IS NULL OR a.supplier_id = %s::uuid) "
        "AND (%s::text IS NULL OR (a.created_at, a.id) < (%s::timestamptz, %s::uuid)) "
        "ORDER BY a.created_at DESC, a.id DESC LIMIT %s",
        (status, status, aid, aid, sid, sid, pos and pos[0], pos and pos[0], pos and pos[1],
         lim + 1)).fetchall()
    return page(c, rows, lim, ("created_at", "id"))


class AlertPatch(BaseModel):
    status: Literal["new", "in_review", "acknowledged", "dismissed", "escalated"] | None = None
    assignee_id: str | None = None
    reason: str | None = Field(default=None, max_length=500)


@router.patch("/alerts/{alert_id}", summary="Change alert status or assignee")
def alert_patch(alert_id: str, body: AlertPatch, p: Principal = Depends(actor),
                conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
                ) -> dict[str, Any]:
    aid = parse_uuid(alert_id, "alert")
    alert = conn.execute("SELECT * FROM alerts WHERE id = %s FOR UPDATE", (aid,)).fetchone()
    if not alert:
        raise ApiError(404, "The alert was not found.", code="not-found")
    if body.status and body.status != alert["status"]:
        if body.status not in TRANSITIONS.get(alert["status"], set()):
            raise ApiError(409, f"An alert cannot move from {alert['status']} to {body.status}.",
                           code="invalid-transition")
        if body.status == "dismissed" and not (body.reason and body.reason.strip()):
            raise ApiError(422, "A reason is required to dismiss an alert.", code="validation")
        conn.execute("UPDATE alerts SET status = %s, updated_at = now() WHERE id = %s",
                     (body.status, aid))
        conn.execute("INSERT INTO alert_events (alert_id, actor_user_id, change, reason) "
                     "VALUES (%s,%s,%s,%s)", (aid, p.user_id, f"status:{body.status}", body.reason))
    if body.assignee_id is not None:
        who = parse_uuid(body.assignee_id, "assignee")
        if not conn.execute("SELECT 1 FROM users WHERE id = %s AND is_active", (who,)).fetchone():
            raise ApiError(422, "The assignee is not a user of this tenant.", code="validation")
        conn.execute("UPDATE alerts SET assignee_id = %s, updated_at = now() WHERE id = %s", (who, aid))
        conn.execute("INSERT INTO alert_events (alert_id, actor_user_id, change, comment) "
                     "VALUES (%s,%s,'assigned',%s)", (aid, p.user_id, who))
    audit_event(c, p, "alert.updated", "alert", aid, body.model_dump(exclude_none=True))
    row = conn.execute("SELECT id, supplier_id, kind, status, assignee_id, detail, updated_at "
                       "FROM alerts WHERE id = %s", (aid,)).fetchone()
    return jsonable(row)


class CommentIn(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


@router.post("/alerts/{alert_id}/comments", status_code=201, summary="Comment on an alert")
def alert_comment(alert_id: str, body: CommentIn, p: Principal = Depends(actor),
                  conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    aid = parse_uuid(alert_id, "alert")
    if not conn.execute("SELECT 1 FROM alerts WHERE id = %s", (aid,)).fetchone():
        raise ApiError(404, "The alert was not found.", code="not-found")
    row = conn.execute("INSERT INTO alert_events (alert_id, actor_user_id, change, comment) "
                       "VALUES (%s,%s,'comment',%s) RETURNING id, occurred_at",
                       (aid, p.user_id, body.comment)).fetchone()
    return jsonable(row)


@router.get("/alerts/{alert_id}/history", summary="Alert change history")
def alert_history(alert_id: str, p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB
                  ) -> dict[str, Any]:
    rows = conn.execute("SELECT id, actor_user_id, change, reason, comment, occurred_at FROM alert_events "
                        "WHERE alert_id = %s ORDER BY id", (parse_uuid(alert_id, "alert"),)).fetchall()
    return {"items": [jsonable(r) for r in rows]}


# ------------------------------------------------------------------ rules
class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    event_types: list[str] = []
    min_severity: int = Field(default=3, ge=1, le=4)
    supplier_tiers: list[str] = []
    states: list[str] = []
    channels: list[Literal["in_app", "email", "webhook"]] = ["in_app"]
    webhook_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class RulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    event_types: list[str] | None = None
    min_severity: int | None = Field(default=None, ge=1, le=4)
    supplier_tiers: list[str] | None = None
    states: list[str] | None = None
    channels: list[Literal["in_app", "email", "webhook"]] | None = None
    webhook_url: str | None = None
    is_active: bool | None = None


def _check_webhook(url: str | None, channels: Sequence[str] | None) -> None:
    if url and not url.startswith("https://"):
        raise ApiError(422, "Webhook URLs must use https.", code="validation")
    if channels and "webhook" in channels and not url:
        raise ApiError(422, "A webhook URL is required for the webhook channel.", code="validation")


@router.get("/rules", summary="Alert rules")
def rules(p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM alert_rules ORDER BY name").fetchall()
    return {"items": [jsonable(r) for r in rows]}


@router.post("/rules", status_code=201, summary="Create an alert rule")
def rule_create(body: RuleIn, p: Principal = Depends(manager), t: str = Depends(deps.require_tenant),
                conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
                ) -> dict[str, Any]:
    _check_webhook(body.webhook_url, body.channels)
    row = conn.execute(
        "INSERT INTO alert_rules (tenant_id, name, event_types, min_severity, supplier_tiers, states, "
        "channels, webhook_url, is_active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (t, body.name, body.event_types, body.min_severity, body.supplier_tiers,
         [s.upper() for s in body.states], body.channels, body.webhook_url, body.is_active)).fetchone()
    audit_event(c, p, "rule.created", "rule", str(row["id"]))
    return jsonable(row)


@router.patch("/rules/{rule_id}", summary="Update an alert rule")
def rule_patch(rule_id: str, body: RulePatch, p: Principal = Depends(manager),
               conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
               ) -> dict[str, Any]:
    rid = parse_uuid(rule_id, "rule")
    changes = body.model_dump(exclude_none=True)
    _check_webhook(changes.get("webhook_url"), changes.get("channels"))
    if not changes:
        raise ApiError(422, "Nothing to change.", code="validation")
    if "states" in changes:
        changes["states"] = [s.upper() for s in changes["states"]]
    sets = ", ".join(f"{k} = %s" for k in changes)
    row = conn.execute(f"UPDATE alert_rules SET {sets} WHERE id = %s RETURNING *",
                       (*changes.values(), rid)).fetchone()
    if not row:
        raise ApiError(404, "The rule was not found.", code="not-found")
    audit_event(c, p, "rule.updated", "rule", rid, {"fields": sorted(changes)})
    return jsonable(row)


# ------------------------------------------------------------------ live stream
async def sse_events(c: Container, tenant_id: str, request: Request | None = None,
                     heartbeat: float = 15.0) -> AsyncIterator[str]:
    """Server-sent events for one tenant. Sends a comment every `heartbeat` seconds."""
    yield ": connected\n\n"
    stream = c.broker.subscribe(alert_channel(tenant_id))
    it = stream.__aiter__()
    pending: asyncio.Task[Any] | None = None
    try:
        while True:
            if request is not None and await request.is_disconnected():
                return
            pending = pending or asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=heartbeat)
            if not done:
                yield ": keep-alive\n\n"
                continue
            task, pending = pending, None
            try:
                message = task.result()
            except StopAsyncIteration:
                return
            yield f"event: alert\ndata: {json.dumps(message)}\n\n"
    finally:
        if pending is not None:
            pending.cancel()
        await stream.aclose()  # type: ignore[attr-defined]


@router.get("/stream/alerts", summary="Live alerts (server-sent events)")
async def stream_alerts(request: Request, p: Principal = Depends(viewer),
                        t: str = Depends(deps.require_tenant),
                        c: Container = Depends(deps.get_container)) -> StreamingResponse:
    return StreamingResponse(sse_events(c, t, request), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
