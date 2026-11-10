"""Data quality tests (pandera and SQL assertions) and the coverage report."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import pandera.pandas as pa
import psycopg

from app.kb.normalize import VALID_STATE_CODES

COMPANY_SCHEMA = pa.DataFrameSchema(
    {
        "canonical_name": pa.Column(str, pa.Check(lambda s: s.str.strip().str.len() > 0)),
        "normalized_name": pa.Column(str, pa.Check(lambda s: s.str.len() > 0)),
        "hq_state": pa.Column(
            str, pa.Check.isin(sorted(VALID_STATE_CODES)), nullable=True
        ),
        "cik": pa.Column(float, nullable=True, unique=False),
    },
    strict=False,
)

FACILITY_SCHEMA = pa.DataFrameSchema(
    {
        "registry_id": pa.Column(str, unique=True),
        "name": pa.Column(str, pa.Check(lambda s: s.str.strip().str.len() > 0)),
        "state": pa.Column(str, pa.Check.isin(sorted(VALID_STATE_CODES)), nullable=True),
    },
    strict=False,
)

# Each assertion returns the number of violating rows; zero means pass.
SQL_ASSERTIONS: dict[str, str] = {
    "companies_without_name": "SELECT count(*) FROM companies WHERE trim(canonical_name) = ''",
    "invalid_company_state": "SELECT count(*) FROM companies WHERE hq_state IS NOT NULL "
    "AND hq_state !~ '^[A-Z]{2}$'",
    "duplicate_cik": "SELECT count(*) FROM (SELECT cik FROM companies WHERE cik IS NOT NULL "
    "GROUP BY cik HAVING count(*) > 1) t",
    "duplicate_lei": "SELECT count(*) FROM (SELECT lei FROM companies WHERE lei IS NOT NULL "
    "GROUP BY lei HAVING count(*) > 1) t",
    "duplicate_source_keys": "SELECT count(*) FROM (SELECT 1 FROM source_records GROUP BY source, "
    "source_key, record_type HAVING count(*) > 1) t",
    "orphan_source_records": "SELECT count(*) FROM source_records WHERE company_id IS NULL",
    "self_relationships": "SELECT count(*) FROM company_relationships WHERE parent_id = child_id",
    "bad_embedding_dimension": "SELECT count(*) FROM entity_embeddings "
    "WHERE vector_dims(embedding) <> 1024",
    "facility_bad_coordinates": "SELECT count(*) FROM facilities WHERE latitude IS NOT NULL "
    "AND (latitude NOT BETWEEN 18 AND 72 OR longitude NOT BETWEEN -180 AND -60) "
    "AND state NOT IN ('GU','AS','MP','VI','PR','HI','AK')",
}


@dataclass
class QualityReport:
    assertion_failures: dict[str, int]
    schema_errors: list[str]
    coverage: dict[str, Any]
    conflicts: dict[str, int]

    @property
    def passed(self) -> bool:
        return not self.schema_errors and not any(self.assertion_failures.values())


def run_sql_assertions(conn: psycopg.Connection) -> dict[str, int]:
    return {name: int(conn.execute(sql).fetchone()[0]) for name, sql in SQL_ASSERTIONS.items()}  # type: ignore[index]


def run_schema_checks(conn: psycopg.Connection) -> list[str]:
    errors: list[str] = []
    for name, schema, query in (
        ("companies", COMPANY_SCHEMA,
         "SELECT canonical_name, normalized_name, hq_state, cik FROM companies"),
        ("facilities", FACILITY_SCHEMA, "SELECT registry_id, name, state FROM facilities"),
    ):
        cur = conn.execute(query)
        frame = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description or []])
        try:
            schema.validate(frame, lazy=True)
        except pa.errors.SchemaErrors as exc:
            errors.append(f"{name}: {len(exc.failure_cases)} failures")
    return errors


def coverage(conn: psycopg.Connection) -> dict[str, Any]:
    """Identifier coverage, alias counts, and facility linkability."""

    def one(sql: str) -> int:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0

    total = one("SELECT count(*) FROM companies")
    facilities = one("SELECT count(*) FROM facilities")
    linked = one("SELECT count(*) FROM facilities WHERE company_id IS NOT NULL")
    by_source: dict[str, int] = {
        str(k): int(v)
        for k, v in conn.execute("SELECT source, count(*) FROM source_records GROUP BY 1")
    }
    return {
        "companies": total,
        "with_cik": one("SELECT count(*) FROM companies WHERE cik IS NOT NULL"),
        "with_lei": one("SELECT count(*) FROM companies WHERE lei IS NOT NULL"),
        "with_qid": one("SELECT count(*) FROM companies WHERE wikidata_qid IS NOT NULL"),
        "aliases": one("SELECT count(*) FROM company_aliases"),
        "relationships": one("SELECT count(*) FROM company_relationships"),
        "facilities": facilities,
        "facilities_linked_exact": linked,
        "facility_link_rate": (linked / facilities) if facilities else None,
        "source_records_by_source": by_source,
    }


def build_report(conn: psycopg.Connection) -> QualityReport:
    conflicts: dict[str, int] = {
        str(k): int(v)
        for k, v in conn.execute("SELECT kind, count(*) FROM canonical_conflicts GROUP BY 1")
    }
    return QualityReport(
        run_sql_assertions(conn), run_schema_checks(conn), coverage(conn), conflicts
    )


def format_report(report: QualityReport) -> str:
    lines = ["Data quality report", "==================="]
    lines += [f"{k}: {v}" for k, v in report.coverage.items()]
    lines.append("conflicts: " + (", ".join(f"{k}={v}" for k, v in report.conflicts.items()) or "none"))
    lines += [f"assertion {k}: {'ok' if v == 0 else f'FAIL ({v})'}" for k, v in report.assertion_failures.items()]
    lines += [f"schema {e}" for e in report.schema_errors]
    lines.append("RESULT: " + ("pass" if report.passed else "fail"))
    return "\n".join(lines)
