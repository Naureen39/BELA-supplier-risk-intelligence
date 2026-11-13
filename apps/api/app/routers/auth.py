"""Authentication endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from starlette.concurrency import run_in_threadpool

from app.auth import deps
from app.auth.deps import Principal
from app.auth.service import SessionTokens
from app.container import Container
from app.core.errors import ApiError
from app.repo import auth as repo

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

    model_config = {"json_schema_extra": {"examples": [
        {"email": "analyst@example.org", "password": "correct horse battery staple"}]}}


class MfaVerifyIn(BaseModel):
    mfa_token: str | None = Field(default=None, max_length=2000)
    code: str | None = Field(default=None, max_length=12)
    recovery_code: str | None = Field(default=None, max_length=40)


class MfaSetupIn(BaseModel):
    mfa_token: str | None = Field(default=None, max_length=2000)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=256)


async def _limit(c: Container, key: str, limit: tuple[int, int]) -> None:
    allowed, retry = await c.limiter.hit(key, *limit)
    if not allowed:
        raise ApiError(429, "Too many attempts. Try again later.", code="rate-limited",
                       headers={"Retry-After": str(retry)})


def _user_view(user: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(user["id"]), "email": user["email"], "role": user["role"],
            "tenant_id": str(user["tenant_id"]) if user["tenant_id"] else None}


def _session_response(c: Container, response: Response, tokens: SessionTokens) -> dict[str, Any]:
    csrf = deps.set_auth_cookies(response, c, tokens.access, tokens.refresh)
    return {"status": "authenticated", "user": _user_view(tokens.user), "csrf_token": csrf}


@router.post("/login", summary="Sign in with email and password")
async def login(body: LoginIn, request: Request, response: Response,
                c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    ip = request.state.client_ip
    await _limit(c, f"login-ip:{ip}", c.settings.login_ip_limit)
    await _limit(c, f"login-acct:{body.email.lower()}", c.settings.login_account_limit)
    outcome = await run_in_threadpool(c.auth.login, body.email, body.password, ip,
                                      request.headers.get("user-agent"))
    if outcome.tokens:
        return _session_response(c, response, outcome.tokens)
    return {"status": outcome.status, "mfa_token": outcome.mfa_token}


@router.post("/mfa/setup", summary="Begin multi-factor enrollment")
async def mfa_setup(body: MfaSetupIn, request: Request,
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    if body.mfa_token:
        claims = c.auth.read_mfa_token(body.mfa_token)
        if not claims.enroll:
            raise ApiError(403, "Enrollment is not available for this sign-in.", code="forbidden")
        user_id = claims.user_id
    else:
        principal = await run_in_threadpool(deps.get_principal, request, c)
        if principal.kind != "session" or not principal.user_id:
            raise ApiError(403, "This endpoint requires an interactive session.", code="forbidden")
        user_id = principal.user_id
    await _limit(c, f"mfa-setup:{user_id}", (10, 3600))
    return await run_in_threadpool(c.auth.setup_mfa, user_id)


@router.post("/mfa/verify", summary="Verify a one-time or recovery code")
async def mfa_verify(body: MfaVerifyIn, request: Request, response: Response,
                     c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    if not (body.code or body.recovery_code):
        raise ApiError(422, "Provide a code or a recovery code.", code="validation")
    ua = request.headers.get("user-agent")
    if body.mfa_token:
        claims = c.auth.read_mfa_token(body.mfa_token)
        await _limit(c, f"mfa:{claims.user_id}", (5, 300))
        tokens = await run_in_threadpool(c.auth.verify_mfa, claims.user_id, body.code,
                                         body.recovery_code, ua, True)
        assert tokens is not None
        return _session_response(c, response, tokens)
    principal = await run_in_threadpool(deps.get_principal, request, c)
    if principal.kind != "session" or not principal.user_id:
        raise ApiError(403, "This endpoint requires an interactive session.", code="forbidden")
    await _limit(c, f"mfa:{principal.user_id}", (5, 300))
    await run_in_threadpool(c.auth.verify_mfa, principal.user_id, body.code, None, ua, False)
    return {"status": "mfa_enabled"}


@router.post("/refresh", summary="Rotate the refresh token and issue a new access token")
async def refresh(request: Request, response: Response,
                  c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    deps._check_csrf(request)
    raw = request.cookies.get(deps.REFRESH_COOKIE)
    if not raw:
        raise ApiError(401, "The session is no longer valid.", code="session-invalid")
    await _limit(c, f"refresh-ip:{request.state.client_ip}", (60, 60))
    try:
        tokens = await run_in_threadpool(c.auth.refresh, raw, request.headers.get("user-agent"))
    except ApiError:
        deps.clear_auth_cookies(response)
        raise
    return _session_response(c, response, tokens)


@router.post("/logout", status_code=204, summary="End the current session")
async def logout(response: Response, principal: Principal = Depends(deps.session_only),
                 c: Container = Depends(deps.get_container)) -> Response:
    assert principal.family_id and principal.user_id
    await run_in_threadpool(c.auth.logout, principal.family_id, principal.user_id,
                            principal.tenant_id)
    out = Response(status_code=204)
    deps.clear_auth_cookies(out)
    return out


@router.post("/password/forgot", status_code=202, summary="Request a password reset email")
async def forgot(body: ForgotIn, request: Request,
                 c: Container = Depends(deps.get_container)) -> dict[str, str]:
    await _limit(c, f"forgot-ip:{request.state.client_ip}", (10, 3600))
    await _limit(c, f"forgot-acct:{body.email.lower()}", (3, 3600))
    await run_in_threadpool(c.auth.forgot_password, body.email)
    return {"detail": "If the account exists, a reset email has been sent."}


@router.post("/password/reset", summary="Set a new password with a reset token")
async def reset(body: ResetIn, request: Request,
                c: Container = Depends(deps.get_container)) -> dict[str, str]:
    await _limit(c, f"reset-ip:{request.state.client_ip}", (20, 3600))
    await run_in_threadpool(c.auth.reset_password, body.token, body.password)
    return {"detail": "The password has been changed. Sign in again."}


@router.get("/me", summary="Current user")
def me(principal: Principal = Depends(deps.session_only),
       c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    with c.db.system() as conn:
        mfa_row = repo.get_mfa(conn, principal.user_id or "")
    return {"id": principal.user_id, "email": principal.email, "role": principal.role,
            "tenant_id": principal.tenant_id, "permissions": sorted(principal.permissions),
            "mfa_enabled": bool(mfa_row and mfa_row["confirmed_at"])}


@router.get("/sessions", summary="Active sessions of the current user")
def sessions(principal: Principal = Depends(deps.session_only),
             c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    with c.db.system() as conn:
        rows = repo.list_sessions(conn, principal.user_id or "")
    return {"items": [{"id": str(r["family_id"]), "started_at": r["started_at"],
                       "last_seen_at": r["last_seen_at"], "user_agent": r["user_agent"],
                       "current": str(r["family_id"]) == principal.family_id} for r in rows]}
