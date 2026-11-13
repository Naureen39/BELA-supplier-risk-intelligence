"""Tenant administration: users, API keys, audit log, risk configuration, tenant settings."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, EmailStr, Field

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.auth.tokens import new_api_key
from app.container import Container
from app.core import audit
from app.core.errors import ApiError
from app.events.risk import ConfigError, next_version
from app.routers.common import audit_event, jsonable, keyset, page, parse_uuid
from app.services.risk_config import current_risk_config

router = APIRouter(tags=["admin"])
TENANT_ROLES = ("viewer", "analyst", "manager", "tenant_admin")
admin_user = deps.require_session(P.MANAGE_USERS)
audit_viewer = deps.require_session(P.VIEW_AUDIT)
viewer_dep = deps.require(P.VIEW)


# ------------------------------------------------------------------ tenant settings
class TenantPatch(BaseModel):
    require_mfa: bool | None = None
    retention_days: int | None = Field(default=None, ge=30, le=3650)
    share_feedback_for_training: bool | None = None


@router.get("/tenants/current", summary="Current tenant and its settings")
def tenant_current(p: Principal = Depends(deps.get_principal), t: str = Depends(deps.require_tenant),
                   conn: Any = deps.TENANT_DB) -> dict[str, Any]:
    row = conn.execute("SELECT id, name, industry, region, country, retention_days, require_mfa, "
                       "share_feedback_for_training, created_at FROM tenants WHERE id = %s",
                       (t,)).fetchone()
    if not row:
        raise ApiError(404, "The tenant was not found.", code="not-found")
    return jsonable(row)


@router.patch("/tenants/current", summary="Update tenant settings")
def tenant_patch(body: TenantPatch, p: Principal = Depends(admin_user),
                 t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                 c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    if changes:
        sets = ", ".join(f"{k} = %s" for k in changes)
        conn.execute(f"UPDATE tenants SET {sets} WHERE id = %s", (*changes.values(), t))
        audit_event(c, p, "tenant.settings_changed", "tenant", t, changes)
    return tenant_current(p, t, conn)


# ------------------------------------------------------------------ users
class UserIn(BaseModel):
    email: EmailStr
    role: Literal["viewer", "analyst", "manager", "tenant_admin"]


class UserPatch(BaseModel):
    role: Literal["viewer", "analyst", "manager", "tenant_admin"] | None = None
    is_active: bool | None = None


@router.get("/users", summary="Users of the tenant (assignee lookup)")
def users_lookup(p: Principal = Depends(viewer_dep), conn: Any = deps.TENANT_DB
                 ) -> dict[str, Any]:
    rows = conn.execute("SELECT id, email, role FROM users WHERE is_active ORDER BY email").fetchall()
    return {"items": [jsonable(r) for r in rows]}


@router.get("/admin/users", summary="List users")
def admin_users(cursor: str | None = None, limit: int = 50, p: Principal = Depends(admin_user),
                conn: Any = deps.TENANT_DB, c: Container = Depends(deps.get_container)
                ) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT id, tenant_id, email, role, is_active, last_login_at, created_at FROM users "
        "WHERE (%s::text IS NULL OR (created_at, id) > (%s::timestamptz, %s::uuid)) "
        "ORDER BY created_at, id LIMIT %s",
        (pos and pos[0], pos and pos[0], pos and pos[1], lim + 1)).fetchall()
    return page(c, rows, lim, ("created_at", "id"))


@router.post("/admin/users", status_code=201, summary="Invite a user")
def admin_user_create(body: UserIn, background: BackgroundTasks,
                      p: Principal = Depends(admin_user),
                      t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                      c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    unusable = c.passwords.hash(secrets.token_urlsafe(32))
    exists = conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (body.email,)).fetchone()
    if exists:
        raise ApiError(409, "A user with this email already exists.", code="conflict")
    row = conn.execute(
        "INSERT INTO users (tenant_id, email, password_hash, role) VALUES (%s,%s,%s,%s) "
        "RETURNING id, email, role, is_active", (t, body.email, unusable, body.role)).fetchone()
    audit_event(c, p, "user.created", "user", str(row["id"]), {"role": body.role})
    # The invitation email goes out after the request transaction commits.
    background.add_task(c.auth.forgot_password, body.email)
    return jsonable(row) | {"invitation": "queued"}


@router.patch("/admin/users/{user_id}", summary="Change a user's role or status")
def admin_user_patch(user_id: str, body: UserPatch, p: Principal = Depends(admin_user),
                     conn: Any = deps.TENANT_DB,
                     c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    uid = parse_uuid(user_id, "user")
    if uid == p.user_id and (body.is_active is False or (body.role and body.role != p.role)):
        raise ApiError(409, "You cannot change your own role or deactivate yourself.", code="conflict")
    sets, vals = [], []
    for col, val in (("role", body.role), ("is_active", body.is_active)):
        if val is not None:
            sets.append(f"{col} = %s")
            vals.append(val)
    if not sets:
        raise ApiError(422, "Nothing to change.", code="validation")
    row = conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s AND role <> 'platform_admin' "
                       "RETURNING id, email, role, is_active", (*vals, uid)).fetchone()
    if not row:
        raise ApiError(404, "The user was not found.", code="not-found")
    if body.is_active is False or body.role:
        with c.db.system() as sconn:
            sconn.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = %s AND "
                          "revoked_at IS NULL", (uid,))
    audit_event(c, p, "user.updated", "user", uid, body.model_dump(exclude_none=True))
    return jsonable(row)


# ------------------------------------------------------------------ API keys
class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1)
    expires_in_days: int | None = Field(default=90, ge=1, le=730)


@router.get("/admin/api-keys", summary="List API keys (secrets are never shown again)")
def keys_list(p: Principal = Depends(admin_user), conn: Any = deps.TENANT_DB
              ) -> dict[str, Any]:
    rows = conn.execute("SELECT id, name, prefix, scopes, expires_at, last_used_at, revoked_at, "
                        "created_at FROM api_keys ORDER BY created_at DESC").fetchall()
    return {"items": [jsonable(r) for r in rows]}


@router.post("/admin/api-keys", status_code=201, summary="Create an API key (shown once)")
def keys_create(body: KeyIn, p: Principal = Depends(admin_user),
                t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    bad = set(body.scopes) - P.KEY_SCOPES
    if bad:
        raise ApiError(422, f"Unknown or non-delegable scopes: {', '.join(sorted(bad))}.",
                       code="validation")
    key, prefix, digest = new_api_key()
    expires = datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    row = conn.execute(
        "INSERT INTO api_keys (tenant_id, prefix, secret_hash, name, scopes, expires_at) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (t, prefix, digest, body.name,
                                                    sorted(body.scopes), expires)).fetchone()
    audit_event(c, p, "api_key.created", "api_key", str(row["id"]), {"scopes": sorted(body.scopes)})
    return {"id": str(row["id"]), "name": body.name, "scopes": sorted(body.scopes),
            "expires_at": expires, "key": key,
            "notice": "Store this key now. It cannot be shown again."}


@router.delete("/admin/api-keys/{key_id}", status_code=204, summary="Revoke an API key")
def keys_revoke(key_id: str, p: Principal = Depends(admin_user), conn: Any = deps.TENANT_DB,
                c: Container = Depends(deps.get_container)) -> None:
    kid = parse_uuid(key_id, "API key")
    row = conn.execute("UPDATE api_keys SET revoked_at = coalesce(revoked_at, now()) WHERE id = %s "
                       "RETURNING id", (kid,)).fetchone()
    if not row:
        raise ApiError(404, "The API key was not found.", code="not-found")
    audit_event(c, p, "api_key.revoked", "api_key", kid)


# ------------------------------------------------------------------ audit
@router.get("/admin/audit", summary="Audit log entries for the tenant")
def audit_list(cursor: str | None = None, limit: int = 100, action: str | None = None,
               p: Principal = Depends(audit_viewer), conn: Any = deps.TENANT_DB,
               c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    pos, lim = keyset(c, cursor, limit)
    rows = conn.execute(
        "SELECT seq, occurred_at, tenant_id, actor_user_id, action, target_type, target_id, detail "
        "FROM audit_log WHERE (%s::bigint IS NULL OR seq < %s::bigint) AND "
        "(%s::text IS NULL OR action = %s::text) ORDER BY seq DESC LIMIT %s",
        (pos and pos[0], pos and pos[0], action, action, lim + 1)).fetchall()
    return page(c, rows, lim, ("seq",))


@router.get("/admin/audit/verify", summary="Verify the audit hash chain")
def audit_verify(p: Principal = Depends(audit_viewer), c: Container = Depends(deps.get_container)
                 ) -> dict[str, Any]:
    ok, bad, n = audit.verify_chain(c.db)
    return {"ok": ok, "first_bad_seq": bad, "rows_checked": n}


# ------------------------------------------------------------------ risk configuration
class RiskConfigIn(BaseModel):
    severity_weights: list[float] | None = Field(default=None, min_length=4, max_length=4)
    half_life_regulator_days: float | None = None
    half_life_news_days: float | None = None
    relation_weights: dict[str, float] | None = None
    source_reliability: dict[str, float] | None = None
    impact_cap: float | None = None
    level_thresholds: list[float] | None = Field(default=None, min_length=3, max_length=3)


@router.get("/admin/risk-config", summary="Active risk scoring configuration")
def risk_config_get(p: Principal = Depends(admin_user), conn: Any = deps.TENANT_DB
                    ) -> dict[str, Any]:
    n, cfg = current_risk_config(conn)
    return {"version": n, "config": json.loads(cfg.to_json())}


@router.put("/admin/risk-config", summary="Publish a new risk configuration version")
def risk_config_put(body: RiskConfigIn, p: Principal = Depends(admin_user),
                    t: str = Depends(deps.require_tenant), conn: Any = deps.TENANT_DB,
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    n, cfg = current_risk_config(conn)
    changes = {k: (tuple(v) if isinstance(v, list) else v)
               for k, v in body.model_dump(exclude_none=True).items()}
    try:
        new = next_version(cfg, **changes)
    except ConfigError as exc:
        raise ApiError(422, str(exc), code="config-out-of-bounds") from exc
    version = n + 1
    stored = json.loads(new.to_json())
    conn.execute("INSERT INTO risk_configs (tenant_id, version, config, created_by) "
                 "VALUES (%s,%s,%s::jsonb,%s)", (t, version, json.dumps(stored), p.user_id))
    audit_event(c, p, "risk_config.published", "risk_config", str(version), {"changes": list(changes)})
    return {"version": version, "config": stored}


@router.get("/admin/risk-config/history", summary="Risk configuration versions")
def risk_config_history(p: Principal = Depends(admin_user), conn: Any = deps.TENANT_DB
                        ) -> dict[str, Any]:
    rows = conn.execute("SELECT version, created_by, created_at, config FROM risk_configs "
                        "ORDER BY version DESC").fetchall()
    return {"items": [jsonable(r) for r in rows]}

