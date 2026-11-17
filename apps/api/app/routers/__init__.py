from __future__ import annotations

from fastapi import APIRouter

from app.routers import (
    admin,
    alerts,
    analytics,
    auth,
    business,
    contact,
    corrections,
    health,
    knowledge,
    monitoring,
    platform,
    revenue,
    suppliers,
    uploads,
)

# `uploads` precedes `suppliers` so /uploads/template wins over /uploads/{upload_id}.
ROUTERS: list[APIRouter] = [
    health.router, auth.router, admin.router, uploads.router, analytics.router, suppliers.router, corrections.router,
    knowledge.router, alerts.router, business.router, monitoring.router, platform.router, revenue.router,
    contact.router,
]
