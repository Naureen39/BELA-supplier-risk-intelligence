from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from app.events.monitor import AlertRule, EventFacts, SupplierFacts, crossed_threshold, draft_alerts
from app.events.risk import (
    ConfigError,
    RiskConfig,
    ScoredEvent,
    event_component,
    level_for,
    next_version,
    recency_decay,
    score_supplier,
    validate_config,
)
from app.resolution.rollup import DIRECT, PARENT_TO_SUBSIDIARY, SIBLING, SUBSIDIARY_TO_PARENT

NOW = datetime(2026, 1, 1, tzinfo=UTC)
CFG = RiskConfig()


def ev(i: int, sev: int = 3, days: float = 0, cls: str = "regulator", conf: float = 1.0,
       rel: str = DIRECT, depth: int = 0, cat: str = "workplace_safety") -> ScoredEvent:
    return ScoredEvent(i, cat, sev, cls, NOW - timedelta(days=days), conf, rel, depth)


def test_formula_matches_hand_calculation() -> None:
    c = event_component(ev(1, sev=3, days=180, conf=0.9, rel=SUBSIDIARY_TO_PARENT, depth=1), NOW, CFG)
    assert c is not None
    assert math.isclose(c.event_impact, 0.45 * 0.5 * 0.9 * 0.7 * 1.0)
    news = event_component(ev(2, sev=2, days=30, cls="news"), NOW, CFG)
    assert news is not None and math.isclose(news.event_impact, 0.25 * 0.5 * 1.0 * 1.0 * 0.7)


def test_supplier_score_combines_with_cap() -> None:
    s = score_supplier([ev(1, sev=4), ev(2, sev=4, cls="news")], NOW, CFG)
    # impacts 0.6 and 0.42 -> 100 * (1 - 0.4 * 0.58)
    assert math.isclose(s.score, round(100 * (1 - 0.4 * 0.58), 2)) and s.level == "critical"
    assert 0 <= score_supplier([], NOW, CFG).score == 0
    capped = RiskConfig(severity_weights=(0.1, 0.25, 0.45, 0.9), impact_cap=0.6)
    assert score_supplier([ev(1, sev=4)], NOW, capped).score == 60.0


def test_levels_boundaries() -> None:
    assert [level_for(x, CFG) for x in (0, 29.99, 30, 49.99, 50, 69.99, 70, 100)] == [
        "low", "low", "medium", "medium", "high", "high", "critical", "critical"]


def test_relation_weights_and_depth_limit() -> None:
    rels = {DIRECT: 1.0, SUBSIDIARY_TO_PARENT: 0.7, PARENT_TO_SUBSIDIARY: 0.5, SIBLING: 0.2}
    for rel, w in rels.items():
        c = event_component(ev(1, rel=rel, depth=1), NOW, CFG)
        assert c is not None and c.relation_weight == w
    assert event_component(ev(1, rel=SIBLING, depth=3), NOW, CFG) is None
    assert event_component(ev(1, rel="unknown"), NOW, CFG) is None


def test_same_event_by_two_paths_counts_once() -> None:
    s = score_supplier([ev(1, rel=DIRECT), ev(1, rel=SIBLING, depth=2)], NOW, CFG)
    assert len(s.components) == 1 and s.components[0].relation == DIRECT


def test_score_is_monotone_in_events_and_decays_with_time() -> None:
    one = score_supplier([ev(1)], NOW, CFG).score
    two = score_supplier([ev(1), ev(2)], NOW, CFG).score
    old = score_supplier([ev(1, days=720)], NOW, CFG).score
    assert two > one > old >= 0
    assert recency_decay(-5, 30) == 1.0


def test_category_subscores() -> None:
    s = score_supplier([ev(1, cat="workplace_safety"), ev(2, cat="environmental", sev=2)], NOW, CFG)
    assert set(s.category_scores) == {"workplace_safety", "environmental"}
    assert s.category_scores["workplace_safety"] > s.category_scores["environmental"]


def test_config_bounds_and_versioning() -> None:
    with pytest.raises(ConfigError):
        validate_config(RiskConfig(impact_cap=0.99))
    with pytest.raises(ConfigError):
        validate_config(RiskConfig(severity_weights=(0.5, 0.2, 0.45, 0.6)))
    with pytest.raises(ConfigError):
        validate_config(RiskConfig(half_life_news_days=1))
    new = next_version(CFG, impact_cap=0.5)
    assert new.version == "risk_config_v2" and new.impact_cap == 0.5


def test_alert_dedup_and_crossing() -> None:
    low = score_supplier([ev(1, sev=1)], NOW, CFG)
    high = score_supplier([ev(1, sev=4), ev(2, sev=4, cls="news")], NOW, CFG)
    assert crossed_threshold("low", "high") and not crossed_threshold("high", "critical")
    sup = SupplierFacts("s1", "tier1")
    facts = [EventFacts(2, "workplace_safety", 4, "OH")]
    first = draft_alerts(sup, low, high, facts, [])
    kinds = sorted(d.kind for d in first)
    assert kinds == ["high_severity_event", "threshold_crossing"]
    again = draft_alerts(sup, low, high, facts, [], existing={d.dedup_key for d in first})
    assert again == []
    quiet = draft_alerts(sup, low, low, [EventFacts(3, "other", 2, "OH")], [])
    assert quiet == []


def test_rule_filters() -> None:
    rule = AlertRule("r1", frozenset({"environmental"}), 2, frozenset({"tier1"}), frozenset({"PA"}))
    sup = SupplierFacts("s", "tier1")
    s = score_supplier([], NOW, CFG)
    hit = draft_alerts(sup, s, s, [EventFacts(1, "environmental", 2, "PA")], [rule])
    assert hit and hit[0].rule_id == "r1"
    assert draft_alerts(sup, s, s, [EventFacts(2, "environmental", 2, "OH")], [rule]) == []
    assert draft_alerts(SupplierFacts("s", "tier3"), s, s, [EventFacts(3, "environmental", 2, "PA")], [rule]) == []
