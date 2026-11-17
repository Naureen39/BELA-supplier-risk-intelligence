"""Date windows, granularity, comparison periods, and JSON/CSV shaping shared by analytics."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, TypeVar

from app.core.csvsafe import to_csv
from app.core.errors import ApiError

Granularity = Literal["day", "week", "month"]
BUCKETS: dict[str, str] = {"day": "day", "week": "week", "month": "month"}
MAX_WINDOW_DAYS = 3660


T = TypeVar("T")


def plain(value: T) -> T:
    """Make query results JSON-serializable and cacheable (the shape is kept, values are converted)."""
    out: Any = _plain(value)
    return out  # type: ignore[no-any-return]


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


@dataclass(frozen=True)
class Window:
    start: date
    end: date  # inclusive

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> Window:
        return Window(self.start - timedelta(days=self.days), self.start - timedelta(days=1))


def window(start: date | None, end: date | None, default_end: date, default_days: int = 90) -> Window:
    end = end or default_end
    start = start or end - timedelta(days=default_days - 1)
    if start > end:
        raise ApiError(422, "The start date must not be after the end date.", code="validation")
    if (end - start).days >= MAX_WINDOW_DAYS:
        raise ApiError(422, "The date range is too long (maximum ten years).", code="validation")
    return Window(start, end)


def month_floor(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def change(current: float | None, previous: float | None) -> float | None:
    """Percent change versus the previous period; None when it is not defined."""
    if current is None or previous is None or previous == 0:
        return None
    return round(100 * (current - previous) / abs(previous), 2)


def csv_response_body(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    header = list(rows[0])
    return to_csv(header, [[r.get(h) for h in header] for r in rows])


def require_rows_for_csv(section: str | None, available: dict[str, list[dict[str, Any]]]
                         ) -> list[dict[str, Any]]:
    if section not in available:
        raise ApiError(422, f"Choose a section for CSV export: {', '.join(sorted(available))}.",
                       code="validation")
    return available[section]
