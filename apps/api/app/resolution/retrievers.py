"""Candidate generators for structured resolution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np

from app.kb.embeddings import Embedder
from app.kb.normalize import state_code
from app.resolution.catalog import Catalog, iter_catalog_names
from app.resolution.clients import BlinkBackend
from app.resolution.config import ResolutionConfig
from app.resolution.models import QueryRecord


class Retriever(Protocol):
    name: str

    def retrieve(self, record: QueryRecord, k: int) -> list[tuple[int, float]]:
        """Return (company_id, score in 0..1), best first."""
        ...


class TrigramRetriever:
    """Trigram overlap over names and aliases with a soft same-state ranking bonus."""

    name = "trigram"

    def __init__(self, catalog: Catalog, cfg: ResolutionConfig) -> None:
        self._catalog = catalog
        self._bonus = cfg.state_bonus

    def retrieve(self, record: QueryRecord, k: int) -> list[tuple[int, float]]:
        hits = self._catalog.trigram_search(record.name, k * 3)
        q_state = state_code(record.state)
        if q_state:
            adjusted = []
            for cid, score in hits:
                same = state_code(self._catalog.by_id[cid].hq_state) == q_state
                adjusted.append((cid, score + (self._bonus if same else 0.0)))
            hits = sorted(adjusted, key=lambda kv: -kv[1])
        return [(cid, min(score, 1.0)) for cid, score in hits[:k]]


class VectorRetriever:
    """Dense retrieval over name and alias embeddings held in memory (numpy).

    The production path queries pgvector (`app.kb.embeddings.search`); this class serves the
    evaluation harness and tests with the same interface.
    """

    name = "vector"

    def __init__(self, catalog: Catalog, embedder: Embedder) -> None:
        self._embedder = embedder
        pairs = list(iter_catalog_names(catalog))
        self._ids = np.array([cid for cid, _ in pairs])
        self._matrix = np.array(embedder.encode([n for _, n in pairs]), dtype=np.float32)

    def retrieve(self, record: QueryRecord, k: int) -> list[tuple[int, float]]:
        q = np.array(self._embedder.encode([record.name])[0], dtype=np.float32)
        sims = self._matrix @ q
        order = np.argsort(-sims)
        out: list[tuple[int, float]] = []
        seen: set[int] = set()
        for idx in order:
            cid = int(self._ids[idx])
            if cid in seen:
                continue
            seen.add(cid)
            out.append((cid, float(max(0.0, min(1.0, sims[idx])))))
            if len(out) == k:
                break
        return out


class BlinkRetriever:
    """BLINK bi-encoder retrieval through the blink service."""

    name = "blink"

    def __init__(self, backend: BlinkBackend) -> None:
        self._backend = backend

    def retrieve(self, record: QueryRecord, k: int) -> list[tuple[int, float]]:
        context = " ".join(
            p for p in (record.city, record.state, record.country, record.context) if p
        )
        found = self._backend.retrieve(record.name, context, k)
        return [(c.company_id, c.score) for c in found]


def union_candidates(
    results: Sequence[tuple[str, list[tuple[int, float]]]],
) -> dict[int, tuple[set[str], float]]:
    """Merge generator outputs: company -> (generators, best score)."""
    merged: dict[int, tuple[set[str], float]] = {}
    for source, hits in results:
        for cid, score in hits:
            sources, best = merged.get(cid, (set(), 0.0))
            sources.add(source)
            merged[cid] = (sources, max(best, score))
    return merged
