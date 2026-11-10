"""Systems compared by `make eval` (structured records)."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Protocol

from rapidfuzz import fuzz

from app.kb.normalize import normalize_name, state_code
from app.resolution.catalog import Catalog
from app.resolution.evaluation.metrics import Prediction
from app.resolution.models import QueryRecord
from app.resolution.structured import Resolver


class System(Protocol):
    name: str
    accept_threshold: float

    def predict(self, record: QueryRecord) -> tuple[int | None, float, tuple[int, ...], str | None]:
        """Return (top company, score 0..1, ranked ids, route or None)."""
        ...


class RapidFuzzSystem:
    """Fuzzy name matching with state blocking: candidates restricted to the record's state."""

    name = "rapidfuzz_state_blocking"
    accept_threshold = 0.90

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._names = [(r.id, normalize_name(n), state_code(r.hq_state))
                       for r in catalog.records for n in r.all_names()]

    def predict(self, record: QueryRecord) -> tuple[int | None, float, tuple[int, ...], str | None]:
        q = normalize_name(record.name)
        q_state = state_code(record.state)
        best: dict[int, float] = {}
        for cid, name, st in self._names:
            if q_state and st and st != q_state:
                continue
            score = fuzz.token_sort_ratio(q, name) / 100.0
            if score > best.get(cid, 0.0):
                best[cid] = score
        ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        if not ranked:
            return None, 0.0, (), None
        return ranked[0][0], ranked[0][1], tuple(c for c, _ in ranked), None


class ResolverSystem:
    """Wraps a Resolver. Variants: Fellegi-Sunter only, vector only, full hybrid."""

    def __init__(self, name: str, resolver: Resolver, accept_threshold: float | None = None) -> None:
        self.name = name
        self._resolver = resolver
        self.accept_threshold = accept_threshold or resolver.cfg.accept_threshold

    def predict(self, record: QueryRecord) -> tuple[int | None, float, tuple[int, ...], str | None]:
        res = self._resolver.resolve(record)
        ranked = tuple(c.company_id for c in res.candidates)
        top = res.candidates[0].company_id if res.candidates else None
        score = res.candidates[0].probability if res.candidates else 0.0
        return top, score, ranked, res.route.value


def run_system(
    system: System, records: Sequence[QueryRecord], truth: dict[str, int | None],
    tags: dict[str, frozenset[str]] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> list[Prediction]:
    out: list[Prediction] = []
    for rec in records:
        t0 = clock()
        top, score, ranked, route = system.predict(rec)
        latency = (clock() - t0) * 1000
        out.append(Prediction(rec.id, truth[rec.id], top, score, ranked, route, latency,
                              (tags or {}).get(rec.id, frozenset())))
    return out
