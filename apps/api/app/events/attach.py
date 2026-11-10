"""Attach events to canonical companies with the resolution pipeline.

Regulator events that resolve with low confidence (review or nil) are held for the platform review
queue and are not visible in tenant views. News events use the news linker's decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.events.schema import NormalizedEvent
from app.resolution.models import QueryRecord, Resolution, Route
from app.resolution.structured import Resolver


@dataclass
class EventEntityLink:
    event_key: tuple[str, str]  # (source, source_id)
    entity_name: str
    role: str
    company_id: int | None
    method: str
    score: float
    route: Route
    candidates: list[tuple[int, float]] = field(default_factory=list)
    degraded: bool = False


@dataclass
class AttachResult:
    links: list[EventEntityLink]

    def visible_company_ids(self, event_key: tuple[str, str]) -> set[int]:
        """Companies a tenant may see for an event: accepted or exact identifier matches only."""
        return {
            link.company_id for link in self.links
            if link.event_key == event_key and link.company_id is not None
            and link.route in (Route.ACCEPTED, Route.EXACT_ID)
        }

    def platform_review_queue(self) -> list[EventEntityLink]:
        return [link for link in self.links if link.route in (Route.REVIEW, Route.NIL)]


def attach_regulator_event(event: NormalizedEvent, resolver: Resolver) -> list[EventEntityLink]:
    out = []
    for i, ent in enumerate(event.entities):
        record = QueryRecord(
            id=f"{event.source}:{event.source_id}:{i}", name=ent.name, state=ent.state or event.state,
            city=ent.city or event.city, country=ent.country,
            cik=int(ent.identifiers["cik"]) if "cik" in ent.identifiers else None,
            lei=ent.identifiers.get("lei"), ticker=ent.identifiers.get("ticker"),
            website=ent.identifiers.get("website"))
        res: Resolution = resolver.resolve(record)
        out.append(EventEntityLink(
            (event.source, event.source_id), ent.name, ent.role, res.company_id, res.method,
            res.probability, res.route,
            [(c.company_id, c.probability) for c in res.candidates], res.degraded))
    return out


def attach_events(events: list[NormalizedEvent], resolver: Resolver) -> AttachResult:
    links: list[EventEntityLink] = []
    for ev in events:
        links.extend(attach_regulator_event(ev, resolver))
    return AttachResult(links)
