"""Seed the demo environment: synthetic business data, a fictional company catalog with ownership edges,
facilities and events, one account per role, and a supplier list resolved through the running API.

Usage (the database must already be migrated):
    PYTHONPATH=.:apps/api python infra/demo/seed_demo.py --database-url URL [--api-url http://api:8000]

Step 1 writes to the database. Step 2 (only with --api-url) signs in as the demo manager, uploads a messy
supplier list so the real resolution pipeline runs, and rescores the portfolio.

Every account gets a generated password. The passwords are printed once, at the end of this run, and only their
Argon2id hashes are stored. Nothing is written to disk. Lose them and run `make demo-reset`.

All company names are fictional (the Phase 3 catalog generator) and all events are synthetic. The demo says so
on screen when DEMO_MODE=true.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import secrets
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg

SOURCES = {
    "epa_echo": ["environmental"], "osha": ["workplace_safety"], "nhtsa": ["recall"], "cpsc": ["recall"],
    "openfda": ["food_safety", "drug_enforcement"], "news": ["plant_incident", "lawsuit", "bankruptcy", "data_breach"],
}
STATES = ["OH", "TX", "PA", "CA", "MI", "NY", "TN", "NC", "IL", "GA", "FL", "NJ", "IN", "WI", "MO"]
TIERS = ["tier_1", "tier_2", "tier_3"]
# (email, role, tenant scoped, note)
ACCOUNTS = [
    ("viewer@demo.example", "viewer", True, "read-only role used for the public demo"),
    ("analyst@demo.example", "analyst", True, "uploads, reviews matches, acts on alerts"),
    ("manager@demo.example", "manager", True, "also manages rules, analytics, and reports"),
    ("admin@demo.example", "tenant_admin", True, "users, API keys, risk settings, audit log (sets up MFA at first sign-in)"),
    ("finance@demo.example", "finance_analyst", False, "revenue and billing analytics"),
    ("platform@demo.example", "platform_admin", False, "tenants and the platform review queue (sets up MFA at first sign-in)"),
]
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alike characters


def new_password() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _copy(conn: psycopg.Connection, table: str, columns: str, rows: list[tuple]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(["\\N" if v is None else v for v in r])
    with conn.cursor().copy(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:  # nosec B608
        cp.write(buf.getvalue())


def degrade(name: str, rng: random.Random) -> str:
    """The kind of noise a real supplier list has: case, dropped suffixes, abbreviations, typos."""
    out = name
    r = rng.random()
    if r < 0.25:
        out = out.upper()
    elif r < 0.45:
        for suf in (" Inc.", " Inc", " LLC", " Corporation", " Corp.", " Co.", " Company", " Group", " Holdings"):
            if out.endswith(suf):
                out = out[: -len(suf)]
                break
    elif r < 0.65:
        out = out.replace("Corporation", "Corp").replace("Company", "Co").replace("Incorporated", "Inc")
    elif r < 0.8 and len(out) > 6:
        i = rng.randrange(2, len(out) - 2)
        out = out[:i] + out[i + 1:]
    return out


def seed_database(url: str, companies: int, events: int, suppliers: int) -> dict[str, str]:
    """Write the demo data. Returns the generated passwords by email. Refuses to run on a seeded database."""
    from app.analytics.loader import load_business_data
    from app.analytics.revenue import refresh_views
    from app.auth.passwords import PasswordService
    from app.kb.normalize import normalize_name
    from app.resolution.synthetic import generate_catalog
    from app.settings import Settings
    from psycopg.rows import dict_row

    from data.scripts.generate_demo_business_data import generate

    rng = random.Random(2026)  # nosec B311
    work = Path(tempfile.mkdtemp())
    generate(work)
    catalog = generate_catalog(companies)
    recs = catalog.records
    now = datetime.now(UTC)
    hasher = PasswordService(Settings.from_env())
    passwords: dict[str, str] = {}

    with psycopg.connect(url, row_factory=dict_row) as conn:
        if conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"]:
            raise SystemExit("this database already has users; run `make demo-reset` to start again")
        load_business_data(conn, work)
        refresh_views(conn)
        with (work / "tenants.csv").open(newline="", encoding="utf-8") as fh:
            tenant = next(t for t in csv.DictReader(fh) if not t["churned_at"])["id"]
        for email, role, scoped, _ in ACCOUNTS:
            pw = new_password()
            passwords[email] = pw
            conn.execute("INSERT INTO users (tenant_id, email, password_hash, role) VALUES (%s,%s,%s,%s)",
                         (tenant if scoped else None, email, hasher.hash(pw), role))

        _copy(conn, "companies", "canonical_name, normalized_name, cik, hq_state, hq_city, sic_code, is_public",
              [(r.name, normalize_name(r.name), r.cik, r.hq_state, r.hq_city, r.sic_code, str(r.is_public).lower()) for r in recs])
        _copy(conn, "company_relationships", "parent_id, child_id, rel_type, source, as_of",
              [(p, c, "direct_parent", "gleif", "2026-06-30") for p, c in catalog.edges])
        _copy(conn, "facilities", "registry_id, name, normalized_name, city, state, latitude, longitude, source, company_id, link_method, link_confidence",
              [(f"F{r.id}", f"{r.name} plant", normalize_name(r.name), r.hq_city, r.hq_state, round(rng.uniform(26, 48), 4),
                round(rng.uniform(-122, -72), 4), "epa_echo", r.id, "hybrid", 0.9) for r in recs if rng.random() < 0.4])

        # About a third of the events land on the companies that will become suppliers, so the portfolio has signal.
        chosen = rng.sample(recs, min(suppliers, len(recs)))
        ev_rows, ent_rows = [], []
        for i in range(events):
            src = rng.choice(list(SOURCES))
            et = rng.choice(SOURCES[src])
            at = now - timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23))
            co = rng.choice(chosen) if rng.random() < 0.35 else rng.choice(recs)
            ev_rows.append((src, f"demo-{i}", et, rng.choices([1, 2, 3, 4], [30, 35, 25, 10])[0], at.isoformat(), at.isoformat(),
                            f"{src.upper()} record: {co.name}", f"Synthetic record {i} for {co.name}.", f"https://example.org/r/{i}",
                            co.hq_state, co.hq_city, round(rng.uniform(26, 48), 4), round(rng.uniform(-122, -72), 4), "{}"))
            ent_rows.append((i + 1, co.id, "operator", "hybrid", round(rng.uniform(0.7, 0.99), 3), "accepted"))
        _copy(conn, "events", "source, source_id, event_type, severity, occurred_at, reported_at, title, summary, url, state, city, latitude, longitude, raw_ref", ev_rows)
        _copy(conn, "event_entities", "event_id, company_id, role, method, score, route", ent_rows)
        _copy(conn, "link_candidates", "event_entity_id, rank, company_id, bela_score, blink_score, splink_score, llm_label",
              [(i + 1, k + 1, rng.choice(recs).id, 0.8 / (k + 1), 0.7 / (k + 1), 9.0 / (k + 1), "match" if k == 0 else "no_match")
               for i in range(0, events, 5) for k in range(3)])
        conn.execute("ANALYZE")
        conn.commit()

    (work / "suppliers.csv").write_text(
        "name,city,state,tier\n" + "\n".join(
            f'"{degrade(r.name, rng)}",{r.hq_city},{r.hq_state},{rng.choice(TIERS)}' for r in chosen) + "\n",
        encoding="utf-8")
    SUPPLIER_CSV.write_text((work / "suppliers.csv").read_text(encoding="utf-8"), encoding="utf-8")
    return passwords


SUPPLIER_CSV = Path(tempfile.gettempdir()) / "demo_suppliers.csv"


def seed_suppliers(api_url: str, password: str, wait_s: int = 600) -> None:
    """Upload the supplier list as the demo manager so the real resolution pipeline processes it."""
    with httpx.Client(base_url=f"{api_url}/api/v1", timeout=60) as c:
        r = c.post("/auth/login", json={"email": "manager@demo.example", "password": password})
        r.raise_for_status()
        h = {"X-CSRF-Token": c.cookies.get("pr_csrf") or ""}
        up = c.post("/uploads", headers=h, files={"file": ("suppliers.csv", SUPPLIER_CSV.read_bytes(), "text/csv")})
        up.raise_for_status()
        uid = up.json()["id"]
        deadline = time.time() + wait_s
        s: dict = {}
        while time.time() < deadline:
            s = c.get(f"/uploads/{uid}").json()
            if s["status"] in ("complete", "completed", "failed", "done"):
                break
            time.sleep(1)
        print(f"upload {s.get('status')}: " + ", ".join(f"{k}={s.get(k)}" for k in ("auto_resolved", "needs_review", "unresolved")))
        if s.get("status") == "failed":
            raise SystemExit("the supplier upload failed; see the API log")
        rec = c.post("/monitoring/recompute", headers=h, timeout=300)
        rec.raise_for_status()
        print("portfolio rescored:", json.dumps(rec.json())[:160])


def print_credentials(passwords: dict[str, str], web_url: str) -> None:
    print("\n" + "=" * 78)
    print("DEMO ACCOUNTS. These passwords are shown once and are not stored anywhere in readable form.")
    print(f"Sign in at {web_url}/login\n")
    for email, role, _, note in ACCOUNTS:
        print(f"  {email:<24} {passwords[email]}   {role}: {note}")
    print("=" * 78 + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--api-url", help="when set, also upload the supplier list through this API")
    ap.add_argument("--web-url", default="https://localhost")
    ap.add_argument("--companies", type=int, default=1500)
    ap.add_argument("--events", type=int, default=3000)
    ap.add_argument("--suppliers", type=int, default=250)
    a = ap.parse_args()
    url = a.database_url.replace("postgresql+psycopg://", "postgresql://")
    passwords = seed_database(url, a.companies, a.events, a.suppliers)
    if a.api_url:
        seed_suppliers(a.api_url, passwords["manager@demo.example"])
    print_credentials(passwords, a.web_url)


if __name__ == "__main__":
    sys.exit(main())
