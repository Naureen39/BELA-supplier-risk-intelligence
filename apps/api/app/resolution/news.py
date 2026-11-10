"""News linking pipeline (problem B).

Steps: chunk, pre-filter by event topic, BELA detection and linking, map QIDs to canonical
companies, BLINK retrieve and re-rank for unlinked or non-company mentions, local LLM adjudication
for ambiguous cases, per-route calibration, and storage of every candidate considered.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.kb.normalize import normalize_name
from app.resolution.catalog import Catalog
from app.resolution.clients import (
    BlinkBackend,
    MentionInput,
    NelBackend,
    ServiceUnavailable,
)
from app.resolution.config import DEFAULT_CONFIG, ResolutionConfig
from app.resolution.llm import CandidateText, LlmAdjudicator
from app.resolution.models import Mention, MentionLink, Route, ScoredCandidate
from app.resolution.scoring import Calibrator

# --------------------------------------------------------------------- chunking

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_ABBREV = re.compile(r"\b(?:Inc|Corp|Co|Ltd|Mr|Mrs|Ms|Dr|St|No|U\.S|vs|Jr|Sr)\.$")


def split_sentences(text: str) -> list[str]:
    """Sentence splitter that keeps common abbreviations (Inc., Corp.) inside a sentence."""
    parts = _SENTENCE_END.split(text.strip())
    sentences: list[str] = []
    for part in parts:
        if sentences and _ABBREV.search(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {part}"
        elif part:
            sentences.append(part)
    return sentences


@dataclass(frozen=True)
class Chunk:
    text: str
    offset: int  # character offset of the chunk in the source text


def chunk_text(text: str, max_chars: int = 1800, overlap_sentences: int = 1) -> list[Chunk]:
    """Chunk at sentence boundaries with sentence overlap. Offsets index into `text`."""
    sentences: list[tuple[str, int]] = []
    cursor = 0
    for sent in split_sentences(text):
        start = text.find(sent, cursor)
        start = cursor if start < 0 else start
        sentences.append((sent, start))
        cursor = start + len(sent)
    chunks: list[Chunk] = []
    i = 0
    while i < len(sentences):
        j, size = i, 0
        while j < len(sentences) and (size == 0 or size + len(sentences[j][0]) + 1 <= max_chars):
            size += len(sentences[j][0]) + 1
            j += 1
        first = sentences[i][1]
        last_text, last_start = sentences[j - 1]
        chunks.append(Chunk(text[first : last_start + len(last_text)], first))
        if j >= len(sentences):
            break
        i = max(j - overlap_sentences, i + 1)
    return chunks


# --------------------------------------------------------------------- topic pre-filter

EVENT_KEYWORDS: tuple[str, ...] = (
    "recall", "fire", "explosion", "blast", "spill", "leak", "strike", "walkout", "bankruptcy",
    "chapter 11", "insolvency", "data breach", "ransomware", "cyberattack", "lawsuit", "sued",
    "settlement", "fine", "penalty", "violation", "citation", "investigation", "shutdown",
    "plant closure", "closing", "layoff", "shortage", "contamination", "injur", "fatal",
    "indict", "fraud", "sanction", "default", "downgrade", "evacuat", "emissions",
)


class EventTopicFilter:
    """Keyword rules, optionally combined with prototype similarity from an embedder."""

    def __init__(self, min_hits: int = 1) -> None:
        self.min_hits = min_hits

    def score(self, text: str) -> int:
        lowered = text.casefold()
        return sum(1 for kw in EVENT_KEYWORDS if kw in lowered)

    def keep(self, text: str) -> bool:
        return self.score(text) >= self.min_hits


# --------------------------------------------------------------------- type filter

_STOP_SURFACES = frozenset(
    {"the", "company", "firm", "officials", "regulators", "state", "city", "county", "monday",
     "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "it", "they"}
)


def plausible_organization_surface(surface: str) -> bool:
    """Cheap type filter: reject empty, generic, purely numeric, or all-lowercase surfaces."""
    text = surface.strip()
    if len(text) < 2 or text.casefold() in _STOP_SURFACES:
        return False
    if text.isdigit() or not any(ch.isalpha() for ch in text):
        return False
    return not text.islower()


# --------------------------------------------------------------------- linker


@dataclass
class NewsLinker:
    catalog: Catalog
    nel: NelBackend
    blink: BlinkBackend | None = None
    llm: LlmAdjudicator | None = None
    cfg: ResolutionConfig = DEFAULT_CONFIG
    calibrators: dict[str, Calibrator] = field(default_factory=dict)  # keyed by route name
    topic_filter: EventTopicFilter = field(default_factory=EventTopicFilter)
    model_versions: dict[str, str] = field(default_factory=dict)

    def _cal(self, route: str, p: float) -> float:
        cal = self.calibrators.get(route)
        return cal.apply(p) if cal else p

    # ------------------------------------------------------------------ article level
    def link_article(self, article_id: str, text: str, lang: str = "en") -> list[MentionLink]:
        """Chunk, pre-filter, detect, and link. Returns one MentionLink per detected mention."""
        chunks = [c for c in chunk_text(text, self.cfg.chunk_max_chars,
                                        self.cfg.chunk_overlap_sentences)
                  if self.topic_filter.keep(c.text)]
        if not chunks:
            return []
        per_chunk = self.nel.link(
            [MentionInput(f"{article_id}:{i}", c.text, lang) for i, c in enumerate(chunks)]
        )
        links: list[MentionLink] = []
        seen_spans: set[tuple[int, int]] = set()
        for chunk, mentions in zip(chunks, per_chunk, strict=True):
            for m in mentions:
                span = (chunk.offset + m.start, chunk.offset + m.end)
                if span in seen_spans:  # overlap region produced a duplicate
                    continue
                seen_spans.add(span)
                shifted = Mention(article_id, span[0], span[1], m.surface, m.sentence, m.qid,
                                  m.md_score, m.el_score, m.bela_candidates)
                links.append(self.link_mention(shifted))
        return links

    # ------------------------------------------------------------------ mention level
    def _mk(
        self, m: Mention, company_id: int | None, route: Route, method: str, probability: float,
        candidates: list[ScoredCandidate], **extra: Any,
    ) -> MentionLink:
        return MentionLink(
            m, company_id, route, method, probability, candidates,
            config_version=self.cfg.version, model_versions=dict(self.model_versions), **extra,
        )

    def link_mention(self, m: Mention) -> MentionLink:
        if not plausible_organization_surface(m.surface):
            return self._mk(m, None, Route.NIL, "type_filter", 0.0, [])

        # 1. BELA link that maps to a canonical company.
        company_id = self.catalog.by_qid.get(m.qid) if m.qid else None
        if company_id is not None and m.el_score >= self.cfg.bela_trust_el_score:
            p = self._cal("bela", m.el_score)
            cand = ScoredCandidate(company_id, self.catalog.by_id[company_id].name, {"bela"},
                                   m.el_score, probability=p, raw_probability=m.el_score)
            route = Route.ACCEPTED if p >= self.cfg.news_accept_threshold else Route.REVIEW
            return self._mk(m, company_id, route, "bela", p, [cand])

        # 2. Fallback: BLINK retrieve and re-rank over the company catalog.
        return self._fallback(m)

    def _fallback(self, m: Mention) -> MentionLink:
        degraded = False
        candidates: list[ScoredCandidate] = []
        if self.blink is not None:
            try:
                retrieved = self.blink.retrieve(m.surface, m.sentence, self.cfg.blink_k)
                ids = [c.company_id for c in retrieved]
                scores = self.blink.rerank(m.surface, m.sentence, ids) if ids else {}
                bi = {c.company_id: c.score for c in retrieved}
                for cid in ids:
                    cross = scores.get(cid, 0.0)
                    candidates.append(
                        ScoredCandidate(cid, self.catalog.by_id[cid].name, {"blink"}, bi[cid],
                                        blink_score=cross, raw_probability=cross, probability=cross)
                    )
            except ServiceUnavailable:
                degraded = True
        else:
            degraded = True
        if degraded:  # exact normalized name is the only evidence left
            for cid in self.catalog.exact_name(m.surface)[: self.cfg.llm_candidates]:
                candidates.append(
                    ScoredCandidate(cid, self.catalog.by_id[cid].name, {"exact_name"}, 1.0,
                                    raw_probability=0.55, probability=0.55)
                )
        candidates.sort(key=lambda c: (-c.probability, c.company_id))
        candidates = candidates[: self.cfg.candidates_kept]
        if not candidates:
            return self._mk(m, None, Route.NIL, "no_candidates", 0.0, [], degraded=degraded)

        top = candidates[0]
        runner = candidates[1].probability if len(candidates) > 1 else 0.0
        confident = top.probability >= self.cfg.blink_confident and (
            top.probability - runner >= self.cfg.min_margin
        )
        if confident and not degraded:
            p = self._cal("blink", top.probability)
            route = Route.ACCEPTED if p >= self.cfg.news_accept_threshold else Route.REVIEW
            return self._mk(m, top.company_id, route, "blink", p, candidates)
        if top.probability < self.cfg.news_review_threshold * 0.5:
            return self._mk(m, None, Route.NIL, "blink_low", top.probability, candidates,
                               degraded=degraded)
        return self._adjudicate(m, candidates, degraded)

    def _adjudicate(
        self, m: Mention, candidates: list[ScoredCandidate], degraded: bool
    ) -> MentionLink:
        top = candidates[0]
        if self.llm is None or degraded:
            # Without the LLM, ambiguous cases go to human review and are flagged.
            return self._mk(m, top.company_id, Route.REVIEW, "retrieval_only", top.probability,
                               candidates, degraded=True)
        shortlist = candidates[: self.cfg.llm_candidates]
        texts = [
            CandidateText(c.company_id, self.catalog.blink_entity_text(self.catalog.by_id[c.company_id]))
            for c in shortlist
        ]
        try:
            chosen, out = self.llm.choose(m.surface, m.sentence, texts)
        except ServiceUnavailable:
            return self._mk(m, top.company_id, Route.REVIEW, "retrieval_only", top.probability,
                               candidates, degraded=True)
        label = f"choice={out.choice};confidence={out.confidence:.2f}"
        if chosen is None:
            return self._mk(m, None, Route.NIL, "llm_none", 1.0 - out.confidence, candidates,
                               llm_label=label, llm_confidence=out.confidence)
        chosen_score = next(c.probability for c in shortlist if c.company_id == chosen)
        agree = chosen == top.company_id
        # The LLM is one input to the score, never the sole decision (plan section 10).
        raw = 0.5 * chosen_score + 0.5 * out.confidence if agree else 0.4 * out.confidence + 0.2 * chosen_score
        p = self._cal("llm", raw)
        route = Route.ACCEPTED if (agree and p >= self.cfg.news_accept_threshold) else (
            Route.REVIEW if p >= self.cfg.news_review_threshold else Route.NIL
        )
        return self._mk(m, chosen if route is not Route.NIL else None, route, "llm", p,
                           candidates, llm_label=label, llm_confidence=out.confidence)


def mention_norm(surface: str) -> str:
    return normalize_name(surface)


def links_to_rows(links: Sequence[MentionLink]) -> list[dict[str, object]]:
    """Flatten links for persistence or evaluation output."""
    rows: list[dict[str, object]] = []
    for link in links:
        rows.append(
            {
                "article_id": link.mention.article_id, "start": link.mention.start,
                "end": link.mention.end, "surface": link.mention.surface,
                "company_id": link.company_id, "route": link.route.value, "method": link.method,
                "probability": link.probability, "degraded": link.degraded,
                "candidates": [(c.company_id, c.probability) for c in link.candidates],
            }
        )
    return rows
