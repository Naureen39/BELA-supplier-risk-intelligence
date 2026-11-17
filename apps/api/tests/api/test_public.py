"""Public endpoints used by the marketing site."""

from __future__ import annotations

import re

from conftest import Api, World, seed_catalog, seed_event


def test_newsletter_double_opt_in(world: World) -> None:
    api = Api(world)
    r = api.post("/newsletter", json={"email": "reader@example.org"})
    assert r.status_code == 202 and "confirmation" in r.json()["detail"]
    to, subject, body = world.mailer.outbox[-1]
    assert to == "reader@example.org" and "Confirm" in subject
    token = re.search(r"token=([\w-]+)", body).group(1)  # type: ignore[union-attr]
    with world.container.db.system() as conn:
        assert conn.execute("SELECT confirmed_at FROM newsletter_subscribers").fetchone()["confirmed_at"] is None
    assert api.post("/newsletter/confirm", json={"token": "x" * 40}).status_code == 404
    assert api.post("/newsletter/confirm", json={"token": token}).status_code == 200
    with world.container.db.system() as conn:
        assert conn.execute("SELECT confirmed_at FROM newsletter_subscribers").fetchone()["confirmed_at"] is not None
    sent = len(world.mailer.outbox)
    again = api.post("/newsletter", json={"email": "READER@example.org"})  # confirmed: same reply, no mail
    assert again.status_code == 202 and len(world.mailer.outbox) == sent
    assert api.post("/newsletter", json={"email": "not-an-email"}).status_code == 422


def test_site_stats_are_counts_only(world: World) -> None:
    ids = seed_catalog(world)
    seed_event(world, ids["Harborline Foods, Inc.|OH"])
    body = Api(world).get("/public/stats").json()
    assert body["companies"] == 5 and body["facilities"] == 0
    assert body["sources"][0]["source"] == "osha" and body["sources"][0]["linked"] == 1
    assert body["evaluation"] is None or "systems" in body["evaluation"]
