"""List the slowest queries recorded by pg_stat_statements, with their generic plans.

Usage: python infra/perf/top_queries.py DATABASE_URL [--limit 20] [--out var/perf/top-queries.md]
Run it after a load test (reset the counters first with `SELECT pg_stat_statements_reset()`).
The generic plan (`EXPLAIN (GENERIC_PLAN)`) shows the plan PostgreSQL would use without knowing the parameter
values: it flags sequential scans on large tables and shows which indexes are used.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

NOISE = re.compile(r"^(SET|SELECT set_config|BEGIN|COMMIT|ROLLBACK|SHOW|DEALLOCATE|SELECT pg_stat|CREATE|ANALYZE|COPY|INSERT INTO audit_log)", re.I)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", type=Path, default=Path("var/perf/top-queries.md"))
    a = ap.parse_args()
    url = a.url.replace("postgresql+psycopg://", "postgresql://")
    lines = ["# Slowest queries by total time", "", "| # | Calls | Mean ms | Total ms | Rows per call | Plan summary | Query |", "|---|---|---|---|---|---|---|"]
    details: list[str] = []
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT queryid, query, calls, mean_exec_time, total_exec_time, rows::float / greatest(calls, 1) AS rpc "
            "FROM pg_stat_statements WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) "
            "ORDER BY total_exec_time DESC LIMIT 200").fetchall()
        picked = [r for r in rows if not NOISE.match(r["query"].lstrip())][: a.limit]
        for n, r in enumerate(picked, 1):
            q = " ".join(r["query"].split())
            plan_text, summary = "", "n/a"
            try:
                plan = conn.execute("EXPLAIN (GENERIC_PLAN, COSTS OFF) " + r["query"]).fetchall()
                plan_text = "\n".join(next(iter(p.values())) for p in plan)
                scans = re.findall(r"(Seq Scan|Index Only Scan|Index Scan|Bitmap Heap Scan) (?:using \w+ )?on (\w+)", plan_text)
                seq = sorted({t for k, t in scans if k == "Seq Scan"})
                summary = ("seq scan: " + ", ".join(seq)) if seq else "indexed"
            except psycopg.Error as exc:
                summary = f"not explained ({type(exc).__name__})"
            lines.append(f"| {n} | {r['calls']} | {r['mean_exec_time']:.2f} | {r['total_exec_time']:.0f} | {r['rpc']:.1f} | {summary} | `{q[:110].replace('|', '/')}` |")
            details.append(f"## {n}. {q[:160]}\n\nCalls {r['calls']}, mean {r['mean_exec_time']:.2f} ms.\n\n```\n{plan_text or summary}\n```\n")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(lines) + "\n\n" + "\n".join(details))
    print(f"{len(picked)} queries written to {a.out}")


if __name__ == "__main__":
    main()
