"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.container import Container
from app.core.errors import install_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.routers import ROUTERS
from app.settings import Settings

API_PREFIX = "/api/v1"
UPLOAD_PATHS = ("/uploads",)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging()
    c = container or Container.build(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> Any:
        yield
        await c.broker.close()
        c.db.close()

    app = FastAPI(
        title="Provenance Risk API", version="1.0.0", lifespan=lifespan,
        docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
        description="Supplier and counterparty risk intelligence. Results are leads for human "
                    "review and not statements of fault.")
    app.state.container = c
    app.add_middleware(
        RequestContextMiddleware, limiter=c.limiter, ip_limit=c.settings.ip_limit,
        max_body=c.settings.max_body_bytes, max_upload=c.settings.max_upload_bytes,
        upload_paths=UPLOAD_PATHS, hsts=c.settings.cookie_secure,
        trust_proxy=c.settings.trust_proxy_headers)
    install_handlers(app)
    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    return app
