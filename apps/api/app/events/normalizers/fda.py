"""openFDA enforcement report records (food, drug, device) to events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.events.normalizers.common import NormalizeStats, clean_state, field
from app.events.rules import EventRules
from app.events.schema import REGULATOR, EntityRef, NormalizedEvent, clamp_severity, parse_date

SOURCE = "openfda"


def normalize_row(row: Mapping[str, Any], rules: EventRules,
                  stats: NormalizeStats | None = None, kind: str = "food") -> list[NormalizedEvent]:
    stats = stats if stats is not None else NormalizeStats()

    def f(logical: str) -> Any:
        return field(row, rules, SOURCE, logical, stats)

    number, firm = f("number"), f("firm")
    if not number or not firm:
        stats["skipped:no_identity"] += 1
        return []
    when = parse_date(f("report_date")) or parse_date(f("initiation_date"))
    if when is None:
        stats["skipped:no_date"] += 1
        return []
    if when.year < rules.min_year:
        stats["skipped:too_old"] += 1
        return []
    classification = str(f("classification") or "")
    severity = int(rules.section(SOURCE)["class_severity"].get(classification, 2))
    state = clean_state(f("state"))
    stats["events"] += 1
    return [NormalizedEvent(
        source=SOURCE, source_id=f"{kind}:{number}", source_class=REGULATOR,
        event_type="product_safety_recall", severity=clamp_severity(severity), reported_at=when,
        occurred_at=parse_date(f("initiation_date")),
        title=f"FDA {kind} recall {number} ({classification or 'unclassified'}) "
              f"initiated by {firm}",
        summary=(str(f("reason") or "")[:300] or None),
        url="https://www.accessdata.fda.gov/scripts/ires/",
        state=state, city=f("city"), entities=[EntityRef(str(firm), "recalling_firm", state, f("city"))],
        raw_ref={"recall_number": str(number), "classification": classification, "kind": kind},
        rules_version=rules.version)]


def normalize_rows(rows: Iterable[Mapping[str, Any]], rules: EventRules,
                   stats: NormalizeStats | None = None, kind: str = "food") -> list[NormalizedEvent]:
    return [e for r in rows for e in normalize_row(r, rules, stats, kind)]
