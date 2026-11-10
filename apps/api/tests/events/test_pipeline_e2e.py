"""Phase 4 exit test: fixtures in, events attached (with parent roll-up), score changes, alerts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.events.monitor import AlertRule
from app.events.normalizers import osha
from app.events.pipeline import EventPipeline, Supplier
from app.events.rules import load_rules
from app.resolution.clients import MentionInput
from app.resolution.models import Mention, Route
from app.resolution.news import NewsLinker
from app.resolution.rollup import SUBSIDIARY_TO_PARENT, CorporateGraph
from app.resolution.structured import Resolver
from resolution_fixtures import catalog

NOW = datetime(2025, 9, 1, tzinfo=UTC)
RULES = load_rules()
ARTICLE = ("Workers were injured in an accident at the Harborline Foods plant in Columbus on Tuesday. "
           "The company said production would resume next week.")


class StubNel:
    def link(self, items: Sequence[MentionInput]) -> list[list[Mention]]:
        out = []
        for item in items:
            i = item.text.find("Harborline Foods")
            out.append([] if i < 0 else [Mention(item.id, i, i + 16, "Harborline Foods",
                                                item.text.split(". ")[0], "Q1001", 0.95, 0.95)])
        return out


def osha_row(activity: str, name: str, state: str, penalty: str, date: str) -> dict[str, str]:
    return {"activity_nr": activity, "estab_name": name, "site_state": state, "site_city": "X",
            "citation_id": "01", "viol_type": "S", "current_penalty": penalty, "issuance_date": date,
            "open_date": date}


def build() -> EventPipeline:
    cat = catalog()
    return EventPipeline(Resolver(cat), CorporateGraph(cat.edges), linker=NewsLinker(cat, StubNel()),
                         alert_rules=[AlertRule("r-severe", min_severity=3)])


SUPPLIERS = [Supplier("sup-parent", 3, "tier1"), Supplier("sup-harbor", 1, "tier2"),
             Supplier("sup-cobalt", 5, "tier3"), Supplier("sup-unresolved", None)]


def test_subsidiary_event_rolls_up_to_parent_supplier_and_alerts() -> None:
    p = build()
    assert p.recompute(SUPPLIERS, NOW) == []

    row = osha_row("9001", "Northgate Metals of Texas LLC", "TX", "90000", "2025-08-20")
    assert p.ingest_regulator(osha.normalize_row(row, RULES)) == 1
    alerts = p.recompute(SUPPLIERS, NOW)

    score = p.state.scores["sup-parent"]
    comp = score.components[0]
    assert score.score > 0 and comp.relation == SUBSIDIARY_TO_PARENT and comp.path == (4, 3)
    assert comp.relation_weight == 0.7 and comp.source_reliability == 1.0
    assert {a.supplier_id for a in alerts} == {"sup-parent"}
    assert {a.kind for a in alerts} == {"high_severity_event"}
    assert p.state.scores["sup-harbor"].score == 0 and p.state.scores["sup-unresolved"].score == 0

    # Idempotent reload, and no duplicate alert on a second recompute.
    assert p.ingest_regulator(osha.normalize_row(row, RULES)) == 0
    assert p.recompute(SUPPLIERS, NOW) == []


def test_low_confidence_regulator_record_goes_to_platform_review_not_tenants() -> None:
    p = build()
    row = osha_row("9002", "Cobalt Ridge Logistics Co", "", "50000", "2025-08-20")
    p.ingest_regulator(osha.normalize_row(row, RULES))
    p.recompute(SUPPLIERS, NOW)
    queue = p.attach_result().platform_review_queue()
    assert queue and all(link.route in (Route.REVIEW, Route.NIL) for link in queue)
    assert p.state.scores["sup-cobalt"].score == 0  # ambiguous twin names never silently attach


def test_news_event_changes_score_and_merges_with_regulator_record() -> None:
    p = build()
    p.ingest_regulator(osha.normalize_row(
        osha_row("9003", "Harborline Foods Inc", "OH", "40000", "2025-08-28"), RULES))
    p.recompute(SUPPLIERS, NOW)
    before = p.state.scores["sup-harbor"].score
    assert before > 0

    added = p.ingest_article("art-1", "https://news.example/a", "Accident at Harborline plant",
                             datetime(2025, 8, 30, tzinfo=UTC), ARTICLE)
    assert added == 1
    p.recompute(SUPPLIERS, NOW)
    after = p.state.scores["sup-harbor"]
    # Same incident (company, type, window): one cluster, counted once, regulator wins.
    assert len(p.clusters()) == 1 and len(after.components) == 1
    assert after.score == before and after.components[0].source_reliability == 1.0


def test_unmerged_news_event_raises_score_and_threshold_alert() -> None:
    p = build()
    p.ingest_article("art-2", "https://news.example/b", "Accident at Harborline plant",
                     datetime(2025, 8, 30, tzinfo=UTC), ARTICLE)
    alerts = p.recompute(SUPPLIERS, NOW)
    s = p.state.scores["sup-harbor"]
    assert s.score > 0 and s.components[0].source_reliability == 0.7
    assert s.components[0].link_confidence >= 0.9
    assert any(a.supplier_id == "sup-harbor" for a in alerts)
    # Later regulator evidence at a different time window adds to the score.
    p.ingest_regulator(osha.normalize_row(
        osha_row("9004", "Harborline Foods Inc", "OH", "160000", "2025-03-01"), RULES))
    p.recompute(SUPPLIERS, NOW)
    assert p.state.scores["sup-harbor"].score > s.score
