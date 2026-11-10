"""EPA ECHO facility rows to events (formal actions, penalties, significant noncompliance)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.events.normalizers.common import NormalizeStats, clean_state, field, money, to_number
from app.events.rules import EventRules
from app.events.schema import REGULATOR, EntityRef, NormalizedEvent, clamp_severity, parse_date

SOURCE = "epa_echo"


def normalize_row(row: Mapping[str, Any], rules: EventRules,
                  stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    stats = stats if stats is not None else NormalizeStats()

    def f(logical: str) -> Any:
        return field(row, rules, SOURCE, logical, stats)

    registry, name = f("registry_id"), f("name")
    if not registry or not name:
        stats["skipped:no_identity"] += 1
        return []
    penalties = to_number(f("penalties")) or 0.0
    actions = int(to_number(f("formal_action_count")) or 0)
    snc = str(f("significant_noncompliance") or "").upper() in {"Y", "YES", "1", "TRUE"}
    when = parse_date(f("last_action_date"))
    if not (snc or penalties > 0 or actions > 0):
        stats["skipped:no_enforcement_signal"] += 1
        return []
    if when is None:
        stats["skipped:no_date"] += 1
        return []
    if when.year < rules.min_year:
        stats["skipped:too_old"] += 1
        return []
    sec = rules.section(SOURCE)
    severity = rules.band(SOURCE, "penalty_bands", penalties)
    if snc:
        severity = max(severity, int(sec["snc_base_severity"]))
    parts = []
    if actions:
        parts.append(f"{actions} formal enforcement action{'s' if actions != 1 else ''}")
    if penalties > 0:
        parts.append(f"total penalties of {money(penalties)}")
    if snc:
        parts.append("a significant noncompliance status")
    title = f"EPA ECHO record for {name}: " + ", ".join(parts)
    stats["events"] += 1
    return [NormalizedEvent(
        source=SOURCE, source_id=f"{registry}:{when:%Y%m%d}", source_class=REGULATOR,
        event_type="environmental", severity=clamp_severity(severity), reported_at=when,
        occurred_at=when, title=title,
        summary="Record from the EPA ECHO facility data. A record is not a finding of fault.",
        url=f"https://echo.epa.gov/detailed-facility-report?fid={registry}",
        state=clean_state(f("state")), city=f("city"),
        latitude=to_number(f("latitude")), longitude=to_number(f("longitude")),
        entities=[EntityRef(str(name), "operator", clean_state(f("state")), f("city"))],
        raw_ref={"registry_id": str(registry), "penalties": penalties, "snc": snc,
                 "formal_actions": actions}, rules_version=rules.version)]


def normalize_rows(rows: Iterable[Mapping[str, Any]], rules: EventRules,
                   stats: NormalizeStats | None = None) -> list[NormalizedEvent]:
    return [e for r in rows for e in normalize_row(r, rules, stats)]
