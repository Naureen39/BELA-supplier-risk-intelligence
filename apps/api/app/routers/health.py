from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.deps import get_container
from app.container import Container

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness: database reachable")
def ready(c: Container = Depends(get_container)) -> dict[str, str]:
    from app.core.errors import ApiError

    if not c.db.ping():
        raise ApiError(503, "The database is not reachable.", code="not-ready")
    return {"status": "ready"}
