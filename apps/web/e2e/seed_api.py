"""Create and seed the database used by the end-to-end tests.

Usage: PYTHONPATH=.:apps/api python apps/web/e2e/seed_api.py postgresql://user@host:port/postgres
Creates database `web_e2e` (replacing it), runs the migrations, loads the synthetic business data, adds a
demo tenant (one of the generated tenants, so usage and portfolio statistics exist) with a user for each
role, a second tenant, a small company catalog with ownership edges, facilities, and events.
Prints the DATABASE_URL to start the API with. Run `seed_suppliers.py` after the API is up.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

PASSWORD = "Violet-Harbor-Quartz-7421"
RESET_TOKEN = "e2e-reset-token-0123456789"

# name, state, city, cik, parent index
COMPANIES = [
    ("Northgate Metals Corporation", "PA", "Pittsburgh", 1003, None),
    ("Northgate Metals of Texas LLC", "TX", "Houston", None, 0),
    ("Northgate Alloys Ohio Inc.", "OH", "Toledo", None, 0),
    ("Harborline Foods, Inc.", "OH", "Columbus", 1001, None),
    ("Harborline Packaging LLC", "OH", "Columbus", None, 3),
    ("Cobalt Ridge Logistics Co.", "TN", "Memphis", None, None),
    ("Summit Chemicals Corporation", "TX", "Houston", 1010, None),
    ("Summit Plastics Inc.", "MI", "Detroit", None, 6),
    ("Ironwood Motors Inc.", "MI", "Detroit", 1020, None),
    ("Lantern Pharma Labs Inc.", "NJ", "Newark", None, None),
    ("Willow Textiles Co.", "NC", "Charlotte", None, None),
    ("Quartz Energy Group", "CA", "Fresno", 1030, None),
]
# company index, source, type, severity, days ago, title, summary, state, lat, lon
EVENTS = [
    (1, "osha", "workplace_safety", 3, 6, "OSHA inspection record: Northgate Metals of Texas LLC", "Inspection record lists two citations at the Houston establishment, status contested.", "TX", 29.76, -95.37),
    (6, "epa_echo", "environmental", 3, 12, "EPA compliance record: Summit Chemicals Corporation", "Facility listed in significant noncompliance for a reporting quarter.", "TX", 29.73, -95.25),
    (8, "nhtsa", "recall", 4, 3, "NHTSA recall campaign: Ironwood Motors Inc.", "Recall of 18,400 units for a brake component, manufacturer notice filed.", "MI", 42.33, -83.05),
    (3, "openfda", "food_safety", 3, 20, "FDA enforcement report: Harborline Foods, Inc.", "Class II recall of a packaged product, voluntary firm-initiated.", "OH", 39.96, -82.99),
    (5, "news", "plant_incident", 2, 2, "Fire reported at Memphis warehouse", "Cobalt Ridge Logistics Co. said a fire at its Memphis warehouse was contained and no injuries were reported.", "TN", 35.15, -90.05),
    (2, "osha", "workplace_safety", 2, 40, "OSHA inspection record: Northgate Alloys Ohio Inc.", "Inspection closed with one other-than-serious citation.", "OH", 41.65, -83.54),
    (9, "openfda", "drug_enforcement", 3, 9, "FDA enforcement report: Lantern Pharma Labs Inc.", "Enforcement report classified as Class II for a labeling issue.", "NJ", 40.73, -74.17),
    (7, "cpsc", "recall", 3, 15, "CPSC recall: Summit Plastics Inc.", "Recall of a consumer product for a laceration hazard.", "MI", 42.36, -83.07),
]


def main(admin_url: str) -> None:
    admin_url = admin_url.replace("postgresql+psycopg://", "postgresql://")
    base = admin_url.rsplit("/", 1)[0]
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS web_e2e WITH (FORCE)")
        conn.execute("CREATE DATABASE web_e2e")
    url = f"{base}/web_e2e"
    os.environ["DATABASE_URL"] = url
    cfg = Config("apps/api/alembic.ini")
    cfg.set_main_option("script_location", "apps/api/migrations")
    command.upgrade(cfg, "head")

    from app.analytics.loader import load_business_data
    from app.analytics.revenue import refresh_views
    from app.auth.passwords import PasswordService
    from app.auth.tokens import hash_token
    from app.kb.normalize import normalize_name
    from app.settings import Settings
    from psycopg.rows import dict_row

    from data.scripts.generate_demo_business_data import generate

    pw = PasswordService(Settings(argon_time_cost=1, argon_memory_kib=64, argon_parallelism=1)).hash(PASSWORD)
    out = Path(tempfile.mkdtemp())
    generate(out)
    with psycopg.connect(url, row_factory=dict_row) as conn:
        load_business_data(conn, out)
        refresh_views(conn)
        with (out / "tenants.csv").open() as fh:
            demo = next(t for t in csv.DictReader(fh) if not t["churned_at"])["id"]
        other = conn.execute("INSERT INTO tenants (name) VALUES ('Other Tenant') RETURNING id").fetchone()["id"]
        users = {}
        for email, role, tenant in (
            ("viewer@demo.example", "viewer", demo), ("analyst@demo.example", "analyst", demo),
            ("manager@demo.example", "manager", demo), ("admin@demo.example", "tenant_admin", demo), ("admin2@demo.example", "tenant_admin", demo),
            ("reset@demo.example", "viewer", demo), ("manager@other.example", "manager", other),
            ("finance@demo.example", "finance_analyst", None), ("platform@demo.example", "platform_admin", None),
        ):
            users[email] = conn.execute(
                "INSERT INTO users (tenant_id, email, password_hash, role) VALUES (%s,%s,%s,%s) RETURNING id",
                (tenant, email, pw, role)).fetchone()["id"]
        conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s,%s,%s)",
                     (users["reset@demo.example"], hash_token(RESET_TOKEN), datetime.now(UTC) + timedelta(hours=2)))

        ids = []
        for name, state, city, cik, _ in COMPANIES:
            ids.append(conn.execute(
                "INSERT INTO companies (canonical_name, normalized_name, cik, hq_state, hq_city, is_public) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (name, normalize_name(name), cik, state, city, cik is not None)).fetchone()["id"])
        for i, (_, _, _, _, parent) in enumerate(COMPANIES):
            if parent is not None:
                conn.execute("INSERT INTO company_relationships (parent_id, child_id, rel_type, source, as_of) "
                             "VALUES (%s,%s,'direct_parent','gleif','2026-06-30')", (ids[parent], ids[i]))
        now = datetime.now(UTC)
        for n, (ci, source, etype, sev, days, title, summary, state, lat, lon) in enumerate(EVENTS):
            ev = conn.execute(
                "INSERT INTO events (source, source_id, event_type, severity, reported_at, title, summary, url, "
                "state, latitude, longitude, raw_ref) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id",
                (source, f"seed-{n}", etype, sev, now - timedelta(days=days), title, summary,
                 f"https://example.org/records/{source}/{n}", state, lat, lon,
                 json.dumps({"program_id": f"demo-{n}", "status": "contested"}))).fetchone()["id"]
            ee = conn.execute(
                "INSERT INTO event_entities (event_id, company_id, role, method, score, route) "
                "VALUES (%s,%s,'operator','hybrid',0.93,'accepted') RETURNING id", (ev, ids[ci])).fetchone()["id"]
            for rank, cid in enumerate([ids[ci], ids[(ci + 1) % len(ids)]], start=1):
                conn.execute("INSERT INTO link_candidates (event_entity_id, rank, company_id, bela_score, "
                             "blink_score, splink_score, llm_label) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                             (ee, rank, cid, 0.9 / rank, 0.85 / rank, 11.0 / rank, "match" if rank == 1 else "no_match"))
            conn.execute(
                "INSERT INTO facilities (registry_id, name, normalized_name, city, state, latitude, longitude, "
                "source, company_id, link_method, link_confidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'hybrid',0.9)",
                (f"FAC-{n}", COMPANIES[ci][0] + " plant", normalize_name(COMPANIES[ci][0]), COMPANIES[ci][2],
                 state, lat, lon, source, ids[ci]))
        # Two uploaded rows the matcher was unsure about, so the review queue has work in it.
        for name, state, ci, prob in (("Northgate Metals", "PA", 0, 0.62), ("Summit Chemical Co", "TX", 6, 0.58)):
            sid = conn.execute(
                "INSERT INTO suppliers (tenant_id, uploaded_name, attributes, tier, status, confidence, resolution_detail) "
                "VALUES (%s,%s,%s::jsonb,'tier_2','needs_review',%s,'{\"route\": \"review\", \"method\": \"hybrid\"}') "
                "RETURNING id", (demo, name, json.dumps({"state": state}), prob)).fetchone()["id"]
            cands = [{"company_id": ids[(ci + k) % len(ids)], "name": COMPANIES[(ci + k) % len(ids)][0],
                      "probability": round(prob - 0.2 * k, 2), "sources": ["trigram"],
                      "scores": {"retrieval": 0.8 - 0.2 * k, "splink_weight": 4.0 - k, "blink": None},
                      "features": {"name_token_sort": 0.82 - 0.2 * k, "state_agree": 1.0 if k == 0 else 0.0}}
                     for k in range(3)]
            conn.execute("INSERT INTO resolution_reviews (tenant_id, supplier_id, candidates) VALUES (%s,%s,%s::jsonb)",
                         (demo, sid, json.dumps(cands)))
        conn.commit()
    print(url)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.environ["E2E_ADMIN_URL"])
