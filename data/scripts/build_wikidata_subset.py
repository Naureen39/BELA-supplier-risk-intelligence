"""Extract a company subset from a Wikidata Parquet conversion using DuckDB.

Input: Parquet files of the truthy dump (community conversion on Hugging Face), with columns
(subject, predicate, object) and a labels table (id, lang, label, aliases). The exact layout of
the chosen conversion must be set in data/scripts/wikidata_layout.yaml. Verify class and property
IDs on wikidata.org before relying on them.

Outputs (raw/knowledge_base/wikidata/):
  companies.parquet      qid, label_en, description_en
  aliases.parquet        qid, lang, alias
  identifiers.parquet    qid, lei, cik, ticker
  relations.parquet      qid, property, target_qid
  qid_map.parquet        qid, lei, cik (basis for the QID to canonical company map)

Usage: python -m data.scripts.build_wikidata_subset --source DIR
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from data.scripts.common import RAW_DIR, record_file, setup_logging

OUT = RAW_DIR / "knowledge_base" / "wikidata"

# Instance-of roots (subclasses are included through P279 closure).
CLASS_ROOTS = ["Q783794", "Q4830453", "Q891723", "Q6881511", "Q22687"]
INSTANCE_OF = "P31"
SUBCLASS_OF = "P279"
IDENTIFIER_PROPS = {"lei": "P1278", "cik": "P5531", "ticker": "P249"}
RELATION_PROPS = {
    "parent_organization": "P749",
    "owned_by": "P127",
    "subsidiary": "P355",
    "industry": "P452",
    "headquarters": "P159",
    "inception": "P571",
}


def subclass_closure_sql(roots: list[str], triples: str) -> str:
    """SQL (recursive CTE) listing every class that is a subclass of any root."""
    values = ", ".join(f"('{r}')" for r in roots)
    return f"""
    WITH RECURSIVE classes(qid) AS (
        SELECT * FROM (VALUES {values}) AS t(qid)
        UNION
        SELECT s.subject FROM {triples} s JOIN classes c ON s.object = c.qid
        WHERE s.predicate = '{SUBCLASS_OF}'
    )
    SELECT qid FROM classes
    """


def build(source: Path, out: Path = OUT) -> dict[str, int]:
    log = setup_logging("build_wikidata_subset")
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE VIEW triples AS SELECT * FROM read_parquet('{source}/triples/*.parquet')")
    con.execute(f"CREATE VIEW labels AS SELECT * FROM read_parquet('{source}/labels/*.parquet')")
    con.execute(f"CREATE TABLE classes AS {subclass_closure_sql(CLASS_ROOTS, 'triples')}")
    con.execute(
        f"""CREATE TABLE company_ids AS
        SELECT DISTINCT subject AS qid FROM triples
        WHERE predicate = '{INSTANCE_OF}' AND object IN (SELECT qid FROM classes)"""
    )
    exports = {
        "companies": """SELECT c.qid, l.label AS label_en, l.description AS description_en
                        FROM company_ids c LEFT JOIN labels l ON l.id = c.qid AND l.lang = 'en'""",
        "aliases": """SELECT c.qid, l.lang, unnest(l.aliases) AS alias
                      FROM company_ids c JOIN labels l ON l.id = c.qid""",
        "identifiers": "SELECT c.qid, "
        + ", ".join(
            f"max(CASE WHEN t.predicate = '{p}' THEN t.object END) AS {name}"
            for name, p in IDENTIFIER_PROPS.items()
        )
        + " FROM company_ids c LEFT JOIN triples t ON t.subject = c.qid GROUP BY c.qid",
        "relations": "SELECT t.subject AS qid, t.predicate AS property, t.object AS target_qid "
        "FROM triples t JOIN company_ids c ON c.qid = t.subject WHERE t.predicate IN ("
        + ", ".join(f"'{p}'" for p in RELATION_PROPS.values())
        + ")",
    }
    counts: dict[str, int] = {}
    for name, query in exports.items():
        dest = out / f"{name}.parquet"
        con.execute(f"COPY ({query}) TO '{dest}' (FORMAT PARQUET)")
        counts[name] = int(con.execute(f"SELECT count(*) FROM read_parquet('{dest}')").fetchall()[0][0])
        record_file("wikidata", dest, str(source))
        log.info("wrote %s: %d rows", dest.name, counts[name])
    qid_map = out / "qid_map.parquet"
    con.execute(
        f"COPY (SELECT qid, lei, cik FROM read_parquet('{out / 'identifiers.parquet'}') "
        f"WHERE lei IS NOT NULL OR cik IS NOT NULL) TO '{qid_map}' (FORMAT PARQUET)"
    )
    record_file("wikidata", qid_map, str(source))
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args(argv)
    build(args.source)


if __name__ == "__main__":
    main()
