"""Signed keyset cursors and the page envelope."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.core.errors import ApiError

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


def encode_cursor(values: list[Any], secret: bytes) -> str:
    raw = json.dumps(values, separators=(",", ":"), default=str).encode()
    sig = hmac.new(secret, raw, hashlib.sha256).digest()[:12]
    return base64.urlsafe_b64encode(sig + raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, secret: bytes) -> list[Any] | None:
    if not cursor:
        return None
    try:
        data = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        sig, raw = data[:12], data[12:]
        if not hmac.compare_digest(sig, hmac.new(secret, raw, hashlib.sha256).digest()[:12]):
            raise ValueError("bad signature")
        values = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "The cursor is not valid.", code="bad-cursor") from exc
    if not isinstance(values, list):
        raise ApiError(400, "The cursor is not valid.", code="bad-cursor")
    return values


def clamp_limit(limit: int, default: int = 50, maximum: int = 200) -> int:
    return default if limit <= 0 else min(limit, maximum)
