"""Build the database used for load tests: fictional companies, events, a tenant, and its suppliers.

Usage: PYTHONPATH=.:apps/api python infra/perf/seed_perf.py ADMIN_URL [--companies 20000] [--events 60000]
                                                             [--suppliers 3000] [--db perf10]
Prints a JSON object with the database URL, the tenant id, and an API key for the load tests. All names are
fictional (the Phase 3 catalog generator); the figures describe a synthetic workload, not real data.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import random
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

SOURCES = {
    "epa_echo": ["environmental"], "osha": ["workplace_safety"], "nhtsa": ["recall"], "cpsc": ["recall"],
    "openfda": ["food_safety", "drug_enforcement"], "news": ["plant_incident", "lawsuit", "bankruptcy", "data_breach"],
}
STATES = ["OH", "TX", "PA", "CA", "MI", "NY", "TN", "NC", "IL", "GA", "FL", "NJ", "IN", "WI", "MO"]


def _copy(conn: psycopg.Connection, table: str, columns: str, rows: list[tuple]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(["\\N" if v is None else v for v in r])
    with conn.cursor().copy(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:  # nosec B608
        cp.write(buf.getvalue())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("admin_url")
    ap.add_argument("--companies", type=int, default=20_000)
    ap.add_argument("--events", type=int, default=60_000)
    ap.add_argument("--suppliers", type=int, default=3_000)
    ap.add_argument("--db", default="perf10")
    a = ap.parse_args()
    rng = random.Random(42)  # nosec B311
    admin = a.admin_url.replace("postgresql+psycopg://", "postgresql://")
    base = admin.rsplit("/", 1)[0]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{a.db}" WITH (FORCE)')  # nosec B608
        c.execute(f'CREATE DATABASE "{a.db}"')  # nosec B608
    url = f"{base}/{a.db}"
    os.environ["DATABASE_URL"] = url
    cfg = Config("apps/api/alembic.ini")
    cfg.set_main_option("script_location", "apps/api/migrations")
    command.upgrade(cfg, "head")

    from app.analytics.loader import load_business_data
    from app.analytics.revenue import refresh_views
    from app.auth.passwords import PasswordService
    from app.auth.tokens import new_api_key
    from app.kb.normalize import normalize_name
    from app.resolution.synthetic import generate_catalog
    from app.settings import Settings
    from psycopg.rows import dict_row

    from data.scripts.generate_demo_business_data import generate

    tmp = Path(tempfile.mkdtemp())
    generate(tmp)
    catalog = generate_catalog(a.companies)
    now = datetime.now(UTC)
    with psycopg.connect(url, row_factory=dict_row) as conn:
        load_business_data(conn, tmp)
        refresh_views(conn)
        with (tmp / "tenants.csv").open() as fh:
            tenant = next(t for t in csv.DictReader(fh) if not t["churned_at"])["id"]
        pw = PasswordService(Settings(argon_time_cost=1, argon_memory_kib=64, argon_parallelism=1)).hash("unused-perf-password")
        conn.execute("INSERT INTO users (tenant_id, email, password_hash, role) VALUES (%s,'perf@perf.example',%s,'manager')", (tenant, pw))
        key, prefix, secret_hash = new_api_key()
        conn.execute("INSERT INTO api_keys (tenant_id, prefix, secret_hash, name, scopes, expires_at) VALUES (%s,%s,%s,'perf',%s,%s)",
                     (tenant, prefix, secret_hash, ["view", "upload_review", "alert_action", "manage_rules"], now + timedelta(days=30)))
        conn.commit()

        recs = catalog.records
        _copy(conn, "companies", "canonical_name, normalized_name, cik, hq_state, hq_city, sic_code, is_public",
              [(r.name, normalize_name(r.name), r.cik, r.hq_state, r.hq_city, r.sic_code, str(r.is_public).lower()) for r in recs])
        _copy(conn, "company_relationships", "parent_id, child_id, rel_type, source, as_of",
              [(p, ch, "direct_parent", "gleif", "2026-06-30") for p, ch in catalog.edges])
        _copy(conn, "facilities", "registry_id, name, normalized_name, city, state, latitude, longitude, source, company_id, link_method, link_confidence",
              [(f"F{r.id}", f"{r.name} plant", normalize_name(r.name), r.hq_city, r.hq_state, round(rng.uniform(26, 48), 4),
                round(rng.uniform(-122, -72), 4), "epa_echo", r.id, "hybrid", 0.9) for r in recs if rng.random() < 0.4])

        ev_rows, ent_rows = [], []
        for i in range(a.events):
            src = rng.choice(list(SOURCES))
            et = rng.choice(SOURCES[src])
            st = rng.choice(STATES)
            at = now - timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23))
            co = rng.choice(recs)
            ev_rows.append((src, f"perf-{i}", et, rng.choices([1, 2, 3, 4], [30, 35, 25, 10])[0], at.isoformat(), at.isoformat(),
                            f"{src.upper()} record: {co.name}", f"Synthetic record {i} for {co.name}.", f"https://example.org/r/{i}",
                            st, co.hq_city, round(rng.uniform(26, 48), 4), round(rng.uniform(-122, -72), 4), "{}"))
            ent_rows.append((i + 1, co.id, "operator", "hybrid", round(rng.uniform(0.7, 0.99), 3), "accepted"))
        _copy(conn, "events", "source, source_id, event_type, severity, occurred_at, reported_at, title, summary, url, state, city, latitude, longitude, raw_ref", ev_rows)
        _copy(conn, "event_entities", "event_id, company_id, role, method, score, route", ent_rows)
        _copy(conn, "link_candidates", "event_entity_id, rank, company_id, bela_score, blink_score, splink_score, llm_label",
              [(i + 1, k + 1, rng.choice(recs).id, 0.8 / (k + 1), 0.7 / (k + 1), 9.0 / (k + 1), "match" if k == 0 else "no_match")
               for i in range(0, a.events, 5) for k in range(3)])

        chosen = rng.sample(recs, min(a.suppliers, len(recs)))
        _copy(conn, "suppliers", "tenant_id, uploaded_name, attributes, tier, status, resolved_company_id, confidence, resolution_detail",
              [(tenant, r.name.upper(), json.dumps({"state": r.hq_state, "city": r.hq_city}), rng.choice(["tier_1", "tier_2", "tier_3"]),
                "auto_resolved", r.id, 0.97, json.dumps({"route": "accepted", "method": "hybrid"})) for r in chosen])
        conn.execute("ANALYZE")
        conn.commit()
    print(json.dumps({"database_url": url, "tenant_id": tenant, "api_key": key, "companies": len(recs), "events": a.events,
                      "suppliers": len(chosen)}))


if __name__ == "__main__":
    main()
