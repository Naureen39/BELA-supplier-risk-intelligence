"""Shared data types for the resolution engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Route(StrEnum):
    EXACT_ID = "exact_id"
    ACCEPTED = "accepted"
    REVIEW = "review"
    NIL = "nil"


@dataclass(frozen=True)
class QueryRecord:
    """A structured record or uploaded supplier row to resolve (problems A and C)."""

    id: str
    name: str
    state: str | None = None
    city: str | None = None
    country: str | None = None
    address: str | None = None
    website: str | None = None
    cik: int | None = None
    lei: str | None = None
    ticker: str | None = None
    industry_code: str | None = None
    context: str | None = None  # free text such as program or record description


@dataclass
class ScoredCandidate:
    company_id: int
    name: str
    sources: set[str] = field(default_factory=set)  # generators that proposed it
    retrieval_score: float = 0.0
    features: dict[str, float] = field(default_factory=dict)
    splink_weight: float = 0.0
    blink_score: float | None = None
    raw_probability: float = 0.0
    probability: float = 0.0  # calibrated


@dataclass
class Resolution:
    record_id: str
    company_id: int | None
    route: Route
    method: str
    probability: float
    margin: float
    candidates: list[ScoredCandidate]
    config_version: str
    degraded: bool = False  # a model service was unavailable; confidence is reduced
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Mention:
    """A company mention found in article text."""

    article_id: str
    start: int
    end: int
    surface: str
    sentence: str
    qid: str | None
    md_score: float
    el_score: float
    bela_candidates: tuple[tuple[str, float], ...] = ()


@dataclass
class MentionLink:
    mention: Mention
    company_id: int | None
    route: Route
    method: str
    probability: float
    candidates: list[ScoredCandidate]
    llm_label: str | None = None
    llm_confidence: float | None = None
    degraded: bool = False
    config_version: str = ""
    model_versions: dict[str, str] = field(default_factory=dict)
