"""Helpers shared by the regulator normalizers."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.events.rules import EventRules

_NUM = re.compile(r"[^0-9.\-]")


class NormalizeStats(Counter[str]):
    """Counts of produced events and skip reasons, for the ingest log and quality report."""


def field(row: Mapping[str, Any], rules: EventRules, source: str, logical: str,
          stats: NormalizeStats | None = None) -> Any:
    """Value of a logical field through the rules field map. Missing fields are counted."""
    column = rules.fields(source)[logical]
    value = row.get(column)
    if value is None or (isinstance(value, str) and not value.strip()):
        if stats is not None:
            stats[f"missing_field:{logical}"] += 1
        return None
    return value.strip() if isinstance(value, str) else value


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    cleaned = _NUM.sub("", str(value))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except ValueError:
        return None


def money(value: float) -> str:
    return f"${value:,.0f}"


def clean_state(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().upper()
    return text if len(text) == 2 else None
