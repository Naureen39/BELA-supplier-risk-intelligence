"""Alembic environment. The database URL comes from DATABASE_URL (psycopg driver)."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ.get("DATABASE_URL", "")
if not url:
    raise RuntimeError("DATABASE_URL is not set (example: postgresql+psycopg://user:pw@host/db)")

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
