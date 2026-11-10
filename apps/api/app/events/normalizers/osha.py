"""OSHA violation rows (joined with inspection fields) to events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.events.normalizers.common import NormalizeStats, clean_state, field, money, to_number
from app.events.rules import EventRules
from app.events.schema import REGULATOR, EntityRef, NormalizedEvent, clamp_severity, parse_date

SOURCE = "osha"


def normalize_row(row: Mapping[str, Any], rules: EventRules,
                  stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    stats = stats if stats is not None else NormalizeStats()

    def f(logical: str) -> Any:
        return field(row, rules, SOURCE, logical, stats)

    activity, citation, name = f("activity"), f("citation"), f("name")
    if not activity or not name:
        stats["skipped:no_identity"] += 1
        return []
    sec = rules.section(SOURCE)
    penalty = to_number(f("current_penalty"))
    if penalty is None:
        penalty = to_number(f("initial_penalty")) or 0.0
    if penalty < float(sec["min_penalty"]):
        stats["skipped:below_threshold"] += 1
        return []
    when = parse_date(f("issuance_date")) or parse_date(f("open_date"))
    if when is None:
        stats["skipped:no_date"] += 1
        return []
    if when.year < rules.min_year:
        stats["skipped:too_old"] += 1
        return []
    vtype = str(f("violation_type") or "U").upper()[:1]
    severity = rules.band(SOURCE, "penalty_bands", penalty)
    if vtype in sec["bump_types"]:
        severity += 1
    label = sec["violation_types"].get(vtype, "unclassified")
    state = clean_state(f("state"))
    stats["events"] += 1
    return [NormalizedEvent(
        source=SOURCE, source_id=f"{activity}:{citation or 'na'}", source_class=REGULATOR,
        event_type="workplace_safety", severity=clamp_severity(severity), reported_at=when,
        occurred_at=parse_date(f("open_date")),
        title=f"OSHA citation record for {name}: {label} classification, "
              f"penalty {money(penalty)}",
        summary="Citation record from US Department of Labor enforcement data. Citations can be "
                "contested and amended; a record is not a final finding.",
        url=f"https://www.osha.gov/ords/imis/establishment.inspection_detail?id={activity}",
        state=state, city=f("city"),
        entities=[EntityRef(str(name), "operator", state, f("city"))],
        raw_ref={"activity_nr": str(activity), "citation_id": str(citation), "viol_type": vtype,
                 "penalty": penalty}, rules_version=rules.version)]


def normalize_rows(rows: Iterable[Mapping[str, Any]], rules: EventRules,
                   stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    return [e for r in rows for e in normalize_row(r, rules, stats)]
