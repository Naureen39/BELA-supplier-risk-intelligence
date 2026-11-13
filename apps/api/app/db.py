"""Database access: a system connection (owner) and tenant-scoped connections.

Tenant connections run `SET LOCAL ROLE app_user` and set `app.tenant_id` (and `app.platform` for
platform administrators) inside the request transaction, so PostgreSQL row level security binds
every query. System connections serve authentication and background jobs.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


class Database:
    def __init__(self, url: str, min_size: int = 1, max_size: int = 10) -> None:
        self.pool = ConnectionPool(
            normalize_url(url), min_size=min_size, max_size=max_size, open=True,
            kwargs={"row_factory": dict_row}, timeout=10)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def system(self) -> Iterator[Any]:
        """Owner connection in a transaction (no row level security)."""
        with self.pool.connection() as conn:
            yield conn

    @contextmanager
    def tenant(self, tenant_id: str | None, platform: bool = False) -> Iterator[Any]:
        """Connection restricted to `app_user` with the tenant context set for this transaction."""
        with self.pool.connection() as conn:
            conn.execute("SET LOCAL ROLE app_user")
            conn.execute("SELECT set_config('app.tenant_id', %s, true), "
                         "set_config('app.platform', %s, true)",
                         (tenant_id or "", "on" if platform else "off"))
            yield conn

    def ping(self) -> bool:
        try:
            with self.system() as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False
