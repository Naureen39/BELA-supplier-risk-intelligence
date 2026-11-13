from __future__ import annotations

from fastapi import APIRouter

from app.routers import (
    admin,
    alerts,
    auth,
    business,
    contact,
    corrections,
    health,
    knowledge,
    monitoring,
    platform,
    suppliers,
    uploads,
)

# `uploads` precedes `suppliers` so /uploads/template wins over /uploads/{upload_id}.
ROUTERS: list[APIRouter] = [
    health.router, auth.router, admin.router, uploads.router, suppliers.router, corrections.router,
    knowledge.router, alerts.router, business.router, monitoring.router, platform.router,
    contact.router,
]
