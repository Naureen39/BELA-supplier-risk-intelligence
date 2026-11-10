"""Build the canonical company table from staged source records.

Rules, in order (first match wins):
  1. Identifier match: CIK, LEI, or Wikidata QID already held by a canonical company.
  2. Exact normalized name plus state (both present and equal).
  3. Reviewed fuzzy matches: high similarity candidates are NOT merged. They are recorded as
     `fuzzy_candidate` conflicts for human review and the record starts a new canonical company.
Records whose identifiers point to two different canonical companies are recorded as
`identifier_conflict` and attached to the first match. Every source record is linked with its
method and score. Corporate family edges are checked for cycles and multi-parent conflicts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
from rapidfuzz import fuzz, process

from app.kb.normalize import legal_form, normalize_name
from app.kb.staging import SourceCompany, SourceEdge

FUZZY_THRESHOLD = 92.0


@dataclass
class Canonical:
    index: int
    name: str
    normalized: str
    legal_form: str | None = None
    cik: int | None = None
    lei: str | None = None
    qid: str | None = None
    state: str | None = None
    country: str | None = None
    city: str | None = None
    tickers: list[str] = field(default_factory=list)
    sic: str | None = None
    is_public: bool = False
    status: str = "active"
    description: str | None = None
    aliases: dict[tuple[str, str], str] = field(default_factory=dict)  # (normalized, type)->alias


@dataclass(frozen=True)
class Link:
    source: str
    source_key: str
    canonical: int
    method: str
    score: float
    name: str
    state: str | None


@dataclass(frozen=True)
class Conflict:
    kind: str
    canonical: tuple[int, ...]
    details: dict[str, Any]


@dataclass(frozen=True)
class Relationship:
    parent: int
    child: int
    rel_type: str
    source: str
    share: float | None
    as_of: str | None


class CanonicalBuilder:
    def __init__(self) -> None:
        self.companies: list[Canonical] = []
        self.links: list[Link] = []
        self.conflicts: list[Conflict] = []
        self._by_cik: dict[int, int] = {}
        self._by_lei: dict[str, int] = {}
        self._by_qid: dict[str, int] = {}
        self._by_name_state: dict[tuple[str, str], int] = {}
        self._by_key: dict[tuple[str, str], int] = {}
        self._names: list[str] = []
        self._name_index: list[int] = []

    # -- matching -------------------------------------------------------------------------
    def _identifier_matches(self, rec: SourceCompany) -> set[int]:
        found = set()
        if rec.cik is not None and rec.cik in self._by_cik:
            found.add(self._by_cik[rec.cik])
        if rec.lei and rec.lei in self._by_lei:
            found.add(self._by_lei[rec.lei])
        if rec.qid and rec.qid in self._by_qid:
            found.add(self._by_qid[rec.qid])
        return found

    def add(self, rec: SourceCompany) -> int:
        norm = normalize_name(rec.name)
        method, score = "new", 1.0
        matches = self._identifier_matches(rec)
        target: int | None = None
        if matches:
            ordered = sorted(matches)
            target = ordered[0]
            method = "identifier"
            if len(ordered) > 1:
                self.conflicts.append(
                    Conflict(
                        "identifier_conflict",
                        tuple(ordered),
                        {"source": rec.source, "key": rec.source_key, "name": rec.name},
                    )
                )
        elif rec.state and (norm, rec.state) in self._by_name_state:
            target = self._by_name_state[(norm, rec.state)]
            method = "exact_name_state"
        if target is None:
            target = self._create(rec, norm)
            self._record_fuzzy_candidates(target, norm, rec)
        else:
            self._merge_into(self.companies[target], rec, norm)
        self.links.append(Link(rec.source, rec.source_key, target, method, score, rec.name, rec.state))
        self._by_key[(rec.source, rec.source_key)] = target
        return target

    def _create(self, rec: SourceCompany, norm: str) -> int:
        company = Canonical(
            index=len(self.companies),
            name=rec.name,
            normalized=norm,
            legal_form=legal_form(rec.name),
        )
        self.companies.append(company)
        self._merge_into(company, rec, norm)
        self._names.append(norm)
        self._name_index.append(company.index)
        return company.index

    def _merge_into(self, company: Canonical, rec: SourceCompany, norm: str) -> None:
        for attr in ("cik", "lei", "qid", "sic", "description", "city", "country"):
            value = getattr(rec, attr)
            if value is not None and getattr(company, attr) is None:
                setattr(company, attr, value)
        if rec.state and company.state is None:
            company.state = rec.state
        company.is_public = company.is_public or rec.is_public
        for ticker in rec.tickers:
            if ticker not in company.tickers:
                company.tickers.append(ticker)
        if rec.cik is not None:
            self._by_cik.setdefault(rec.cik, company.index)
        if rec.lei:
            self._by_lei.setdefault(rec.lei, company.index)
        if rec.qid:
            self._by_qid.setdefault(rec.qid, company.index)
        if company.state:
            self._by_name_state.setdefault((company.normalized, company.state), company.index)
        if norm != company.normalized:
            company.aliases.setdefault((norm, "legal"), rec.name)
        for alias, alias_type in rec.aliases:
            alias_norm = normalize_name(alias)
            if alias_norm and alias_norm != company.normalized:
                company.aliases.setdefault((alias_norm, alias_type), alias)
                if company.state:
                    self._by_name_state.setdefault((alias_norm, company.state), company.index)

    def _record_fuzzy_candidates(self, new_index: int, norm: str, rec: SourceCompany) -> None:
        if len(self._names) < 2 or len(norm) < 4:
            return
        hits = process.extract(
            norm, self._names[:-1], scorer=fuzz.token_sort_ratio, score_cutoff=FUZZY_THRESHOLD,
            limit=3,
        )
        for _name, score, position in hits:
            other = self._name_index[position]
            same_state = rec.state is None or self.companies[other].state in (None, rec.state)
            if same_state:
                self.conflicts.append(
                    Conflict("fuzzy_candidate", (other, new_index), {"score": round(score, 1)})
                )

    def add_all(self, records: list[SourceCompany]) -> None:
        for rec in records:
            self.add(rec)

    # -- relationships --------------------------------------------------------------------
    def resolve_edges(self, edges: list[SourceEdge]) -> list[Relationship]:
        out: list[Relationship] = []
        seen: set[tuple[int, int, str, str]] = set()
        for edge in edges:
            parent = self._by_key.get(edge.parent_key)
            child = self._by_key.get(edge.child_key)
            if parent is None or child is None or parent == child:
                continue
            key = (parent, child, edge.rel_type, edge.source)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                Relationship(parent, child, edge.rel_type, edge.source, edge.share, edge.as_of)
            )
        return out

    def check_relationships(self, relationships: list[Relationship]) -> list[Conflict]:
        """Detect cycles and conflicting direct parents across sources."""
        conflicts: list[Conflict] = []
        graph = nx.DiGraph()
        parents: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
        for rel in relationships:
            if rel.rel_type in ("direct_parent", "subsidiary", "owned_by"):
                graph.add_edge(rel.parent, rel.child)
                parents[rel.child][rel.parent].add(rel.source)
        for component in nx.strongly_connected_components(graph):
            if len(component) > 1:
                conflicts.append(Conflict("relationship_cycle", tuple(sorted(component)), {}))
        for child, by_parent in parents.items():
            if len(by_parent) > 1:
                conflicts.append(
                    Conflict(
                        "parent_conflict",
                        (child, *sorted(by_parent)),
                        {"parents": {str(p): sorted(s) for p, s in by_parent.items()}},
                    )
                )
        self.conflicts.extend(conflicts)
        return conflicts

    def lookup(self, source: str, key: str) -> int | None:
        return self._by_key.get((source, key))

    def find_exact(self, name: str, state: str | None) -> int | None:
        if not state:
            return None
        return self._by_name_state.get((normalize_name(name), state))
