"""Monitoring: alert creation after score recomputation, de-duplicated per supplier and event."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from app.events.risk import LEVELS, SupplierScore

HIGH_SEVERITY = 3


@dataclass(frozen=True)
class AlertRule:
    id: str
    event_types: frozenset[str] = frozenset()  # empty means all
    min_severity: int = 3
    supplier_tiers: frozenset[str] = frozenset()  # empty means all
    states: frozenset[str] = frozenset()  # empty means all
    is_active: bool = True


@dataclass(frozen=True)
class EventFacts:
    event_id: int
    event_type: str
    severity: int
    state: str | None


@dataclass(frozen=True)
class SupplierFacts:
    supplier_id: str
    tier: str | None = None


@dataclass(frozen=True)
class AlertDraft:
    supplier_id: str
    kind: str  # threshold_crossing or high_severity_event
    event_id: int | None
    rule_id: str | None
    detail: str

    @property
    def dedup_key(self) -> tuple[str, str, int | None]:
        return (self.supplier_id, self.kind, self.event_id)


def crossed_threshold(previous_level: str | None, new_level: str, floor: str = "high") -> bool:
    """True when the level rose from below `floor` to `floor` or above."""
    prev = LEVELS.index(previous_level) if previous_level else -1
    return LEVELS.index(new_level) >= LEVELS.index(floor) > prev


def rule_matches(rule: AlertRule, ev: EventFacts, sup: SupplierFacts) -> bool:
    return (
        rule.is_active
        and ev.severity >= rule.min_severity
        and (not rule.event_types or ev.event_type in rule.event_types)
        and (not rule.supplier_tiers or (sup.tier or "") in rule.supplier_tiers)
        and (not rule.states or (ev.state or "") in rule.states)
    )


def draft_alerts(
    supplier: SupplierFacts,
    previous: SupplierScore | None,
    current: SupplierScore,
    new_events: Iterable[EventFacts],
    rules: Collection[AlertRule],
    existing: Collection[tuple[str, str, int | None]] = (),
) -> list[AlertDraft]:
    """Alerts for one supplier. `existing` holds dedup keys of alerts already raised.

    - A threshold crossing alert when the level rises to high or critical.
    - A high-severity event alert per new event, once per supplier and event.
    - Tenant rules can also raise an event alert at lower severities.
    """
    drafts: list[AlertDraft] = []
    seen = set(existing)

    def add(d: AlertDraft) -> None:
        if d.dedup_key not in seen:
            seen.add(d.dedup_key)
            drafts.append(d)

    if crossed_threshold(previous.level if previous else None, current.level):
        add(AlertDraft(supplier.supplier_id, "threshold_crossing", None, None,
                       f"risk level {previous.level if previous else 'none'} to {current.level} "
                       f"(score {current.score:.1f})"))
    for ev in new_events:
        matched = [r for r in rules if rule_matches(r, ev, supplier)]
        if matched:
            add(AlertDraft(supplier.supplier_id, "high_severity_event", ev.event_id, matched[0].id,
                           f"{ev.event_type} severity {ev.severity} matched rule {matched[0].id}"))
        elif ev.severity >= HIGH_SEVERITY:
            add(AlertDraft(supplier.supplier_id, "high_severity_event", ev.event_id, None,
                           f"{ev.event_type} severity {ev.severity}"))
    return drafts
