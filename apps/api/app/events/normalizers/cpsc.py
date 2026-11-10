"""CPSC recall JSON records to events: one event per recall, one entity per named firm."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.events.normalizers.common import NormalizeStats, field, to_number
from app.events.rules import EventRules
from app.events.schema import REGULATOR, EntityRef, NormalizedEvent, clamp_severity, parse_date

SOURCE = "cpsc"
_ROLES = (("Manufacturers", "manufacturer"), ("Retailers", "retailer"),
          ("Importers", "importer"), ("Distributors", "distributor"))
_UNITS = re.compile(r"([\d,]+)")


def _units(products: Any) -> float:
    total = 0.0
    for p in products or []:
        match = _UNITS.search(str(p.get("NumberOfUnits", "")))
        if match:
            total += to_number(match.group(1)) or 0.0
    return total


def normalize_row(row: Mapping[str, Any], rules: EventRules,
                  stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    stats = stats if stats is not None else NormalizeStats()

    def f(logical: str) -> Any:
        return field(row, rules, SOURCE, logical, stats)

    number = f("number") or f("id")
    when = parse_date(f("date"))
    if not number or when is None:
        stats["skipped:no_identity_or_date"] += 1
        return []
    if when.year < rules.min_year:
        stats["skipped:too_old"] += 1
        return []
    sec = rules.section(SOURCE)
    hazards = " ".join(str(h.get("Name", "")) for h in (f("hazards") or [])).lower()
    severity = int(sec["default_severity"])
    for level in sorted(sec["hazard_keywords"], key=int):
        if any(k in hazards for k in sec["hazard_keywords"][level]):
            severity = max(severity, int(level))
    units = _units(f("products"))
    if units >= float(sec["large_units"]):
        severity += 1
    entities = [EntityRef(str(m["Name"]), role) for key, role in _ROLES
                for m in row.get(key, []) or [] if m.get("Name")]
    if not entities:
        stats["skipped:no_firms"] += 1
        return []
    stats["events"] += 1
    return [NormalizedEvent(
        source=SOURCE, source_id=str(number), source_class=REGULATOR,
        event_type="product_safety_recall", severity=clamp_severity(severity), reported_at=when,
        occurred_at=when, title=f"CPSC recall {number}: {f('title') or 'consumer product recall'}",
        summary=(hazards[:300] or None), url=f("url"), entities=entities,
        raw_ref={"recall_number": str(number), "units": units}, rules_version=rules.version)]


def normalize_rows(rows: Iterable[Mapping[str, Any]], rules: EventRules,
                   stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    return [e for r in rows for e in normalize_row(r, rules, stats)]
