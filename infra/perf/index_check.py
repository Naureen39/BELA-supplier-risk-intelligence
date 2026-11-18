"""Time the queries that the profile flagged, before and after an index change.

Usage: python infra/perf/index_check.py DATABASE_URL [--label before]
Each query runs 30 times; the mean and the plan's top node are printed as JSON lines.
"""

from __future__ import annotations

import argparse
import json
import time

import psycopg
from psycopg.rows import dict_row

OLD_SEARCH = ("SELECT id, canonical_name FROM companies WHERE normalized_name %% %(n)s OR normalized_name LIKE %(n)s || '%%' "
              "OR upper(%(q)s) = ANY(tickers) ORDER BY similarity(normalized_name, %(n)s) DESC, id LIMIT 20")
NEW_SEARCH = ("SELECT id, canonical_name FROM ("
              " (SELECT id, canonical_name, normalized_name FROM companies WHERE normalized_name %% %(n)s)"
              " UNION (SELECT id, canonical_name, normalized_name FROM companies WHERE normalized_name LIKE %(n)s || '%%' LIMIT 100)"
              " UNION (SELECT id, canonical_name, normalized_name FROM companies WHERE tickers @> ARRAY[upper(%(q)s)])"
              ") t ORDER BY similarity(normalized_name, %(n)s) DESC, id LIMIT 20")


def timed(conn: psycopg.Connection, name: str, sql: str, params: dict[str, object], label: str) -> None:
    conn.execute(sql, params).fetchall()  # warm up
    t = time.perf_counter()
    for _ in range(30):
        conn.execute(sql, params).fetchall()
    ms = (time.perf_counter() - t) / 30 * 1000
    plan = conn.execute("EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) " + sql, params).fetchall()
    top = "; ".join(sorted({line for row in plan for line in [next(iter(row.values())).strip()]
                            if line.startswith(("Seq Scan", "Index", "Bitmap", "->  Seq", "->  Index", "->  Bitmap"))})[:3])
    print(json.dumps({"label": label, "query": name, "mean_ms": round(ms, 2), "plan": top[:160]}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--label", default="run")
    a = ap.parse_args()
    with psycopg.connect(a.url.replace("postgresql+psycopg://", "postgresql://"), row_factory=dict_row, autocommit=True) as conn:
        score = conn.execute("SELECT id FROM risk_scores ORDER BY id LIMIT 1 OFFSET 500").fetchone()
        ent = conn.execute("SELECT event_entity_id AS id FROM link_candidates ORDER BY id LIMIT 1 OFFSET 4000").fetchone()
        alert = conn.execute("SELECT alert_id AS id FROM alert_events LIMIT 1").fetchone()
        sid = score["id"] if score else 1
        timed(conn, "score components by score", "SELECT c.event_id, e.title FROM risk_score_components c JOIN events e ON e.id = c.event_id "
              "WHERE c.risk_score_id = %(id)s ORDER BY c.event_impact DESC", {"id": sid}, a.label)
        timed(conn, "candidates by event entity", "SELECT lc.rank, co.canonical_name FROM link_candidates lc JOIN companies co ON co.id = lc.company_id "
              "WHERE lc.event_entity_id = %(id)s ORDER BY lc.rank", {"id": ent["id"] if ent else 1}, a.label)
        if alert:
            timed(conn, "alert history", "SELECT id, change FROM alert_events WHERE alert_id = %(id)s ORDER BY id", {"id": alert["id"]}, a.label)
        for q in ("granite", "summit steel", "cobalt"):
            p = {"n": q, "q": q}
            timed(conn, f"company search old ({q})", OLD_SEARCH, p, a.label)
            timed(conn, f"company search new ({q})", NEW_SEARCH, p, a.label)


if __name__ == "__main__":
    main()
