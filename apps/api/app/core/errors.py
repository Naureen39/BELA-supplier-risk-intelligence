"""RFC 7807 problem responses."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM = "application/problem+json"
_TITLES = {400: "Bad request", 401: "Authentication required", 403: "Forbidden", 404: "Not found",
           405: "Method not allowed", 409: "Conflict", 413: "Payload too large",
           415: "Unsupported media type", 422: "Validation failed", 429: "Too many requests"}


class ApiError(Exception):
    def __init__(self, status: int, detail: str, *, code: str | None = None,
                 headers: dict[str, str] | None = None, extra: dict[str, Any] | None = None) -> None:
        self.status, self.detail, self.code = status, detail, code
        self.headers, self.extra = headers or {}, extra or {}


def problem(request: Request, status: int, detail: str, *, code: str | None = None,
            headers: dict[str, str] | None = None, extra: dict[str, Any] | None = None
            ) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://provenance.example/problems/{code or status}",
        "title": _TITLES.get(status, "Error"), "status": status, "detail": detail,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", None), **(extra or {})}
    return JSONResponse(body, status_code=status, media_type=PROBLEM, headers=headers)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError) -> JSONResponse:
        return problem(request, exc.status, exc.detail, code=exc.code, headers=exc.headers,
                       extra=exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(request, exc.status_code, str(exc.detail), headers=dict(exc.headers or {}))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo submitted values: they can contain passwords or identifiers.
        errors = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"],
                   "type": e["type"]} for e in exc.errors()]
        return problem(request, 422, "The request did not pass validation.", code="validation",
                       extra={"errors": errors})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        import structlog

        structlog.get_logger().error("unhandled_error", error_type=type(exc).__name__,
                                     request_id=getattr(request.state, "request_id", None))
        return problem(request, 500, "An internal error occurred.", code="internal")
