from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def admin_url() -> str:
    url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not url:
        pytest.skip("TEST_DATABASE_ADMIN_URL is not set (needs PostgreSQL with pgvector)")
    return url


@pytest.fixture()
def db_url(admin_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A fresh database migrated to head."""
    name = f"t_{uuid.uuid4().hex[:10]}"
    base = admin_url.rsplit("/", 1)[0]
    with psycopg.connect(admin_url.replace("+psycopg", ""), autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = f"{base}/{name}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    command.upgrade(config, "head")
    yield url
    with psycopg.connect(admin_url.replace("+psycopg", ""), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
