"""ETL entry point: stage sources, build canonical companies, load PostgreSQL, embed, report.

Usage (from apps/api, with the repository root on PYTHONPATH):
  DATABASE_URL=... python -m app.kb.pipeline [--embedder bge-m3|hashed] [--no-embed]
Sources that are not present under data/raw are skipped with a warning.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from app.kb import staging
from app.kb.canonical import CanonicalBuilder
from app.kb.embeddings import BgeM3Embedder, Embedder, HashedNgramEmbedder, embed_entities
from app.kb.quality import build_report, format_report
from app.kb.writer import (
    connect,
    reset_knowledge,
    write_companies,
    write_conflicts,
    write_facilities,
    write_relationships,
)

log = logging.getLogger("etl")
RAW = Path(__file__).resolve().parents[4] / "data" / "raw"


def build(
    raw: Path | None = None,
) -> tuple[CanonicalBuilder, list[staging.SourceEdge], list[staging.SourceFacility]]:
    raw = raw or RAW
    builder = CanonicalBuilder()
    edges: list[staging.SourceEdge] = []
    facilities: list[staging.SourceFacility] = []

    tickers = raw / "edgar" / "company_tickers_exchange.json"
    if tickers.exists():
        records = staging.load_edgar_tickers(tickers)
        lookup = raw / "edgar" / "cik-lookup-data.txt"
        names = staging.load_edgar_cik_lookup(lookup) if lookup.exists() else {}
        for rec in records:
            if rec.cik is not None:
                rec.aliases += [(n, "former") for n in names.get(rec.cik, []) if n != rec.name]
        builder.add_all(records)
    else:
        log.warning("EDGAR tickers missing: %s", tickers)

    wikidata = raw / "knowledge_base" / "wikidata"
    if (wikidata / "companies.parquet").exists():
        builder.add_all(staging.load_wikidata(wikidata))
    else:
        log.warning("Wikidata subset missing: %s", wikidata)

    for level1 in sorted((raw / "registry" / "gleif").glob("*lei2*.csv")):
        builder.add_all(list(staging.load_gleif_level1(level1)))
    for level2 in sorted((raw / "registry" / "gleif").glob("*rr*.csv")):
        edges += list(staging.load_gleif_level2(level2))

    ex21 = raw / "edgar" / "exhibit21"
    if ex21.exists():
        subs, sub_edges = staging.load_exhibit21(ex21)
        builder.add_all(subs)
        edges += sub_edges

    for frs in sorted((raw / "regulators" / "epa_echo").glob("*frs*.csv")):
        facilities += list(staging.load_frs(frs))
    return builder, edges, facilities


def make_embedder(kind: str) -> Embedder:
    return BgeM3Embedder() if kind == "bge-m3" else HashedNgramEmbedder()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedder", choices=["bge-m3", "hashed"], default="bge-m3")
    parser.add_argument("--no-embed", action="store_true")
    args = parser.parse_args(argv)

    builder, edges, facilities = build()
    relationships = builder.resolve_edges(edges)
    builder.check_relationships(relationships)
    with connect(os.environ["DATABASE_URL"]) as conn:
        reset_knowledge(conn)
        ids = write_companies(conn, builder)
        write_relationships(conn, relationships, ids)
        write_facilities(conn, builder, facilities, ids)
        write_conflicts(conn, builder.conflicts, ids)
        if not args.no_embed:
            log.info("embedded %d texts", embed_entities(conn, make_embedder(args.embedder)))
        report = build_report(conn)
    print(format_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
