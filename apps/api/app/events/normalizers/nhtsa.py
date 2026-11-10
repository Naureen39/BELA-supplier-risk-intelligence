"""NHTSA recall flat-file rows (tab-delimited, layout in RCL.txt) to events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.events.normalizers.common import NormalizeStats, field, to_number
from app.events.rules import EventRules
from app.events.schema import REGULATOR, EntityRef, NormalizedEvent, clamp_severity, parse_date

SOURCE = "nhtsa"


def normalize_row(row: Mapping[str, Any], rules: EventRules,
                  stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    stats = stats if stats is not None else NormalizeStats()

    def f(logical: str) -> Any:
        return field(row, rules, SOURCE, logical, stats)

    campaign, maker = f("campaign"), f("manufacturer")
    if not campaign or not maker:
        stats["skipped:no_identity"] += 1
        return []
    when = parse_date(f("report_date"))
    if when is None:
        stats["skipped:no_date"] += 1
        return []
    if when.year < rules.min_year:
        stats["skipped:too_old"] += 1
        return []
    units = to_number(f("units")) or 0.0
    component = str(f("component") or "")
    severity = rules.band(SOURCE, "units_bands", units)
    if any(c in component.lower() for c in rules.section(SOURCE)["critical_components"]):
        severity += 1
    stats["events"] += 1
    return [NormalizedEvent(
        source=SOURCE, source_id=str(campaign), source_class=REGULATOR,
        event_type="product_safety_recall", severity=clamp_severity(severity), reported_at=when,
        occurred_at=when,
        title=f"NHTSA recall campaign {campaign} by {maker}"
              + (f" ({component.title()}, {int(units):,} units potentially affected)"
                 if component and units else ""),
        summary=(str(f("defect") or "")[:300] or None),
        url=f"https://www.nhtsa.gov/recalls?nhtsaId={campaign}",
        entities=[EntityRef(str(maker), "manufacturer")],
        raw_ref={"campaign": str(campaign), "units": units, "component": component},
        rules_version=rules.version)]


def normalize_rows(rows: Iterable[Mapping[str, Any]], rules: EventRules,
                   stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    return [e for r in rows for e in normalize_row(r, rules, stats)]
