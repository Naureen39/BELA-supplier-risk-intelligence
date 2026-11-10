"""HTTP clients and protocols for the nel, blink, and llm services.

Every client raises `ServiceUnavailable` on transport errors, timeouts, or error statuses so the
pipeline can degrade (retrieval and Splink scoring only, ambiguous cases to human review).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.resolution.models import Mention


class ServiceUnavailable(RuntimeError):
    """A model service did not return a usable answer."""


@dataclass(frozen=True)
class RetrievedCandidate:
    company_id: int
    score: float  # similarity in 0..1 (bi-encoder cosine mapped to 0..1)


@dataclass(frozen=True)
class MentionInput:
    id: str
    text: str
    lang: str = "en"


class NelBackend(Protocol):
    def link(self, items: Sequence[MentionInput]) -> list[list[Mention]]: ...


class BlinkBackend(Protocol):
    def retrieve(self, mention: str, context: str, k: int) -> list[RetrievedCandidate]: ...

    def rerank(
        self, mention: str, context: str, candidate_ids: Sequence[int]
    ) -> dict[int, float]: ...


class _Http:
    def __init__(self, base_url: str, timeout: float, client: httpx.Client | None) -> None:
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceUnavailable(f"{path}: {exc}") from exc


class NelClient(_Http):
    def __init__(
        self, base_url: str, timeout: float = 30.0, client: httpx.Client | None = None
    ) -> None:
        super().__init__(base_url, timeout, client)

    def link(self, items: Sequence[MentionInput]) -> list[list[Mention]]:
        data = self.post(
            "/v1/link", {"items": [{"id": i.id, "text": i.text, "lang": i.lang} for i in items]}
        )
        out: list[list[Mention]] = []
        by_id = {r["id"]: r["mentions"] for r in data["results"]}
        for item in items:
            mentions = []
            for m in by_id.get(item.id, []):
                mentions.append(
                    Mention(
                        article_id=item.id, start=m["start"], end=m["end"], surface=m["surface"],
                        sentence=_sentence_around(item.text, m["start"], m["end"]),
                        qid=m.get("qid"), md_score=m["md_score"], el_score=m["el_score"],
                        bela_candidates=tuple((c["qid"], c["score"]) for c in m.get("candidates", [])),
                    )
                )
            out.append(mentions)
        return out


class BlinkClient(_Http):
    def __init__(
        self, base_url: str, timeout: float = 30.0, client: httpx.Client | None = None
    ) -> None:
        super().__init__(base_url, timeout, client)

    def retrieve(self, mention: str, context: str, k: int) -> list[RetrievedCandidate]:
        data = self.post("/v1/retrieve", {"mention": mention, "context": context, "k": k})
        return [RetrievedCandidate(c["company_id"], c["score"]) for c in data["candidates"]]

    def rerank(self, mention: str, context: str, candidate_ids: Sequence[int]) -> dict[int, float]:
        data = self.post(
            "/v1/rerank",
            {"mention": mention, "context": context, "candidate_ids": list(candidate_ids)},
        )
        return {int(s["company_id"]): float(s["score"]) for s in data["scores"]}


def _sentence_around(text: str, start: int, end: int, window: int = 300) -> str:
    """Sentence-like context around a span, bounded to `window` characters per side."""
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    left = 0 if left < 0 else left + 1
    right_candidates = [i for i in (text.find(". ", end), text.find("\n", end)) if i >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    left = max(left, start - window)
    right = min(right, end + window)
    return text[left:right].strip()
