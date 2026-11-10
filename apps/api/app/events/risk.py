"""Risk scoring.

    event_impact  = severity_weight * recency_decay * link_confidence * relation_weight
                    * source_reliability
    supplier_risk = 100 * (1 - product over events of (1 - min(event_impact, cap)))

Every factor of every event is returned so the UI can show the full breakdown. The configuration is
versioned; tenant admins may change values only inside `BOUNDS`.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any

from app.resolution.rollup import (
    DIRECT,
    PARENT_TO_SUBSIDIARY,
    SIBLING,
    SUBSIDIARY_TO_PARENT,
)

LEVELS: tuple[str, ...] = ("low", "medium", "high", "critical")


@dataclass(frozen=True)
class RiskConfig:
    version: str = "risk_config_v1"
    severity_weights: tuple[float, float, float, float] = (0.10, 0.25, 0.45, 0.60)
    half_life_regulator_days: float = 180.0
    half_life_news_days: float = 30.0
    relation_weights: dict[str, float] = field(default_factory=lambda: {
        DIRECT: 1.0, SUBSIDIARY_TO_PARENT: 0.7, PARENT_TO_SUBSIDIARY: 0.5, SIBLING: 0.2})
    max_depth: int = 2
    source_reliability: dict[str, float] = field(
        default_factory=lambda: {"regulator": 1.0, "news": 0.7})
    impact_cap: float = 0.6
    level_thresholds: tuple[float, float, float] = (30.0, 50.0, 70.0)  # medium, high, critical

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


# Inclusive bounds for tenant-editable values (plan: "editable within bounds").
BOUNDS: dict[str, tuple[float, float]] = {
    "severity_weight": (0.0, 0.9),
    "half_life_days": (7.0, 730.0),
    "relation_weight": (0.0, 1.0),
    "source_reliability": (0.1, 1.0),
    "impact_cap": (0.3, 0.9),
}


class ConfigError(ValueError):
    pass


def validate_config(cfg: RiskConfig) -> RiskConfig:
    """Raise ConfigError unless every value is inside its bounds and ordering is sensible."""
    lo, hi = BOUNDS["severity_weight"]
    if any(not lo <= w <= hi for w in cfg.severity_weights):
        raise ConfigError("severity weight out of bounds")
    if list(cfg.severity_weights) != sorted(cfg.severity_weights):
        raise ConfigError("severity weights must not decrease with severity")
    for h in (cfg.half_life_regulator_days, cfg.half_life_news_days):
        if not BOUNDS["half_life_days"][0] <= h <= BOUNDS["half_life_days"][1]:
            raise ConfigError("half-life out of bounds")
    if any(not BOUNDS["relation_weight"][0] <= w <= BOUNDS["relation_weight"][1]
           for w in cfg.relation_weights.values()):
        raise ConfigError("relation weight out of bounds")
    if cfg.relation_weights.get(DIRECT, 0) < max(
        (w for k, w in cfg.relation_weights.items() if k != DIRECT), default=0
    ):
        raise ConfigError("direct relation must not weigh less than an indirect relation")
    if any(not BOUNDS["source_reliability"][0] <= w <= BOUNDS["source_reliability"][1]
           for w in cfg.source_reliability.values()):
        raise ConfigError("source reliability out of bounds")
    if not BOUNDS["impact_cap"][0] <= cfg.impact_cap <= BOUNDS["impact_cap"][1]:
        raise ConfigError("impact cap out of bounds")
    if list(cfg.level_thresholds) != sorted(cfg.level_thresholds):
        raise ConfigError("level thresholds must ascend")
    return cfg


def next_version(cfg: RiskConfig, **changes: Any) -> RiskConfig:
    """A validated edited copy with an incremented version suffix (history kept by the caller)."""
    base, _, n = cfg.version.rpartition("_v")
    new = replace(cfg, version=f"{base}_v{int(n) + 1}" if n.isdigit() else f"{cfg.version}_edit",
                  **changes)
    return validate_config(new)


@dataclass(frozen=True)
class ScoredEvent:
    """Event as seen by one supplier (after dedup, link, and roll-up)."""

    event_id: int
    category: str
    severity: int
    source_class: str  # regulator or news
    time: datetime  # occurred_at or reported_at
    link_confidence: float
    relation: str
    depth: int = 0
    path: tuple[int, ...] = ()


@dataclass(frozen=True)
class Component:
    event_id: int
    category: str
    severity_weight: float
    recency_decay: float
    link_confidence: float
    relation_weight: float
    source_reliability: float
    event_impact: float
    capped_impact: float
    relation: str
    path: tuple[int, ...]


@dataclass(frozen=True)
class SupplierScore:
    score: float
    level: str
    config_version: str
    components: tuple[Component, ...]
    category_scores: dict[str, float]


DEFAULT_RISK_CONFIG = RiskConfig()


def recency_decay(age_days: float, half_life_days: float) -> float:
    return float(0.5 ** (max(age_days, 0.0) / half_life_days))


def level_for(score: float, cfg: RiskConfig) -> str:
    medium, high, critical = cfg.level_thresholds
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def event_component(ev: ScoredEvent, now: datetime, cfg: RiskConfig) -> Component | None:
    """Impact factors for one event. Returns None when the relation is unknown or too deep."""
    rel_weight = cfg.relation_weights.get(ev.relation)
    if rel_weight is None or ev.depth > cfg.max_depth:
        return None
    half_life = (cfg.half_life_regulator_days if ev.source_class == "regulator"
                 else cfg.half_life_news_days)
    age = (now - ev.time).total_seconds() / 86400
    sev_w = cfg.severity_weights[max(1, min(4, ev.severity)) - 1]
    decay = recency_decay(age, half_life)
    reliability = cfg.source_reliability.get(ev.source_class, 0.5)
    conf = max(0.0, min(1.0, ev.link_confidence))
    impact = sev_w * decay * conf * rel_weight * reliability
    return Component(ev.event_id, ev.category, sev_w, decay, conf, rel_weight, reliability, impact,
                     min(impact, cfg.impact_cap), ev.relation, ev.path)


def _combine(capped: Iterable[float]) -> float:
    product = 1.0
    for c in capped:
        product *= 1.0 - c
    return 100.0 * (1.0 - product)


def score_supplier(
    events: Sequence[ScoredEvent], now: datetime, cfg: RiskConfig = DEFAULT_RISK_CONFIG
) -> SupplierScore:
    """Score a supplier. One event reaching the supplier by several paths counts once, by the
    path with the highest impact."""
    best: dict[int, Component] = {}
    for ev in events:
        comp = event_component(ev, now, cfg)
        if comp is None:
            continue
        current = best.get(ev.event_id)
        if current is None or comp.capped_impact > current.capped_impact:
            best[ev.event_id] = comp
    comps = tuple(sorted(best.values(), key=lambda c: (-c.capped_impact, c.event_id)))
    by_cat: dict[str, list[float]] = defaultdict(list)
    for c in comps:
        by_cat[c.category].append(c.capped_impact)
    score = round(_combine(c.capped_impact for c in comps), 2)
    return SupplierScore(
        score=score, level=level_for(score, cfg), config_version=cfg.version, components=comps,
        category_scores={k: round(_combine(v), 2) for k, v in sorted(by_cat.items())})


def is_finite_score(s: SupplierScore) -> bool:
    return math.isfinite(s.score) and 0.0 <= s.score <= 100.0
