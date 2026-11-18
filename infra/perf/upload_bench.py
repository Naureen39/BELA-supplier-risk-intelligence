"""Upload a 10,000 row supplier list and measure the time to accept it and to resolve every row.

Usage: python infra/perf/upload_bench.py http://127.0.0.1:8000 API_KEY DATABASE_URL [--rows 10000]
Names are the catalog's fictional companies, degraded the way the demo portfolios are (suffix variants,
abbreviations, typos). Resolution runs in the API process as a background task.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
import time

import httpx
import psycopg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("key")
    ap.add_argument("database_url")
    ap.add_argument("--rows", type=int, default=10_000)
    a = ap.parse_args()
    from app.resolution.perturb import perturb_name

    rng = random.Random(7)  # nosec B311
    with psycopg.connect(a.database_url.replace("postgresql+psycopg://", "postgresql://")) as conn:
        rows = conn.execute("SELECT canonical_name, hq_state, hq_city FROM companies ORDER BY id").fetchall()
    sample = [rng.choice(rows) for _ in range(a.rows)]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["name", "city", "state"])
    for name, state, city in sample:
        shown, _ = perturb_name(name, rng, state) if rng.random() < 0.8 else (name, [])
        w.writerow([shown, city if rng.random() < 0.7 else "", state if rng.random() < 0.9 else ""])
    body = out.getvalue().encode()
    h = {"Authorization": f"Bearer {a.key}"}
    with httpx.Client(base_url=a.host + "/api/v1", headers=h, timeout=300) as c:
        t0 = time.perf_counter()
        r = c.post("/uploads", files={"file": ("perf.csv", body, "text/csv")})
        r.raise_for_status()
        accepted = time.perf_counter() - t0
        uid = r.json()["id"]
        status = {}
        while True:
            status = c.get(f"/uploads/{uid}").json()
            if status["status"] in ("complete", "failed"):
                break
            time.sleep(1)
        total = time.perf_counter() - t0
    print(json.dumps({"rows": a.rows, "csv_bytes": len(body), "accepted_seconds": round(accepted, 2),
                      "resolved_seconds": round(total, 2), "rows_per_second": round(a.rows / total, 1),
                      "status": status["status"], "auto_resolved": status.get("auto_resolved"),
                      "needs_review": status.get("needs_review"), "unresolved": status.get("unresolved")}))
    sys.exit(0 if status["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
