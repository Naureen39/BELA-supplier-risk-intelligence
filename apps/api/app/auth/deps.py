"""FastAPI dependencies: principal resolution, permission checks, CSRF, tenant connections."""

from __future__ import annotations

import hmac
import secrets
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request, Response

from app.auth import permissions as P
from app.auth.tokens import TokenError, hash_token, split_api_key
from app.container import Container
from app.core import audit
from app.core.errors import ApiError
from app.repo import auth as repo

ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE = "pr_access", "pr_refresh", "pr_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class Principal:
    kind: str  # session or api_key
    user_id: str | None
    tenant_id: str | None
    role: str
    permissions: frozenset[str]
    email: str | None = None
    family_id: str | None = None
    key_id: str | None = None
    platform_scope: bool = False  # platform administrator without a tenant context


def get_container(request: Request) -> Container:
    c: Container = request.app.state.container
    return c


def _unauth() -> ApiError:
    return ApiError(401, "Authentication is required.", code="unauthenticated",
                    headers={"WWW-Authenticate": "Bearer"})


def get_principal(request: Request, container: Container = Depends(get_container)) -> Principal:
    cached: Principal | None = getattr(request.state, "principal", None)
    if cached:
        return cached
    principal = _resolve(request, container)
    request.state.principal = principal
    return principal


def _resolve(request: Request, c: Container) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return _from_api_key(auth[7:].strip(), c)
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise _unauth()
    try:
        claims = c.tokens.read_access(token)
    except TokenError as exc:
        raise _unauth() from exc
    if request.method not in SAFE_METHODS:
        _check_csrf(request)
    with c.db.system() as conn:
        user = repo.user_by_id(conn, claims.user_id)
        active = bool(user and user["is_active"]) and repo.family_active(
            conn, claims.family_id, claims.user_id)
    if not user or not active:
        raise _unauth()
    role = str(user["role"])  # the database role wins over the token claim
    tenant_id = str(user["tenant_id"]) if user["tenant_id"] else None
    platform_scope = False
    if role == "platform_admin":
        override = request.headers.get("x-tenant-id")
        if override:
            try:
                uuid.UUID(override)
            except ValueError as exc:
                raise ApiError(400, "X-Tenant-Id must be a UUID.", code="bad-tenant") from exc
            tenant_id = override
            audit.record(c.db, action="platform.tenant_context", actor=claims.user_id,
                         tenant_id=override, detail={"path": request.url.path})
        else:
            platform_scope = True
    return Principal("session", claims.user_id, tenant_id, role, P.permissions_for(role),
                     user["email"], claims.family_id, platform_scope=platform_scope)


def _from_api_key(key: str, c: Container) -> Principal:
    parts = split_api_key(key)
    if not parts:
        raise _unauth()
    prefix, secret = parts
    with c.db.system() as conn:
        row = repo.key_by_prefix(conn, prefix)
        valid = bool(row and hmac.compare_digest(row["secret_hash"], hash_token(secret)))
        if valid and row:
            from datetime import UTC, datetime

            expired = row["expires_at"] is not None and row["expires_at"] <= datetime.now(UTC)
            valid = row["revoked_at"] is None and not expired
            if valid:
                repo.touch_key(conn, str(row["id"]))
    if not valid or row is None:
        raise _unauth()
    scopes = frozenset(row["scopes"]) & P.KEY_SCOPES
    return Principal("api_key", None, str(row["tenant_id"]), "api_key", scopes,
                     key_id=str(row["id"]))


def _check_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise ApiError(403, "The CSRF token is missing or does not match.", code="csrf")


def new_csrf() -> str:
    return secrets.token_urlsafe(24)


def set_auth_cookies(response: Response, c: Container, access: str, refresh: str) -> str:
    s = c.settings
    common: dict[str, Any] = {"secure": s.cookie_secure, "samesite": "strict",
                              "domain": s.cookie_domain}
    response.set_cookie(ACCESS_COOKIE, access, httponly=True, path="/api",
                        max_age=s.access_minutes * 60, **common)
    response.set_cookie(REFRESH_COOKIE, refresh, httponly=True, path="/api/v1/auth",
                        max_age=s.session_absolute_days * 86400, **common)
    csrf = new_csrf()
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, path="/",
                        max_age=s.session_absolute_days * 86400, **common)
    return csrf


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/api")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


def require(permission: str) -> Callable[..., Principal]:
    """Dependency factory: the caller must hold `permission`."""

    def check(principal: Principal = Depends(get_principal)) -> Principal:
        if permission not in principal.permissions:
            raise ApiError(403, "You do not have permission to perform this action.",
                           code="forbidden")
        return principal

    return check


def session_only(principal: Principal = Depends(get_principal)) -> Principal:
    """Endpoints that API keys must never reach (account and administration)."""
    if principal.kind != "session":
        raise ApiError(403, "This endpoint requires an interactive session.", code="forbidden")
    return principal


def require_session(permission: str) -> Callable[..., Principal]:
    def check(principal: Principal = Depends(session_only)) -> Principal:
        if permission not in principal.permissions:
            raise ApiError(403, "You do not have permission to perform this action.",
                           code="forbidden")
        return principal

    return check


async def limit_principal(request: Request, principal: Principal = Depends(get_principal),
                          container: Container = Depends(get_container)) -> None:
    """Per-user and per-API-key rate limits (async so the limiter backend can be Valkey)."""
    if principal.kind == "api_key":
        key, limit = f"key:{principal.key_id}", container.settings.key_limit
    else:
        key, limit = f"user:{principal.user_id}", container.settings.user_limit
    allowed, retry = await container.limiter.hit(key, *limit)
    if not allowed:
        raise ApiError(429, "Rate limit exceeded.", code="rate-limited",
                       headers={"Retry-After": str(retry)})


def tenant_conn(principal: Principal = Depends(get_principal),
                container: Container = Depends(get_container),
                _limit: None = Depends(limit_principal)) -> Iterator[Any]:
    """Tenant-scoped connection: `app_user` role with row level security bound to the tenant."""
    with container.db.tenant(principal.tenant_id, platform=principal.platform_scope) as conn:
        yield conn


def require_tenant(principal: Principal = Depends(get_principal)) -> str:
    if not principal.tenant_id:
        raise ApiError(400, "A tenant context is required. Platform administrators send the "
                       "X-Tenant-Id header.", code="tenant-required")
    return principal.tenant_id


# The transaction ends before the response is sent, so a client never sees success for a write
# that has not committed (and background tasks started by the endpoint see the committed rows).
TENANT_DB: Any = Depends(tenant_conn, scope="function")
