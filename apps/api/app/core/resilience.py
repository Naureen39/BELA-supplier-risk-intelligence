"""Retries with backoff and the dead letter queue.

`retry_call` retries transient failures with exponential backoff and jitter. Work that still fails is written
to `dead_letters` (platform data, system connection) so it is not lost: a platform administrator can retry or
discard it from `/platform/dead-letters`.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

import structlog

from app.db import Database

T = TypeVar("T")
log = structlog.get_logger()


def retry_call(fn: Callable[[], T], attempts: int = 3, base_delay: float = 0.2,
               retry_on: tuple[type[BaseException], ...] = (Exception,),
               sleep: Callable[[float], None] = time.sleep) -> T:
    """Call `fn` up to `attempts` times. The delay doubles each time and carries up to 25 percent jitter."""
    for attempt in range(attempts):
        try:
            return fn()
        except retry_on as exc:
            if attempt + 1 >= attempts:
                raise
            delay = base_delay * 2**attempt
            log.warning("retrying", attempt=attempt + 1, error_type=type(exc).__name__)
            sleep(delay * (1 + random.random() * 0.25))  # nosec B311
    raise AssertionError("unreachable")  # pragma: no cover


def dead_letter(db: Database, kind: str, error: str, *, tenant_id: str | None = None, reference: str | None = None,
                payload: dict[str, Any] | None = None, attempts: int = 1) -> None:
    """Record a failed unit of work. A second failure of the same open item increments its attempt count."""
    try:
        with db.system() as conn:
            conn.execute(
                "INSERT INTO dead_letters (kind, tenant_id, reference, payload, error, attempts) "
                "VALUES (%s,%s,%s,%s::jsonb,%s,%s) "
                "ON CONFLICT (kind, reference) WHERE status = 'open' AND reference IS NOT NULL "
                "DO UPDATE SET attempts = dead_letters.attempts + EXCLUDED.attempts, error = EXCLUDED.error",
                (kind, tenant_id, reference, json.dumps(payload or {}), error[:500], attempts))
    except Exception:  # the queue itself must never turn one failure into two
        log.error("dead_letter_write_failed", kind=kind)
