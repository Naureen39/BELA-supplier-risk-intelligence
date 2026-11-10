"""End-to-end event pipeline over in-memory state.

normalize -> link -> dedup -> roll up to suppliers -> score -> alerts. The same functions back the
scheduled tasks; the SQL persistence layer (`store.py`) mirrors this state in PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.events.attach import AttachResult, EventEntityLink, attach_regulator_event
from app.events.classifier import LlmEventClassifier, build_news_event, classify_with_fallback
from app.events.dedup import (
    DEFAULT_DEDUP,
    DedupConfig,
    EventCluster,
    cluster_events,
    representative,
)
from app.events.monitor import (
    AlertDraft,
    AlertRule,
    EventFacts,
    SupplierFacts,
    draft_alerts,
)
from app.events.risk import (
    DEFAULT_RISK_CONFIG,
    RiskConfig,
    ScoredEvent,
    SupplierScore,
    score_supplier,
)
from app.events.schema import NEWS, REGULATOR, NormalizedEvent
from app.resolution.models import Route
from app.resolution.news import NewsLinker
from app.resolution.rollup import CorporateGraph
from app.resolution.structured import Resolver


@dataclass(frozen=True)
class Supplier:
    id: str
    company_id: int | None  # None while unresolved
    tier: str | None = None


@dataclass
class PipelineState:
    events: list[NormalizedEvent] = field(default_factory=list)
    links: list[EventEntityLink] = field(default_factory=list)
    scores: dict[str, SupplierScore] = field(default_factory=dict)
    raised: set[tuple[str, str, int | None]] = field(default_factory=set)

    def event_index(self) -> dict[tuple[str, str], int]:
        return {(e.source, e.source_id): i for i, e in enumerate(self.events)}


class EventPipeline:
    def __init__(
        self, resolver: Resolver, graph: CorporateGraph, risk_cfg: RiskConfig = DEFAULT_RISK_CONFIG,
        linker: NewsLinker | None = None, classifier: LlmEventClassifier | None = None,
        dedup_cfg: DedupConfig = DEFAULT_DEDUP, alert_rules: Sequence[AlertRule] = (),
    ) -> None:
        self.resolver, self.graph, self.risk_cfg = resolver, graph, risk_cfg
        self.linker, self.classifier = linker, classifier
        self.dedup_cfg, self.alert_rules = dedup_cfg, list(alert_rules)
        self.state = PipelineState()

    # ------------------------------------------------------------------ ingest
    def ingest_regulator(self, events: Sequence[NormalizedEvent]) -> int:
        """Idempotent: events already seen (source, source_id) are skipped."""
        known = self.state.event_index()
        added = 0
        for ev in events:
            if (ev.source, ev.source_id) in known:
                continue
            known[(ev.source, ev.source_id)] = len(self.state.events)
            self.state.events.append(ev)
            self.state.links.extend(attach_regulator_event(ev, self.resolver))
            added += 1
        return added

    def ingest_article(self, article_id: str, url: str, title: str, published_at: datetime,
                       text: str, lang: str = "en") -> int:
        """Link company mentions, label each evidence sentence, and create news events."""
        if self.linker is None:
            raise RuntimeError("no news linker configured")
        known = self.state.event_index()
        added = 0
        for link in self.linker.link_article(article_id, text, lang):
            if link.route is Route.NIL:
                continue
            cls = classify_with_fallback(self.classifier, link.mention.sentence)
            ev = build_news_event(cls, link.mention.sentence, link.mention.surface, url, title,
                                  published_at)
            if ev is None:
                continue
            key = (ev.source, ev.source_id)
            if key in known:
                continue
            known[key] = len(self.state.events)
            self.state.events.append(ev)
            self.state.links.append(EventEntityLink(
                key, link.mention.surface, "mentioned", link.company_id, link.method,
                link.probability, link.route, [(c.company_id, c.probability) for c in link.candidates],
                link.degraded or cls.degraded))
            added += 1
        return added

    # ------------------------------------------------------------------ views
    def attach_result(self) -> AttachResult:
        return AttachResult(self.state.links)

    def clusters(self) -> list[EventCluster]:
        attach = self.attach_result()
        keys = [frozenset(attach.visible_company_ids((e.source, e.source_id)))
                for e in self.state.events]
        return cluster_events(self.state.events, keys, self.dedup_cfg)

    def scored_events_for(self, supplier: Supplier) -> list[ScoredEvent]:
        """Cluster-level events that reach a supplier, with relation and path.

        `event_id` is the index of the cluster's representative event in `state.events`.
        """
        if supplier.company_id is None:
            return []
        out: list[ScoredEvent] = []
        for cluster in self.clusters():
            rep_index = representative(self.state.events, cluster)
            rep = self.state.events[rep_index]
            # Best link confidence per company across the cluster's visible links.
            conf: dict[int, float] = {}
            for i in cluster.members:
                ev = self.state.events[i]
                for link in self.state.links:
                    if (link.event_key == (ev.source, ev.source_id) and link.company_id is not None
                            and link.route in (Route.ACCEPTED, Route.EXACT_ID)):
                        conf[link.company_id] = max(conf.get(link.company_id, 0.0), link.score)
            is_reg = any(self.state.events[i].source_class == REGULATOR for i in cluster.members)
            severity = rep.severity
            for company_id, c in conf.items():
                for p in self.graph.reach(company_id, [supplier.company_id], self.risk_cfg.max_depth):
                    out.append(ScoredEvent(
                        event_id=rep_index, category=rep.event_type, severity=severity,
                        source_class=REGULATOR if is_reg else NEWS, time=rep.effective_time,
                        link_confidence=c, relation=p.relation, depth=p.depth, path=p.path))
        return out

    # ------------------------------------------------------------------ scoring and alerts
    def recompute(self, suppliers: Sequence[Supplier], now: datetime) -> list[AlertDraft]:
        """Rescore suppliers and return new alerts (threshold crossings and severe events)."""
        drafts: list[AlertDraft] = []
        for sup in suppliers:
            scored = self.scored_events_for(sup)
            current = score_supplier(scored, now, self.risk_cfg)
            previous = self.state.scores.get(sup.id)
            prev_ids = {c.event_id for c in previous.components} if previous else set()
            new_facts = []
            for c in current.components:
                if c.event_id in prev_ids:
                    continue
                rep = self.state.events[c.event_id]  # event_id is the representative's index
                new_facts.append(EventFacts(c.event_id, rep.event_type, rep.severity, rep.state))
            for d in draft_alerts(SupplierFacts(sup.id, sup.tier), previous, current, new_facts,
                                  self.alert_rules, self.state.raised):
                self.state.raised.add(d.dedup_key)
                drafts.append(d)
            self.state.scores[sup.id] = current
        return drafts
