"""Resolution pipeline for structured records and uploaded suppliers (problems A and C)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.kb.normalize import normalize_name
from app.resolution.catalog import Catalog, domain_of
from app.resolution.clients import BlinkBackend, ServiceUnavailable
from app.resolution.config import DEFAULT_CONFIG, ResolutionConfig
from app.resolution.features import pair_features
from app.resolution.models import QueryRecord, Resolution, Route, ScoredCandidate
from app.resolution.retrievers import Retriever, TrigramRetriever, union_candidates
from app.resolution.routing import route_probabilities
from app.resolution.scoring import (
    Calibrator,
    FellegiSunter,
    LogisticCombiner,
    matrix,
)


class Resolver:
    """Normalize, match identifiers, generate candidates, score, and route.

    Without a fitted combiner the Fellegi-Sunter probability is used directly. Probabilities are
    not calibrated unless a calibrator is supplied, and the config status stays "provisional".
    """

    def __init__(
        self,
        catalog: Catalog,
        retrievers: Sequence[Retriever] | None = None,
        blink: BlinkBackend | None = None,
        fs: FellegiSunter | None = None,
        combiner: LogisticCombiner | None = None,
        calibrator: Calibrator | None = None,
        cfg: ResolutionConfig = DEFAULT_CONFIG,
    ) -> None:
        self.catalog = catalog
        self.cfg = cfg
        self.retrievers: list[Retriever] = (
            list(retrievers) if retrievers is not None else [TrigramRetriever(catalog, cfg)]
        )
        self.blink = blink
        self.fs = fs or FellegiSunter()
        self.combiner = combiner
        self.calibrator = calibrator

    # ------------------------------------------------------------------ identifiers
    def _identifier_matches(self, record: QueryRecord) -> tuple[set[int], str]:
        found: dict[str, set[int]] = {}
        if record.cik is not None:
            found["cik"] = set(self.catalog.by_cik.get(record.cik, ()))
        if record.lei:
            found["lei"] = set(self.catalog.by_lei.get(record.lei.upper(), ()))
        if record.ticker:
            found["ticker"] = set(self.catalog.by_ticker.get(record.ticker.upper(), ()))
        domain = domain_of(record.website)
        if domain:
            found["domain"] = set(self.catalog.by_domain.get(domain, ()))
        hits = {k: v for k, v in found.items() if v}
        if not hits:
            return set(), ""
        union = set().union(*hits.values())
        return union, "+".join(sorted(hits))

    # ------------------------------------------------------------------ scoring
    def score_candidates(self, record: QueryRecord) -> tuple[list[ScoredCandidate], bool]:
        """Generate and score candidates. Returns (candidates best first, degraded flag)."""
        degraded = False
        results: list[tuple[str, list[tuple[int, float]]]] = []
        for retriever in self.retrievers:
            k = {
                "trigram": self.cfg.trigram_k,
                "vector": self.cfg.vector_k,
                "blink": self.cfg.blink_k,
            }.get(retriever.name, 30)
            try:
                results.append((retriever.name, retriever.retrieve(record, k)))
            except ServiceUnavailable:
                degraded = True
        merged = union_candidates(results)

        blink_scores: dict[int, float] = {}
        if self.blink is not None and merged:
            context = " ".join(
                p for p in (record.city, record.state, record.country, record.context) if p
            )
            try:
                blink_scores = self.blink.rerank(record.name, context, list(merged))
            except ServiceUnavailable:
                degraded = True

        scored: list[ScoredCandidate] = []
        for cid, (sources, best) in merged.items():
            rec = self.catalog.by_id[cid]
            feats = pair_features(record, rec, best, len(sources), blink_scores.get(cid))
            weight = self.fs.weight(feats)
            scored.append(
                ScoredCandidate(
                    company_id=cid, name=rec.name, sources=sources, retrieval_score=best,
                    features=feats, splink_weight=weight, blink_score=blink_scores.get(cid),
                )
            )
        self._assign_probabilities(scored)
        scored.sort(key=lambda c: (-c.probability, c.company_id))
        return scored[: self.cfg.candidates_kept], degraded

    def _assign_probabilities(self, scored: list[ScoredCandidate]) -> None:
        if not scored:
            return
        if self.combiner is not None and self.combiner.fitted:
            X = matrix([(c.features, c.splink_weight) for c in scored])
            raw = self.combiner.predict(X)
        else:
            raw = np.array([self.fs.probability(c.features) for c in scored])
        for cand, p in zip(scored, raw, strict=True):
            cand.raw_probability = float(p)
            cand.probability = self.calibrator.apply(float(p)) if self.calibrator else float(p)

    # ------------------------------------------------------------------ main entry
    def resolve(self, record: QueryRecord) -> Resolution:
        if not normalize_name(record.name) and not (record.cik or record.lei or record.ticker):
            return Resolution(
                record.id, None, Route.NIL, "empty_name", 0.0, 0.0, [], self.cfg.version,
                notes=["record has no usable name or identifier"],
            )
        ids, id_method = self._identifier_matches(record)
        if len(ids) == 1:
            cid = next(iter(ids))
            rec = self.catalog.by_id[cid]
            cand = ScoredCandidate(cid, rec.name, {"identifier"}, 1.0, probability=1.0,
                                   raw_probability=1.0)
            return Resolution(record.id, cid, Route.EXACT_ID, f"id:{id_method}", 1.0, 1.0,
                              [cand], self.cfg.version)

        candidates, degraded = self.score_candidates(record)
        notes: list[str] = []
        if len(ids) > 1:
            notes.append(f"identifiers ({id_method}) point to {len(ids)} companies")
            top_ids = [c for c in candidates if c.company_id in ids]
            return Resolution(
                record.id, top_ids[0].company_id if top_ids else None, Route.REVIEW,
                f"id_conflict:{id_method}", top_ids[0].probability if top_ids else 0.0, 0.0,
                candidates, self.cfg.version, degraded, notes,
            )
        if not candidates:
            return Resolution(record.id, None, Route.NIL, "no_candidates", 0.0, 0.0, [],
                              self.cfg.version, degraded)

        top = candidates[0]
        runner = candidates[1].probability if len(candidates) > 1 else 0.0
        route = route_probabilities(top.probability, runner, self.cfg, degraded)
        if degraded:
            notes.append("reduced confidence: a model service was unavailable")
        return Resolution(
            record.id, top.company_id if route is not Route.NIL else None, route,
            "hybrid" if len(self.retrievers) > 1 or self.blink else "fuzzy_fs",
            top.probability, top.probability - runner, candidates, self.cfg.version, degraded, notes,
        )

    def resolve_many(self, records: Sequence[QueryRecord]) -> list[Resolution]:
        return [self.resolve(r) for r in records]
