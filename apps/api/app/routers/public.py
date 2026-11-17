"""Public endpoints for the marketing site: newsletter double opt-in and site statistics."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field

from app.analytics.common import plain
from app.analytics.tenant import read_eval_metrics
from app.auth.deps import get_container
from app.auth.tokens import hash_token
from app.container import Container
from app.core.cache import cached
from app.core.errors import ApiError

router = APIRouter(tags=["public"])
NEWSLETTER_REPLY = {"detail": "If the address is valid, a confirmation email has been sent."}


class NewsletterIn(BaseModel):
    email: EmailStr


class ConfirmIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/newsletter", status_code=202, summary="Subscribe to the newsletter (double opt-in)")
async def newsletter(body: NewsletterIn, request: Request,
                     c: Container = Depends(get_container)) -> dict[str, str]:
    allowed, retry = await c.limiter.hit(f"newsletter-ip:{request.state.client_ip}", 5, 3600)
    if not allowed:
        raise ApiError(429, "Too many requests.", code="rate-limited", headers={"Retry-After": str(retry)})
    token = secrets.token_urlsafe(32)
    with c.db.system() as conn:
        row = conn.execute(
            "INSERT INTO newsletter_subscribers (email, token_hash) VALUES (%s,%s) "
            "ON CONFLICT (lower(email)) DO UPDATE SET token_hash = EXCLUDED.token_hash "
            "WHERE newsletter_subscribers.confirmed_at IS NULL RETURNING id",
            (body.email, hash_token(token))).fetchone()
    if row:  # already confirmed addresses get the same reply and no email
        link = f"{c.settings.web_base_url}/newsletter/confirm?token={token}"
        c.mailer.send(body.email, "Confirm your subscription",
                      f"Confirm your subscription to the newsletter:\n\n{link}\n\n"
                      "If you did not request this, ignore this message.")
    return NEWSLETTER_REPLY


@router.post("/newsletter/confirm", summary="Confirm a newsletter subscription")
def newsletter_confirm(body: ConfirmIn, c: Container = Depends(get_container)) -> dict[str, str]:
    with c.db.system() as conn:
        row = conn.execute(
            "UPDATE newsletter_subscribers SET confirmed_at = coalesce(confirmed_at, now()) "
            "WHERE token_hash = %s RETURNING id", (hash_token(body.token),)).fetchone()
    if not row:
        raise ApiError(404, "The confirmation link is not valid.", code="not-found")
    return {"detail": "Your subscription is confirmed."}


@router.get("/public/stats", summary="Counts and evaluation figures shown on the marketing site")
def site_stats(c: Container = Depends(get_container)) -> Any:
    def compute() -> dict[str, Any]:
        with c.db.system() as conn:
            companies = conn.execute("SELECT count(*) AS n FROM companies").fetchone()["n"]
            sources = conn.execute(
                "SELECT e.source, count(DISTINCT e.id) AS records, "
                "count(DISTINCT e.id) FILTER (WHERE ee.route = 'accepted') AS linked, "
                "max(e.reported_at) AS latest FROM events e "
                "LEFT JOIN event_entities ee ON ee.event_id = e.id GROUP BY e.source ORDER BY e.source"
            ).fetchall()
            facilities = conn.execute("SELECT count(*) AS n FROM facilities").fetchone()["n"]
        return plain({"companies": companies, "facilities": facilities,
                      "sources": [dict(r) for r in sources],
                      "evaluation": read_eval_metrics(c.settings.eval_metrics_path)})

    body, _ = cached(c.cache, "public:stats", 3600, compute)
    return body
