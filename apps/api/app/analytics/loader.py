"""Load the synthetic business dataset and refresh the revenue views.

Usage:
    python -m app.analytics.loader --dir data/synthetic          # load, then refresh
    python -m app.analytics.loader --refresh-only                # nightly job

Loading replaces the demo tenants listed in tenants.csv (and everything that belongs to them) and
the global demo tables. It runs in one transaction with the owner role. Demo data only.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.analytics.revenue import refresh_views
from app.db import normalize_url

DEFAULT_DIR = Path(__file__).resolve().parents[4] / "data" / "synthetic"

# file -> (table, columns in CSV order). Generated and identity columns are not listed.
COPY_PLAN: tuple[tuple[str, str, str], ...] = (
    ("tenants.csv", "tenants",
     "id, name, industry, region, country, created_at, churned_at, acquisition_channel"),
    ("subscriptions.csv", "subscriptions",
     "tenant_id, plan_code, billing_cycle, price, started_on, ended_on, change_reason"),
    ("invoices.csv", "invoices", "tenant_id, period_month, issued_on, due_on, status, total"),
    ("usage_daily.csv", "usage_daily",
     "tenant_id, day, monitored_suppliers, resolutions, events_matched, alerts, api_calls"),
    ("portfolio_stats_daily.csv", "portfolio_stats_daily",
     "tenant_id, day, risk_index, suppliers_by_level, auto_resolved, reviewed, unresolved, "
     "median_review_minutes"),
    ("platform_stats_daily.csv", "platform_stats_daily",
     "day, p50_latency_ms, p95_latency_ms, false_links_per_1000, review_rate, throughput_rps"),
    ("marketing_spend.csv", "marketing_spend", "month, channel, spend"),
    ("business_events.csv", "business_events", "day, label"),
)
GLOBAL_TABLES = ("platform_stats_daily", "marketing_spend", "business_events")


def _copy(conn: Any, path: Path, table: str, columns: str) -> int:
    with path.open("rb") as fh, conn.cursor().copy(
            f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')") as cp:
        while chunk := fh.read(1 << 20):
            cp.write(chunk)
    return int(conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"])


def _plans(conn: Any, path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        conn.execute(
            "INSERT INTO plans (code, name, monthly_price, supplier_limit, overage_per_100) "
            "VALUES (%(code)s, %(name)s, %(monthly_price)s, %(supplier_limit)s, %(overage_per_100)s) "
            "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, monthly_price = EXCLUDED.monthly_price, "
            "supplier_limit = EXCLUDED.supplier_limit, overage_per_100 = EXCLUDED.overage_per_100", r)
    return len(rows)


def load_business_data(conn: Any, directory: Path = DEFAULT_DIR) -> dict[str, int]:
    """Load every CSV in `directory`. The caller owns the transaction."""
    missing = [f for f, _, _ in COPY_PLAN if not (directory / f).exists()]
    missing += [f for f in ("plans.csv", "invoice_lines.csv") if not (directory / f).exists()]
    if missing:
        raise FileNotFoundError(f"missing in {directory}: {', '.join(missing)}. "
                                "Run data.scripts.generate_demo_business_data first.")
    counts = {"plans": _plans(conn, directory / "plans.csv")}
    with (directory / "tenants.csv").open(newline="", encoding="utf-8") as fh:
        ids = [r["id"] for r in csv.DictReader(fh)]
    conn.execute("DELETE FROM tenants WHERE id = ANY(%s::uuid[])", (ids,))
    for table in GLOBAL_TABLES:
        conn.execute(f"DELETE FROM {table}")
    for fname, table, columns in COPY_PLAN:
        _copy(conn, directory / fname, table, columns)
        counts[table] = int(conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"])
    conn.execute("CREATE TEMP TABLE stage_lines (tenant_id uuid, period_month date, line_type text, "
                 "description text, amount numeric(12,2)) ON COMMIT DROP")
    _copy(conn, directory / "invoice_lines.csv", "stage_lines",
          "tenant_id, period_month, line_type, description, amount")
    conn.execute("INSERT INTO invoice_lines (invoice_id, line_type, description, amount) "
                 "SELECT i.id, s.line_type, s.description, s.amount FROM stage_lines s "
                 "JOIN invoices i ON i.tenant_id = s.tenant_id AND i.period_month = s.period_month")
    counts["invoice_lines"] = int(conn.execute("SELECT count(*) AS n FROM invoice_lines").fetchone()["n"])
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--refresh-only", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set.")
    with psycopg.connect(normalize_url(url).replace("postgresql+psycopg://", "postgresql://"),
                         row_factory=dict_row) as conn:
        if not args.refresh_only:
            for name, n in load_business_data(conn, args.dir).items():
                print(f"{name}: {n} rows")
        for name, n in refresh_views(conn).items():
            print(f"refreshed {name}: {n} rows")


if __name__ == "__main__":
    main()
