"""Role x endpoint-group matrix, cross-tenant isolation, and API key scoping."""

from __future__ import annotations

import io
from typing import Any

import pytest
from conftest import ROLES, Api, World, seed_catalog

# (method, path, kwargs, permission needed). A role passes when it holds the permission.
GROUPS: list[tuple[str, str, dict[str, Any], str]] = [
    ("GET", "/suppliers", {}, "view"),
    ("GET", "/events", {}, "view"),
    ("GET", "/alerts", {}, "view"),
    ("GET", "/rules", {}, "view"),
    ("GET", "/graph/neighbors?company_id=1", {}, "view"),
    ("GET", "/reviews", {}, "upload_review"),
    ("POST", "/resolve", {"json": {"name": "Acme Corp"}}, "upload_review"),
    ("POST", "/rules", {"json": {"name": "r"}}, "manage_rules"),
    ("GET", "/analytics/portfolio", {}, "manage_rules"),
    ("GET", "/sources", {}, "manage_rules"),
    ("POST", "/reports/portfolio", {}, "manage_rules"),
    ("GET", "/admin/users", {}, "manage_users"),
    ("GET", "/admin/api-keys", {}, "manage_users"),
    ("GET", "/billing/plan", {}, "manage_users"),
    ("GET", "/admin/audit", {}, "view_audit"),
    ("GET", "/platform/revenue/summary", {}, "view_revenue"),
    ("GET", "/platform/tenants", {}, "platform"),
    ("GET", "/platform/review-queue", {}, "platform"),
]


@pytest.mark.parametrize("role", ROLES)
def test_every_role_against_every_endpoint_group(world: World, role: str) -> None:
    from app.auth.permissions import permissions_for

    tenant = "platform" if role in ("finance_analyst", "platform_admin") else "a"
    api = Api(world).as_role(tenant, role)
    headers = {"X-Tenant-Id": world.tenant_a} if role == "platform_admin" else {}
    for method, path, kw, perm in GROUPS:
        r = api.request(method, path, headers=headers, **kw)
        if perm in permissions_for(role):
            assert r.status_code not in (401, 403), f"{role} {method} {path} -> {r.status_code} {r.text}"
        else:
            assert r.status_code == 403, f"{role} {method} {path} -> {r.status_code}"
            assert r.headers["content-type"].startswith("application/problem+json")


def test_unauthenticated_requests_are_rejected_everywhere(world: World) -> None:
    api = Api(world)
    for method, path, kw, _perm in GROUPS:
        assert api.request(method, path, **kw).status_code == 401, path
    assert api.get("/health").status_code == 200


def test_tenant_data_is_invisible_across_tenants(world: World) -> None:
    ids = seed_catalog(world)
    a_admin = Api(world).as_role("a", "analyst")
    b_admin = Api(world).as_role("b", "analyst")
    sup = a_admin.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"})
    assert sup.status_code == 201, sup.text
    sid = sup.json()["id"]
    assert b_admin.get(f"/suppliers/{sid}/risk").status_code == 404
    assert b_admin.get(f"/suppliers/{sid}/events").status_code == 404
    assert b_admin.patch(f"/suppliers/{sid}", json={"tier": "1"}).status_code == 404
    assert b_admin.get("/suppliers").json()["items"] == []
    assert [s["id"] for s in a_admin.get("/suppliers").json()["items"]] == [sid]
    _ = ids


def test_row_level_security_binds_even_unfiltered_sql(world: World) -> None:
    seed_catalog(world)
    a = Api(world).as_role("a", "analyst")
    a.post("/suppliers", json={"name": "Harborline Foods", "state": "OH"})
    db = world.container.db
    with db.tenant(world.tenant_b) as conn:  # deliberately no WHERE clause
        assert conn.execute("SELECT count(*) AS n FROM suppliers").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 4
        assert conn.execute("SELECT count(*) AS n FROM tenants").fetchone()["n"] == 1
    with db.tenant(world.tenant_a) as conn:
        assert conn.execute("SELECT count(*) AS n FROM suppliers").fetchone()["n"] == 1
    with db.tenant(None) as conn:  # no tenant context at all sees nothing
        assert conn.execute("SELECT count(*) AS n FROM suppliers").fetchone()["n"] == 0


