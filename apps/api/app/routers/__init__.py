from __future__ import annotations

from fastapi import APIRouter

from app.routers import (
    admin,
    alerts,
    auth,
    business,
    contact,
    health,
    knowledge,
    platform,
    suppliers,
)

ROUTERS: list[APIRouter] = [
    health.router, auth.router, admin.router, suppliers.router, knowledge.router, alerts.router,
    business.router, platform.router, contact.router,
]
