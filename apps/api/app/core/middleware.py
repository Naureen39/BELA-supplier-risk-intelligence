"""ASGI middleware: request IDs, security headers, body size limits, per-IP rate limit."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.ratelimit import RateLimiter

_REQ_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_DOCS_CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
             "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: "
             "https://fastapi.tiangolo.com; frame-ancestors 'none'; base-uri 'none'")


def client_ip(scope: Scope, trust_proxy: bool) -> str:
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    if trust_proxy and "x-forwarded-for" in headers:
        return str(headers["x-forwarded-for"].split(",")[0].strip())
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _json(send: Send, status: int, body: dict[str, Any], headers: list[tuple[bytes, bytes]]
                ) -> None:
    payload = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/problem+json"),
        (b"content-length", str(len(payload)).encode()), *headers]})
    await send({"type": "http.response.body", "body": payload})


class RequestContextMiddleware:
    """Request id, security headers, size limits, and per-IP rate limiting."""

    def __init__(self, app: ASGIApp, *, limiter: RateLimiter, ip_limit: tuple[int, int],
                 max_body: int, max_upload: int, upload_paths: tuple[str, ...], hsts: bool,
                 trust_proxy: bool) -> None:
        self.app, self.limiter, self.ip_limit = app, limiter, ip_limit
        self.max_body, self.max_upload, self.upload_paths = max_body, max_upload, upload_paths
        self.hsts, self.trust_proxy = hsts, trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        rid = headers.get("x-request-id", "")
        rid = rid if _REQ_ID.match(rid) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        path: str = scope["path"]
        sec = self._security_headers(path, rid)

        ip = client_ip(scope, self.trust_proxy)
        scope["state"]["client_ip"] = ip
        allowed, retry = await self.limiter.hit(f"ip:{ip}", *self.ip_limit)
        if not allowed:
            await _json(send, 429, self._problem(429, "Rate limit exceeded.", path, rid),
                        [*sec, (b"retry-after", str(retry).encode())])
            return

        limit = self.max_upload if path.endswith(self.upload_paths) else self.max_body
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await _json(send, 413, self._problem(413, "Request body too large.", path, rid), sec)
            return

        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    too_large = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                if too_large:
                    return
                existing = list(message.get("headers", []))
                present = {k.lower() for k, _ in existing}
                message["headers"] = existing + [(k, v) for k, v in sec if k not in present]
            elif too_large and message["type"] == "http.response.body":
                return
            await send(message)

        await self.app(scope, limited_receive, wrapped_send)
        if too_large:
            await _json(send, 413, self._problem(413, "Request body too large.", path, rid), sec)

    @staticmethod
    def _problem(status: int, detail: str, path: str, rid: str) -> dict[str, Any]:
        return {"type": f"https://provenance.example/problems/{status}",
                "title": "Too many requests" if status == 429 else "Payload too large",
                "status": status, "detail": detail, "instance": path, "request_id": rid}

    def _security_headers(self, path: str, rid: str) -> list[tuple[bytes, bytes]]:
        docs = path.startswith("/api/docs") or path.startswith("/api/redoc")
        out = [
            (b"x-request-id", rid.encode()),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
            (b"content-security-policy", (_DOCS_CSP if docs else _API_CSP).encode()),
            (b"cross-origin-resource-policy", b"same-origin"),
        ]
        if not docs:
            out.append((b"cache-control", b"no-store"))
        if self.hsts:
            out.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains"))
        return out


Handler = Callable[[Scope, Receive, Send], Awaitable[None]]
