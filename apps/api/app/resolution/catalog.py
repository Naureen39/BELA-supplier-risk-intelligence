"""In-memory company catalog with identifier maps and a trigram candidate index.

The catalog mirrors `companies`, `company_aliases`, and `company_relationships`. It serves the
resolver, the evaluation harness, and the BLINK entity catalog export. For very large catalogs the
trigram index trades memory for speed; PostgreSQL pg_trgm remains the production fallback.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.kb.normalize import normalize_name


@dataclass(frozen=True)
class CompanyRecord:
    id: int
    name: str
    aliases: tuple[str, ...] = ()
    cik: int | None = None
    lei: str | None = None
    qid: str | None = None
    tickers: tuple[str, ...] = ()
    domain: str | None = None
    sic_code: str | None = None
    industry: str | None = None
    hq_city: str | None = None
    hq_state: str | None = None
    hq_country: str | None = "US"
    is_public: bool = False
    parent_name: str | None = None
    description: str | None = None

    @property
    def normalized(self) -> str:
        return normalize_name(self.name)

    def all_names(self) -> list[str]:
        return [self.name, *self.aliases]


def _trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def domain_of(website: str | None) -> str | None:
    """Reduce a URL or host to a bare registrable-looking domain."""
    if not website:
        return None
    text = website.strip().casefold()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.split("/", 1)[0].split("?", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text or None


@dataclass
class Catalog:
    records: Sequence[CompanyRecord]
    edges: Sequence[tuple[int, int]] = ()  # (parent_id, child_id)

    by_id: dict[int, CompanyRecord] = field(init=False, default_factory=dict)
    by_cik: dict[int, list[int]] = field(init=False, default_factory=lambda: defaultdict(list))
    by_lei: dict[str, list[int]] = field(init=False, default_factory=lambda: defaultdict(list))
    by_qid: dict[str, int] = field(init=False, default_factory=dict)
    by_ticker: dict[str, list[int]] = field(init=False, default_factory=lambda: defaultdict(list))
    by_domain: dict[str, list[int]] = field(init=False, default_factory=lambda: defaultdict(list))
    by_norm: dict[str, list[int]] = field(init=False, default_factory=lambda: defaultdict(list))
    _entries: list[tuple[int, str]] = field(init=False, default_factory=list)
    _postings: dict[str, list[int]] = field(init=False, default_factory=lambda: defaultdict(list))

    def __post_init__(self) -> None:
        for rec in self.records:
            self.by_id[rec.id] = rec
            if rec.cik is not None:
                self.by_cik[rec.cik].append(rec.id)
            if rec.lei:
                self.by_lei[rec.lei.upper()].append(rec.id)
            if rec.qid:
                self.by_qid[rec.qid] = rec.id
            for tick in rec.tickers:
                self.by_ticker[tick.upper()].append(rec.id)
            if rec.domain:
                self.by_domain[rec.domain.casefold()].append(rec.id)
            seen: set[str] = set()
            for name in rec.all_names():
                norm = normalize_name(name)
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                self.by_norm[norm].append(rec.id)
                entry = len(self._entries)
                self._entries.append((rec.id, norm))
                for tri in _trigrams(norm):
                    self._postings[tri].append(entry)

    def __len__(self) -> int:
        return len(self.records)

    # ------------------------------------------------------------------ candidate search
    def trigram_search(self, query: str, k: int = 30) -> list[tuple[int, float]]:
        """Top-k companies by trigram Jaccard overlap with any name or alias (score 0 to 1)."""
        norm = normalize_name(query)
        if not norm:
            return []
        q_tris = _trigrams(norm)
        hits: Counter[int] = Counter()
        limit = max(2000, len(self._entries) // 20)  # ignore trigrams that are near-universal
        for tri in q_tris:
            posting = self._postings.get(tri)
            if posting and len(posting) <= limit:
                hits.update(posting)
        best: dict[int, float] = {}
        for entry, shared in hits.most_common(max(k * 8, 100)):
            company_id, name = self._entries[entry]
            union = len(q_tris) + len(_trigrams(name)) - shared
            score = shared / union if union else 0.0
            if score > best.get(company_id, 0.0):
                best[company_id] = score
        return sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:k]

    def exact_name(self, query: str) -> list[int]:
        return list(self.by_norm.get(normalize_name(query), []))

    # ------------------------------------------------------------------ BLINK export
    def blink_entity_text(self, rec: CompanyRecord) -> str:
        """Description used by the bi-encoder and cross-encoder (section 5.4 of the plan)."""
        parts = [rec.name]
        if rec.aliases:
            parts.append("also known as " + "; ".join(rec.aliases[:5]))
        if rec.industry or rec.sic_code:
            parts.append("industry " + (rec.industry or f"SIC {rec.sic_code}"))
        place = ", ".join(p for p in (rec.hq_city, rec.hq_state) if p)
        if place:
            parts.append("headquartered in " + place)
        parts.append("public company" if rec.is_public else "private company")
        if rec.parent_name:
            parts.append("subsidiary of " + rec.parent_name)
        if rec.tickers:
            parts.append("ticker " + ", ".join(rec.tickers))
        return ". ".join(parts)


def load_catalog(conn: Any) -> Catalog:
    """Load the catalog from PostgreSQL (works with any row factory)."""
    from psycopg.rows import tuple_row

    with conn.cursor(row_factory=tuple_row) as cur:
        aliases: dict[int, list[str]] = defaultdict(list)
        cur.execute("SELECT company_id, alias FROM company_aliases")
        for company_id, alias in cur.fetchall():
            aliases[company_id].append(alias)
        cur.execute("SELECT parent_id, child_id FROM company_relationships "
                    "WHERE rel_type IN ('direct_parent','subsidiary','owned_by')")
        edges = [(p, c) for p, c in cur.fetchall()]
        cur.execute(
            "SELECT id, canonical_name, cik, lei, wikidata_qid, tickers, sic_code, hq_city, hq_state, "
            "hq_country, is_public, description FROM companies")
        rows = cur.fetchall()
    parent_of: dict[int, int] = {c: p for p, c in edges}
    names = {r[0]: r[1] for r in rows}
    records = [
        CompanyRecord(
            id=r[0], name=r[1], aliases=tuple(aliases.get(r[0], ())), cik=r[2], lei=r[3],
            qid=r[4], tickers=tuple(r[5] or ()), sic_code=r[6], hq_city=r[7], hq_state=r[8],
            hq_country=r[9], is_public=bool(r[10]), description=r[11],
            parent_name=names.get(parent_of.get(r[0], -1)),
        )
        for r in rows
    ]
    return Catalog(records, edges)


def iter_catalog_names(catalog: Catalog) -> Iterable[tuple[int, str]]:
    for rec in catalog.records:
        for name in rec.all_names():
            yield rec.id, name
