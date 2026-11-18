"""Load test: 50 concurrent users reading supplier views and dashboards.

    locust -f infra/perf/locustfile.py --headless -u 50 -r 10 -t 120s --host http://127.0.0.1:8000 \
        --csv var/perf/read --only-summary

Environment: API_KEY (a key with the view, upload_review, and manage_rules scopes). The mix follows a reviewer's
day: mostly the supplier list and profiles, some events and alerts, and the analytics dashboards. The API must
run with generous rate limits (RATE_LIMIT_KEY=1000000/60) or the test measures the limiter.
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, events, task

KEY = os.environ.get("API_KEY", "")
THINK_MIN = float(os.environ.get("THINK_MIN", "0.5"))  # seconds between a user's requests; 0 and 0 is a stress test
THINK_MAX = float(os.environ.get("THINK_MAX", "2"))
SUPPLIER_IDS: list[str] = []
COMPANY_IDS: list[int] = []


@events.test_start.add_listener
def load_ids(environment, **_kw):  # type: ignore[no-untyped-def]
    import httpx

    with httpx.Client(base_url=environment.host, headers={"Authorization": f"Bearer {KEY}"}, timeout=30) as c:
        cursor = None
        while len(SUPPLIER_IDS) < 400:
            r = c.get("/api/v1/suppliers", params={"limit": 200, **({"cursor": cursor} if cursor else {})}).json()
            SUPPLIER_IDS.extend(s["id"] for s in r["items"] if s["resolved_company_id"])
            COMPANY_IDS.extend(s["resolved_company_id"] for s in r["items"] if s["resolved_company_id"])
            cursor = r["next_cursor"]
            if not cursor:
                break


class Reviewer(HttpUser):
    wait_time = between(THINK_MIN, THINK_MAX)

    def on_start(self) -> None:
        self.client.headers["Authorization"] = f"Bearer {KEY}"

    def _get(self, path: str, name: str | None = None, **kw) -> None:  # type: ignore[no-untyped-def]
        with self.client.get(path, name=name or path, catch_response=True, **kw) as r:
            if r.status_code >= 400:
                r.failure(f"{r.status_code}")

    @task(6)
    def supplier_list(self) -> None:
        self._get("/api/v1/suppliers?limit=50", "/suppliers?limit=50")

    @task(5)
    def supplier_profile(self) -> None:
        self._get(f"/api/v1/suppliers/{random.choice(SUPPLIER_IDS)}/profile", "/suppliers/{id}/profile")

    @task(3)
    def supplier_risk(self) -> None:
        self._get(f"/api/v1/suppliers/{random.choice(SUPPLIER_IDS)}/risk", "/suppliers/{id}/risk")

    @task(3)
    def events(self) -> None:
        self._get("/api/v1/events?limit=50", "/events?limit=50")

    @task(2)
    def alerts(self) -> None:
        self._get("/api/v1/alerts?limit=50", "/alerts?limit=50")

    @task(2)
    def portfolio_dashboard(self) -> None:
        self._get("/api/v1/analytics/portfolio?granularity=week", "/analytics/portfolio")

    @task(1)
    def quality_dashboard(self) -> None:
        self._get("/api/v1/analytics/quality?granularity=week", "/analytics/quality")

    @task(1)
    def graph(self) -> None:
        self._get(f"/api/v1/graph/neighbors?company_id={random.choice(COMPANY_IDS)}&depth=2", "/graph/neighbors")

    @task(1)
    def company_search(self) -> None:
        self._get("/api/v1/companies/search?q=" + random.choice(["harbor", "summit", "cobalt", "pioneer", "granite"]), "/companies/search")
