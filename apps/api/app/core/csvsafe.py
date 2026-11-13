"""CSV export helpers with formula injection protection."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Any

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    """Prefix text cells that a spreadsheet could execute as a formula."""
    if isinstance(value, str) and value.startswith(_DANGEROUS):
        return "'" + value
    return value


def to_csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([safe_cell(h) for h in header])
    for row in rows:
        writer.writerow([safe_cell(c) for c in row])
    return buf.getvalue()
