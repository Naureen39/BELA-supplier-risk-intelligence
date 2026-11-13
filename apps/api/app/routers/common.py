"""Helpers shared by routers."""

from __future__ import annotations

import uuid
from typing import Any

from app.auth.deps import Principal
from app.container import Container
from app.core import audit
from app.core.errors import ApiError
from app.core.pagination import clamp_limit, decode_cursor, encode_cursor


def jsonable(row: dict[str, Any], drop: tuple[str, ...] = ()) -> dict[str, Any]:
    """Row to a response dict: UUIDs as strings, selected columns removed."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in drop:
            continue
        out[k] = str(v) if isinstance(v, uuid.UUID) else v
    return out


def parse_uuid(value: str, what: str = "id") -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ApiError(404, f"The {what} was not found.", code="not-found") from exc


def keyset(c: Container, cursor: str | None, limit: int) -> tuple[list[Any] | None, int]:
    return decode_cursor(cursor, c.cursor_secret), clamp_limit(limit)


def page(c: Container, rows: list[dict[str, Any]], limit: int, key_fields: tuple[str, ...]
         ) -> dict[str, Any]:
    """Build a page from `limit + 1` fetched rows."""
    more = len(rows) > limit
    items = rows[:limit]
    nxt = encode_cursor([str(items[-1][f]) for f in key_fields], c.cursor_secret) if more else None
    return {"items": [jsonable(r) for r in items], "next_cursor": nxt}


def audit_event(c: Container, p: Principal, action: str, target_type: str | None = None,
                target_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
    audit.record(c.db, action=action, tenant_id=p.tenant_id, actor=p.user_id,
                 target_type=target_type, target_id=target_id,
                 detail={**(detail or {}), **({"api_key": p.key_id} if p.key_id else {})})
