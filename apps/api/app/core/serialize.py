"""Row to response helpers shared by routers and services."""

from __future__ import annotations

import uuid
from typing import Any


def jsonable(row: dict[str, Any], drop: tuple[str, ...] = ()) -> dict[str, Any]:
    """Row to a response dict: UUIDs as strings, selected columns removed."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in drop:
            continue
        out[k] = str(v) if isinstance(v, uuid.UUID) else v
    return out
