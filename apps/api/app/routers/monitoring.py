"""On-demand monitoring: rescore the tenant's suppliers and raise alerts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.routers.common import audit_event
from app.services.monitoring import recompute_tenant

router = APIRouter(tags=["monitoring"])
manager = deps.require(P.MANAGE_RULES)


@router.post("/monitoring/recompute", summary="Rescore this tenant's suppliers now")
async def recompute(p: Principal = Depends(manager),
                    t: str = Depends(deps.require_tenant), _l: None = Depends(deps.limit_principal),
                    c: Container = Depends(deps.get_container)) -> dict[str, Any]:
    result = await recompute_tenant(c, t)
    audit_event(c, p, "monitoring.recomputed", detail=result)
    return result