def test_app_role_cannot_touch_secrets_or_global_writes(world: World) -> None:
    import psycopg

    with world.container.db.tenant(world.tenant_a) as conn:
        for sql in ("SELECT * FROM refresh_tokens", "SELECT * FROM user_mfa",
                    "SELECT * FROM password_reset_tokens", "UPDATE companies SET status = 'inactive'",
                    "DELETE FROM audit_log", "INSERT INTO events (source, source_id, event_type, "
                    "severity, reported_at, title) VALUES ('x','x','x',1,now(),'x')"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute(sql)


def test_cross_tenant_write_is_blocked_by_row_level_security(world: World) -> None:
    import psycopg

    with world.container.db.tenant(world.tenant_a) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.transaction():
                conn.execute("INSERT INTO suppliers (tenant_id, uploaded_name) VALUES (%s, 'x')",
                             (world.tenant_b,))


def test_platform_admin_needs_header_to_act_inside_a_tenant(world: World) -> None:
    api = Api(world).as_role("platform", "platform_admin")
    assert api.post("/suppliers", json={"name": "Acme"}).status_code == 400
    assert api.get("/suppliers").status_code == 200  # cross-tenant read scope
    assert api.get("/suppliers", headers={"X-Tenant-Id": "not-a-uuid"}).status_code == 400


def test_api_keys_scoped_hashed_shown_once_and_revocable(world: World) -> None:
    admin = Api(world).as_role("a", "tenant_admin")
    bad = admin.post("/admin/api-keys", json={"name": "k", "scopes": ["manage_users"]})
    assert bad.status_code == 422
    r = admin.post("/admin/api-keys", json={"name": "ci", "scopes": ["view"], "expires_in_days": 30})
    assert r.status_code == 201
    key, kid = r.json()["key"], r.json()["id"]
    assert key.startswith("pk_") and "key" not in str(admin.get("/admin/api-keys").json())
    with world.container.db.system() as conn:
        row = conn.execute("SELECT secret_hash FROM api_keys").fetchone()
    assert row["secret_hash"] != key and key.split("_", 2)[2] not in row["secret_hash"]

    client = Api(world)
    h = {"Authorization": f"Bearer {key}"}
    assert client.get("/suppliers", headers=h).status_code == 200
    assert client.post("/resolve", headers=h, json={"name": "x"}).status_code == 403  # scope missing
    assert client.get("/admin/users", headers=h).status_code == 403
    assert client.get("/auth/me", headers=h).status_code == 403  # keys never act as sessions
    assert client.get("/suppliers", headers={"Authorization": "Bearer pk_deadbeef_wrong"}).status_code == 401
    with world.container.db.system() as conn:
        assert conn.execute("SELECT last_used_at FROM api_keys").fetchone()["last_used_at"] is not None
    assert admin.delete(f"/admin/api-keys/{kid}").status_code == 204
    assert client.get("/suppliers", headers=h).status_code == 401


def test_api_key_of_another_tenant_sees_only_its_tenant(world: World) -> None:
    seed_catalog(world)
    Api(world).as_role("a", "analyst").post("/suppliers", json={"name": "Harborline Foods", "state": "OH"})
    b_admin = Api(world).as_role("b", "tenant_admin")
    key = b_admin.post("/admin/api-keys", json={"name": "b", "scopes": ["view"]}).json()["key"]
    r = Api(world).get("/suppliers", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200 and r.json()["items"] == []


def test_api_key_rate_limit_and_expiry(world: World) -> None:
    from app.container import Container
    from app.core.mailer import MemoryMailer
    from app.core.ratelimit import MemoryRateLimiter
    from conftest import test_settings

    admin = Api(world).as_role("a", "tenant_admin")
    key = admin.post("/admin/api-keys", json={"name": "k", "scopes": ["view"]}).json()["key"]
    s = test_settings(world.container.settings.database_url, key_limit=(2, 60))
    c = Container.build(s, world.container.db, MemoryMailer(), MemoryRateLimiter(), world.container.broker)
    w = World(c, MemoryMailer(), world.tenant_a, world.tenant_b, world.users)
    api = Api(w)
    h = {"Authorization": f"Bearer {key}"}
    assert [api.get("/suppliers", headers=h).status_code for _ in range(3)] == [200, 200, 429]
    with world.container.db.system() as conn:
        conn.execute("UPDATE api_keys SET expires_at = now() - interval '1 day'")
    assert Api(world).get("/suppliers", headers=h).status_code == 401


def test_security_headers_request_id_and_problem_format(world: World) -> None:
    api = Api(world)
    r = api.get("/suppliers", headers={"X-Request-Id": "req-12345678"})
    assert r.status_code == 401 and r.headers["x-request-id"] == "req-12345678"
    assert r.json()["request_id"] == "req-12345678" and r.headers["content-type"].startswith("application/problem+json")
    for h in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy",
              "permissions-policy", "strict-transport-security"):
        assert h in r.headers, h
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "access-control-allow-origin" not in r.headers  # same origin only
    bad = api.get("/suppliers", headers={"X-Request-Id": "bad id\x00"})
    assert bad.headers["x-request-id"] != "bad id"


def test_validation_errors_do_not_echo_input(world: World) -> None:
    r = Api(world).post("/auth/login", json={"email": "not-an-email", "password": "SecretValue-123"})
    assert r.status_code == 422 and "SecretValue" not in r.text and r.json()["errors"]


def test_body_size_limits(world: World) -> None:
    api = Api(world)
    r = api.http.post("/api/v1/contact/demo-request", content=b"x" * 2_000_000,
                      headers={"content-type": "application/json"})
    assert r.status_code == 413
    chunked = api.http.post("/api/v1/contact/demo-request", headers={"content-type": "application/json"},
                            content=iter([b"x" * 600_000, b"x" * 600_000]))
    assert chunked.status_code == 413


def test_per_ip_rate_limit_returns_429_with_retry_after(world: World) -> None:
    from app.container import Container
    from app.core.mailer import MemoryMailer
    from app.core.ratelimit import MemoryRateLimiter
    from conftest import test_settings

    s = test_settings(world.container.settings.database_url, ip_limit=(3, 60))
    c = Container.build(s, world.container.db, MemoryMailer(), MemoryRateLimiter(), world.container.broker)
    api = Api(World(c, MemoryMailer(), world.tenant_a, world.tenant_b, world.users))
    codes = [api.get("/health").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert "retry-after" in api.get("/health").headers


def test_demo_request_validation_and_storage(world: World) -> None:
    api = Api(world)
    good = {"name": "Alex", "work_email": "alex@example.org", "organization": "Example", "consent": True}
    assert api.post("/contact/demo-request", json=good).status_code == 201
    assert api.post("/contact/demo-request", json={**good, "consent": False}).status_code == 422
    assert api.post("/contact/demo-request", json={**good, "work_email": "bad"}).status_code == 422
    with world.container.db.system() as conn:
        assert conn.execute("SELECT count(*) AS n FROM demo_requests").fetchone()["n"] == 1


def test_openapi_is_served_with_examples(world: World) -> None:
    api = Api(world)
    spec = api.http.get("/api/openapi.json").json()
    assert "/api/v1/auth/login" in spec["paths"] and "/api/v1/uploads" in spec["paths"]
    assert "examples" in spec["components"]["schemas"]["LoginIn"]
    assert api.http.get("/api/docs").status_code == 200
    _ = io
