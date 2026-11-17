"""Create and seed the database used by the end-to-end tests.

Usage: PYTHONPATH=.:apps/api python apps/web/e2e/seed_api.py postgresql://user@host:port/postgres
Creates database `web_e2e` (replacing it), runs the migrations, and adds a demo tenant with a manager,
a tenant administrator (multi-factor enrollment is required), and a viewer with a pending reset token.
Prints the DATABASE_URL to start the API with.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import psycopg
from alembic import command
from alembic.config import Config

PASSWORD = "Violet-Harbor-Quartz-7421"
RESET_TOKEN = "e2e-reset-token-0123456789"


def main(admin_url: str) -> None:
    admin_url = admin_url.replace("postgresql+psycopg://", "postgresql://")
    base = admin_url.rsplit("/", 1)[0]
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS web_e2e WITH (FORCE)")
        conn.execute("CREATE DATABASE web_e2e")
    url = f"{base}/web_e2e"
    os.environ["DATABASE_URL"] = url
    cfg = Config("apps/api/alembic.ini")
    cfg.set_main_option("script_location", "apps/api/migrations")
    command.upgrade(cfg, "head")

    from app.auth.passwords import PasswordService
    from app.auth.tokens import hash_token
    from app.settings import Settings

    pw = PasswordService(Settings(argon_time_cost=1, argon_memory_kib=64, argon_parallelism=1)).hash(PASSWORD)
    with psycopg.connect(url) as conn:
        tenant = conn.execute("INSERT INTO tenants (name) VALUES ('Demo Tenant') RETURNING id").fetchone()[0]  # type: ignore[index]
        for email, role in (("manager@demo.example", "manager"), ("admin@demo.example", "tenant_admin"),
                            ("reset@demo.example", "viewer")):
            uid = conn.execute("INSERT INTO users (tenant_id, email, password_hash, role) VALUES (%s,%s,%s,%s) "
                               "RETURNING id", (tenant, email, pw, role)).fetchone()[0]  # type: ignore[index]
            if role == "viewer":
                conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s,%s,%s)",
                             (uid, hash_token(RESET_TOKEN), datetime.now(UTC) + timedelta(hours=2)))
    print(url)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.environ["E2E_ADMIN_URL"])
