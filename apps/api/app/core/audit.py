"""Append-only audit log with a hash chain.

Writes use their own system transaction so security events persist even when the request fails.
Each row stores `prev_hash` and `row_hash = sha256(prev_hash || canonical fields)`. A serializing
advisory lock keeps the chain linear. `verify_chain` recomputes it and reports the first break.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from app.db import Database

GENESIS = "0" * 64
_LOCK_KEY = 7_340_001
_SENSITIVE = re.compile(r"pass(word)?|token|secret|code|key|hash|tax|account", re.IGNORECASE)


def sanitize(detail: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (detail or {}).items():
        out[k] = "[redacted]" if _SENSITIVE.search(k) else v
    return out


def _canonical(prev: str, occurred: datetime, tenant_id: str | None, actor: str | None,
               action: str, target_type: str | None, target_id: str | None,
               detail: dict[str, Any]) -> str:
    payload = json.dumps(
        [prev, occurred.astimezone(UTC).isoformat(), tenant_id, actor, action, target_type,
         target_id, detail], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def record(db: Database, *, action: str, tenant_id: str | None = None, actor: str | None = None,
           target_type: str | None = None, target_id: str | None = None,
           detail: dict[str, Any] | None = None) -> None:
    clean = sanitize(detail)
    with db.system() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        row = conn.execute("SELECT row_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev = str(row["row_hash"]) if row else GENESIS
        now = datetime.now(UTC).replace(microsecond=0)
        digest = _canonical(prev, now, tenant_id, actor, action, target_type, target_id, clean)
        conn.execute(
            "INSERT INTO audit_log (occurred_at, tenant_id, actor_user_id, action, target_type, "
            "target_id, detail, prev_hash, row_hash) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
            (now, tenant_id, actor, action, target_type, target_id, json.dumps(clean), prev, digest))


def verify_chain(db: Database) -> tuple[bool, int | None, int]:
    """Return (ok, first_bad_seq, rows_checked)."""
    prev = GENESIS
    n = 0
    with db.system() as conn:
        for r in conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall():
            n += 1
            expected = _canonical(prev, r["occurred_at"], _s(r["tenant_id"]), _s(r["actor_user_id"]),
                                  r["action"], r["target_type"], r["target_id"], r["detail"])
            if r["prev_hash"] != prev or r["row_hash"] != expected:
                return False, int(r["seq"]), n
            prev = r["row_hash"]
    return True, None, n


def _s(value: Any) -> str | None:
    return None if value is None else str(value)
