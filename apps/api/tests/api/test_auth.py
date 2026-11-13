from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pyotp
from conftest import PASSWORD, Api, World


def test_login_sets_secure_cookies_and_me(world: World) -> None:
    api = Api(world)
    r = api.login("a", "analyst")
    assert r.status_code == 200 and r.json()["status"] == "authenticated"
    raw = " ".join(r.headers.get_list("set-cookie")).lower()
    for name in ("pr_access", "pr_refresh"):
        part = [c for c in r.headers.get_list("set-cookie") if c.startswith(name)][0].lower()
        assert "httponly" in part and "secure" in part and "samesite=strict" in part
    assert "pr_csrf" in raw and "httponly" not in [c for c in r.headers.get_list("set-cookie")
                                                   if c.startswith("pr_csrf")][0].lower()
    me = api.get("/auth/me").json()
    assert me["role"] == "analyst" and "upload_review" in me["permissions"]
    assert "password" not in str(me).lower()


def test_generic_errors_do_not_reveal_accounts(world: World) -> None:
    api = Api(world)
    wrong = api.post("/auth/login", json={"email": "analyst@a.example", "password": "nope-nope-nope"})
    missing = api.post("/auth/login", json={"email": "ghost@a.example", "password": "nope-nope-nope"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]
    assert wrong.headers["content-type"].startswith("application/problem+json")


def test_lockout_after_repeated_failures_is_generic_and_blocks_correct_password(world: World) -> None:
    api = Api(world)
    email = world.email("a", "viewer")
    for _ in range(5):
        assert api.post("/auth/login", json={"email": email, "password": "bad-bad-bad-bad"}).status_code == 401
    locked = api.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert locked.status_code == 401 and locked.json()["detail"] == "Invalid credentials."
    with world.container.db.system() as conn:
        row = conn.execute("SELECT locked_until, failed_logins FROM users WHERE email = %s", (email,)).fetchone()
        assert row["locked_until"] > datetime.now(UTC) and row["failed_logins"] == 5
        conn.execute("UPDATE users SET locked_until = now() - interval '1 second' WHERE email = %s", (email,))
    assert api.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200


def test_failed_logins_are_audited_without_secrets(world: World) -> None:
    Api(world).post("/auth/login", json={"email": "viewer@a.example", "password": "SuperSecret-Wrong-1"})
    with world.container.db.system() as conn:
        rows = conn.execute("SELECT action, detail FROM audit_log").fetchall()
    assert any(r["action"] == "auth.login_failed" for r in rows)
    assert "SuperSecret" not in str(rows)


def test_login_rate_limit(world: World) -> None:
    from app.container import Container
    from app.core.mailer import MemoryMailer
    from app.core.ratelimit import MemoryRateLimiter
    from conftest import test_settings

    s = test_settings(world.container.settings.database_url, login_ip_limit=(3, 60))
    c = Container.build(s, world.container.db, MemoryMailer(), MemoryRateLimiter(), world.container.broker)
    w = World(c, MemoryMailer(), world.tenant_a, world.tenant_b, world.users)
    api = Api(w)
    codes = [api.post("/auth/login", json={"email": "x@a.example", "password": "bad-bad-bad-bad"}).status_code
             for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_admin_requires_mfa_enrollment_then_login_with_totp(world: World) -> None:
    api = Api(world)
    r = api.post("/auth/login", json={"email": world.email("a", "tenant_admin"), "password": PASSWORD})
    assert r.json()["status"] == "mfa_enrollment_required" and "pr_access" not in api.http.cookies
    token = r.json()["mfa_token"]
    setup = api.post("/auth/mfa/setup", json={"mfa_token": token}).json()
    assert len(setup["recovery_codes"]) == 10 and setup["otpauth_uri"].startswith("otpauth://totp/")
    bad = api.post("/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})
    assert bad.status_code == 401
    ok = api.post("/auth/mfa/verify", json={"mfa_token": token, "code": pyotp.TOTP(setup["secret"]).now()})
    assert ok.status_code == 200 and ok.json()["status"] == "authenticated"
    # Recovery codes are stored hashed, never in clear.
    with world.container.db.system() as conn:
        hashes = conn.execute("SELECT recovery_code_hashes FROM user_mfa").fetchone()["recovery_code_hashes"]
    assert len(hashes) == 10 and not set(hashes) & set(setup["recovery_codes"])
    # The same one-time code cannot be replayed on a later login.
    again = Api(world)
    r2 = again.post("/auth/login", json={"email": world.email("a", "tenant_admin"), "password": PASSWORD})
    replay = again.post("/auth/mfa/verify", json={"mfa_token": r2.json()["mfa_token"],
                                                  "code": pyotp.TOTP(setup["secret"]).now()})
    assert replay.status_code == 401


def test_recovery_code_is_single_use(world: World) -> None:
    api = Api(world)
    token = api.post("/auth/login", json={"email": world.email("a", "tenant_admin"), "password": PASSWORD}).json()["mfa_token"]
    setup = api.post("/auth/mfa/setup", json={"mfa_token": token}).json()
    api.post("/auth/mfa/verify", json={"mfa_token": token, "code": pyotp.TOTP(setup["secret"]).now()})
    code = setup["recovery_codes"][0]
    for expected in (200, 401):
        a = Api(world)
        t = a.post("/auth/login", json={"email": world.email("a", "tenant_admin"), "password": PASSWORD}).json()["mfa_token"]
        assert a.post("/auth/mfa/verify", json={"mfa_token": t, "recovery_code": code}).status_code == expected


def test_csrf_required_on_state_changes(world: World) -> None:
    api = Api(world).as_role("a", "manager")
    r = api.http.post("/api/v1/rules", json={"name": "x"})  # no X-CSRF-Token header
    assert r.status_code == 403 and r.json()["type"].endswith("/csrf")


def test_refresh_rotates_and_reuse_revokes_family(world: World) -> None:
    api = Api(world)
    api.login("a", "analyst")
    old = api.http.cookies.get("pr_refresh")
    r1 = api.post("/auth/refresh")
    assert r1.status_code == 200 and api.http.cookies.get("pr_refresh") != old
    # An attacker replays the old refresh token.
    thief = Api(world)
    thief.http.cookies.set("pr_refresh", old, path="/api/v1/auth")
    thief.http.cookies.set("pr_csrf", "x" * 20, path="/")
    reuse = thief.post("/auth/refresh")
    assert reuse.status_code == 401
    # The whole family is revoked, so the legitimate holder is signed out too.
    assert api.post("/auth/refresh").status_code == 401
    assert api.get("/auth/me").status_code == 401
    with world.container.db.system() as conn:
        assert conn.execute("SELECT count(*) AS n FROM audit_log WHERE action = 'auth.refresh_reuse_detected'").fetchone()["n"] == 1


def test_logout_revokes_session_immediately(world: World) -> None:
    api = Api(world).as_role("a", "viewer")
    token = api.http.cookies.get("pr_access")
    assert api.post("/auth/logout").status_code == 204
    stolen = Api(world)
    stolen.http.cookies.set("pr_access", token, path="/api")
    assert stolen.get("/auth/me").status_code == 401


def test_absolute_session_lifetime(world: World) -> None:
    api = Api(world)
    api.login("a", "viewer")
    with world.container.db.system() as conn:
        conn.execute("UPDATE refresh_tokens SET created_at = now() - interval '31 days'")
    assert api.post("/auth/refresh").status_code == 401


def test_password_reset_flow_single_use_and_no_enumeration(world: World) -> None:
    api = Api(world)
    ghost = api.post("/auth/password/forgot", json={"email": "ghost@a.example"})
    real = api.post("/auth/password/forgot", json={"email": world.email("a", "viewer")})
    assert ghost.status_code == real.status_code == 202 and ghost.json() == real.json()
    assert len(world.mailer.outbox) == 1
    token = re.search(r"token=([\w-]+)", world.mailer.outbox[0][2]).group(1)  # type: ignore[union-attr]
    weak = api.post("/auth/password/reset", json={"token": token, "password": "password1234"})
    assert weak.status_code == 422
    new = "Amber-Lantern-Orbit-9137"
    assert api.post("/auth/password/reset", json={"token": token, "password": new}).status_code == 200
    assert api.post("/auth/password/reset", json={"token": token, "password": new + "x"}).status_code == 400
    assert Api(world).login("a", "viewer", new).status_code == 200
    assert Api(world).login("a", "viewer", PASSWORD).status_code == 401
    with world.container.db.system() as conn:
        stored = conn.execute("SELECT token_hash FROM password_reset_tokens").fetchone()["token_hash"]
    assert stored != token


def test_reset_revokes_existing_sessions(world: World) -> None:
    api = Api(world).as_role("a", "viewer")
    Api(world).post("/auth/password/forgot", json={"email": world.email("a", "viewer")})
    token = re.search(r"token=([\w-]+)", world.mailer.outbox[0][2]).group(1)  # type: ignore[union-attr]
    Api(world).post("/auth/password/reset", json={"token": token, "password": "Amber-Lantern-Orbit-9137"})
    assert api.get("/auth/me").status_code == 401


def test_password_policy() -> None:
    from app.auth.passwords import PasswordService
    from conftest import test_settings

    p = PasswordService(test_settings("x"))
    assert p.problems("short")  # too short
    assert p.problems("password1234") and p.problems("aaaaaaaaaaaaaaa")
    assert p.problems("Amber-Lantern-Orbit-9137") == []
    h = p.hash("Amber-Lantern-Orbit-9137")
    assert h.startswith("$argon2id$") and p.verify(h, "Amber-Lantern-Orbit-9137") and not p.verify(h, "x")
    assert p.verify(None, "anything") is False


def test_sessions_listing_and_expired_access_token(world: World) -> None:
    api = Api(world).as_role("a", "viewer")
    items = api.get("/auth/sessions").json()["items"]
    assert len(items) == 1 and items[0]["current"] is True
    soon = world.container.tokens
    expired = soon._encode({"sub": world.users[("a", "viewer")], "tid": world.tenant_a,
                            "role": "viewer", "fam": "x"}, -1, "access")
    other = Api(world)
    other.http.cookies.set("pr_access", expired, path="/api")
    assert other.get("/auth/me").status_code == 401
    _ = timedelta
