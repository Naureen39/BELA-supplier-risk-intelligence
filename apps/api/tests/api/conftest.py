"""API test fixtures: a migrated template database cloned per test, seeded tenants and users."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
import pyotp
import pytest
from alembic import command
from alembic.config import Config
from app.container import Container
from app.core.mailer import MemoryMailer
from app.core.ratelimit import MemoryRateLimiter
from app.db import Database
from app.events_bus import MemoryBroker
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parents[2]
PASSWORD = "Violet-Harbor-Quartz-7421"
ROLES = ("viewer", "analyst", "manager", "tenant_admin", "finance_analyst", "platform_admin")


def _admin() -> str:
    url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not url:
        pytest.skip("TEST_DATABASE_ADMIN_URL is not set (needs PostgreSQL with pgvector)")
    return url.replace("+psycopg", "")


@pytest.fixture(scope="session")
def template_db() -> Iterator[str]:
    admin = _admin()
    name = f"tmpl_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    base = admin.rsplit("/", 1)[0]
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"{base}/{name}"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    command.upgrade(cfg, "head")
    with psycopg.connect(admin, autocommit=True) as conn:  # alembic leaves a pooled connection
        conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
    if old is None:
        del os.environ["DATABASE_URL"]
    else:
        os.environ["DATABASE_URL"] = old
    yield name
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.fixture()
def db_name(template_db: str) -> Iterator[str]:
    admin = _admin()
    name = f"t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template_db}"')
    yield name
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_settings(url: str, **overrides: Any) -> Settings:
    base = dict(
        database_url=url, cookie_secure=True, argon_time_cost=1, argon_memory_kib=64,
        argon_parallelism=1, allow_ephemeral_secrets=True, ip_limit=(100_000, 60),
        user_limit=(100_000, 60), key_limit=(100_000, 60), login_ip_limit=(1000, 60),
        login_account_limit=(1000, 900), web_base_url="https://app.test")
    base.update(overrides)
    return Settings(**base)


@dataclass
class World:
    container: Container
    mailer: MemoryMailer
    tenant_a: str
    tenant_b: str
    users: dict[tuple[str, str], str] = field(default_factory=dict)  # (tenant key, role) -> id
    totp: dict[str, str] = field(default_factory=dict)  # user id -> secret

    def email(self, tenant: str, role: str) -> str:
        return f"{role}@{tenant}.example"


def _seed(c: Container, mailer: MemoryMailer) -> World:
    with c.db.system() as conn:
        ta = conn.execute("INSERT INTO tenants (name) VALUES ('Tenant A') RETURNING id").fetchone()["id"]
        tb = conn.execute("INSERT INTO tenants (name) VALUES ('Tenant B') RETURNING id").fetchone()["id"]
        world = World(c, mailer, str(ta), str(tb))
        pw = c.passwords.hash(PASSWORD)
        for key, tid in (("a", ta), ("b", tb)):
            for role in ("viewer", "analyst", "manager", "tenant_admin"):
                uid = conn.execute(
                    "INSERT INTO users (tenant_id, email, password_hash, role) VALUES (%s,%s,%s,%s) "
                    "RETURNING id", (tid, world.email(key, role), pw, role)).fetchone()["id"]
                world.users[(key, role)] = str(uid)
        for role in ("finance_analyst", "platform_admin"):
            uid = conn.execute(
                "INSERT INTO users (tenant_id, email, password_hash, role) VALUES (NULL,%s,%s,%s) "
                "RETURNING id", (world.email("platform", role), pw, role)).fetchone()["id"]
            world.users[("platform", role)] = str(uid)
    return world


@pytest.fixture()
def world(db_name: str) -> Iterator[World]:
    url = _admin().rsplit("/", 1)[0] + f"/{db_name}"
    settings = test_settings(url)
    mailer = MemoryMailer()
    container = Container.build(settings, Database(url, max_size=6), mailer,
                                MemoryRateLimiter(), MemoryBroker())
    yield _seed(container, mailer)
    container.db.close()


class Api:
    """Test client wrapper that mirrors the browser: cookies plus the double-submit CSRF header."""

    def __init__(self, world: World, **client_kwargs: Any) -> None:
        self.world = world
        self.app = create_app(world.container.settings, world.container)
        self.http = TestClient(self.app, base_url="https://testserver", **client_kwargs)

    def _hdrs(self, extra: dict[str, str] | None) -> dict[str, str]:
        h = dict(extra or {})
        csrf = self.http.cookies.get("pr_csrf")
        if csrf:
            h.setdefault("X-CSRF-Token", csrf)
        return h

    def request(self, method: str, url: str, headers: dict[str, str] | None = None, **kw: Any) -> Any:
        return self.http.request(method, f"/api/v1{url}", headers=self._hdrs(headers), **kw)

    def get(self, url: str, **kw: Any) -> Any:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> Any:
        return self.request("POST", url, **kw)

    def patch(self, url: str, **kw: Any) -> Any:
        return self.request("PATCH", url, **kw)

    def put(self, url: str, **kw: Any) -> Any:
        return self.request("PUT", url, **kw)

    def delete(self, url: str, **kw: Any) -> Any:
        return self.request("DELETE", url, **kw)

    # -- sign-in helpers
    def enroll_mfa(self, user_id: str) -> str:
        """Pre-enroll TOTP directly in the database (test shortcut)."""
        c = self.world.container
        secret = pyotp.random_base32()
        with c.db.system() as conn:
            conn.execute(
                "INSERT INTO user_mfa (user_id, secret_encrypted, confirmed_at) VALUES (%s,%s,now()) "
                "ON CONFLICT (user_id) DO UPDATE SET secret_encrypted = EXCLUDED.secret_encrypted, "
                "confirmed_at = now()", (user_id, c.cipher.encrypt(secret.encode())))
        self.world.totp[user_id] = secret
        return secret

    def code_for(self, user_id: str) -> str:
        with self.world.container.db.system() as conn:
            conn.execute("UPDATE user_mfa SET last_used_step = NULL WHERE user_id = %s", (user_id,))
        return pyotp.TOTP(self.world.totp[user_id]).now()

    def login(self, tenant: str, role: str, password: str = PASSWORD) -> Any:
        email = self.world.email(tenant, role)
        r = self.post("/auth/login", json={"email": email, "password": password})
        if r.status_code == 200 and r.json().get("status") == "mfa_required":
            uid = self.world.users[(tenant, role)]
            r = self.post("/auth/mfa/verify", json={"mfa_token": r.json()["mfa_token"],
                                                    "code": self.code_for(uid)})
        return r

    def as_role(self, tenant: str, role: str) -> Api:
        if role in ("tenant_admin", "platform_admin"):
            self.enroll_mfa(self.world.users[(tenant, role)])
        r = self.login(tenant, role)
        assert r.status_code == 200, r.text
        return self


@pytest.fixture()
def api(world: World) -> Api:
    return Api(world)


def make_client(world: World, tenant: str, role: str) -> Api:
    return Api(world).as_role(tenant, role)


@pytest.fixture()
def client_factory(world: World) -> Any:
    def make(tenant: str, role: str) -> Api:
        return make_client(world, tenant, role)

    return make


def wait_until(predicate: Any, timeout: float = 3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def seed_catalog(world: World) -> dict[str, int]:
    """Companies, a parent edge, and events for the knowledge endpoints. Returns name -> id."""
    ids: dict[str, int] = {}
    with world.container.db.system() as conn:
        for name, state, city, cik in (
            ("Northgate Metals Corporation", "PA", "Pittsburgh", 1003),
            ("Northgate Metals of Texas LLC", "TX", "Houston", None),
            ("Harborline Foods, Inc.", "OH", "Columbus", 1001),
            ("Cobalt Ridge Logistics Co.", "TN", "Memphis", None),
            ("Cobalt Ridge Logistics Co.", "NV", "Reno", None),
        ):
            from app.kb.normalize import normalize_name

            row = conn.execute(
                "INSERT INTO companies (canonical_name, normalized_name, cik, hq_state, hq_city) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (name, normalize_name(name), cik, state, city)).fetchone()
            ids[f"{name}|{state}"] = row["id"]
        parent, child = ids["Northgate Metals Corporation|PA"], ids["Northgate Metals of Texas LLC|TX"]
        conn.execute("INSERT INTO company_relationships (parent_id, child_id, rel_type, source) "
                     "VALUES (%s,%s,'direct_parent','gleif')", (parent, child))
    world.container.resolver_cache.pop("resolver", None)
    return ids


def seed_event(world: World, company_id: int, route: str = "accepted", title: str = "OSHA citation record",
               severity: int = 3) -> int:
    with world.container.db.system() as conn:
        ev = conn.execute(
            "INSERT INTO events (source, source_id, event_type, severity, reported_at, title, state) "
            "VALUES ('osha', %s, 'workplace_safety', %s, now(), %s, 'TX') RETURNING id",
            (uuid.uuid4().hex, severity, title)).fetchone()["id"]
        ee = conn.execute(
            "INSERT INTO event_entities (event_id, company_id, role, method, score, route) "
            "VALUES (%s,%s,'operator','test',0.95,%s) RETURNING id", (ev, company_id, route)
        ).fetchone()["id"]
        conn.execute("INSERT INTO link_candidates (event_entity_id, rank, company_id, splink_score) "
                     "VALUES (%s,1,%s,0.9)", (ee, company_id))
    return int(ev)
