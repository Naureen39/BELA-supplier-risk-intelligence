"""Public demo request form."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field

from app.auth.deps import get_container
from app.container import Container
from app.core.errors import ApiError

router = APIRouter(tags=["contact"])


class DemoRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    work_email: EmailStr
    organization: str = Field(min_length=1, max_length=160)
    role: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=2000)
    consent: bool

    model_config = {"json_schema_extra": {"examples": [{
        "name": "Alex Morgan", "work_email": "alex@example.org", "organization": "Example Supply Co",
        "role": "Procurement lead", "industry": "Manufacturing",
        "message": "We would like to see the review workflow.", "consent": True}]}}


@router.post("/contact/demo-request", status_code=201, summary="Request a demonstration")
async def demo_request(body: DemoRequest, request: Request,
                       c: Container = Depends(get_container)) -> dict[str, str]:
    if not body.consent:
        raise ApiError(422, "Consent is required to submit the form.", code="validation")
    allowed, retry = await c.limiter.hit(f"demo-ip:{request.state.client_ip}", 5, 3600)
    if not allowed:
        raise ApiError(429, "Too many requests.", code="rate-limited",
                       headers={"Retry-After": str(retry)})
    _store(c, body)
    return {"detail": "Thank you. We will contact you by email."}


def _store(c: Container, body: DemoRequest) -> None:
    data: dict[str, Any] = body.model_dump()
    with c.db.system() as conn:
        conn.execute(
            "INSERT INTO demo_requests (name, work_email, organization, role, industry, message, "
            "consent) VALUES (%(name)s,%(work_email)s,%(organization)s,%(role)s,%(industry)s,"
            "%(message)s,%(consent)s)", data)
