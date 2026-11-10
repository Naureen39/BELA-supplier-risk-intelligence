"""Common event schema shared by regulator normalizers, the news classifier, and scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

EVENT_TYPES: tuple[str, ...] = (
    "workplace_safety",
    "environmental",
    "product_safety_recall",
    "regulatory_enforcement",
    "litigation",
    "financial_distress",
    "operational_disruption",
    "cyber_incident",
    "governance_fraud",
    "other",
    "none",
)
SCORED_TYPES: frozenset[str] = frozenset(EVENT_TYPES) - {"none"}

REGULATOR = "regulator"
NEWS = "news"


@dataclass(frozen=True)
class EntityRef:
    """A company named by an event record, before resolution."""

    name: str
    role: str  # operator, manufacturer, recalling_firm, retailer, importer, distributor, mentioned
    state: str | None = None
    city: str | None = None
    country: str | None = None
    identifiers: dict[str, str] = field(default_factory=dict)


@dataclass
class NormalizedEvent:
    source: str  # epa_echo, osha, nhtsa, cpsc, openfda, news
    source_id: str  # stable id for idempotent reloads
    source_class: str  # regulator or news
    event_type: str
    severity: int  # 1 to 4
    reported_at: datetime
    title: str  # states what the record says; never a statement of fault
    entities: list[EntityRef]
    occurred_at: datetime | None = None
    summary: str | None = None
    url: str | None = None
    state: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw_ref: dict[str, Any] = field(default_factory=dict)
    rules_version: str = ""
    classifier_confidence: float | None = None
    degraded: bool = False

    @property
    def effective_time(self) -> datetime:
        return self.occurred_at or self.reported_at


def parse_date(value: Any) -> datetime | None:
    """Parse the date formats used by the sources into an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f", "%d-%b-%Y"):
        try:
            return datetime.strptime(text[:26] if "T" in text else text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def clamp_severity(value: int) -> int:
    return max(1, min(4, int(value)))
