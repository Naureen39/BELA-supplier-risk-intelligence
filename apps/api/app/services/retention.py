"""Scheduled purge: enforce each tenant's retention period and remove expired credentials.

    python -m app.services.retention            # purge everything that is past its period
    python -m app.services.retention --dry-run  # count only

Per tenant (`tenants.retention_days`, default 730): alerts with their history and deliveries, superseded risk
scores (the latest score of every supplier is always kept), decided resolution reviews, closed corrections, and
generated reports (rows and files). Global: expired or used refresh and reset tokens, and dead letters resolved
more than 90 days ago.

Not purged, on purpose: the audit log (append only and hash chained; it records who did what, not tenant data),
suppliers and uploads (the customer's own list, deleted on request), and events (public records, not tenant data).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.db import Database, normalize_url

DEAD_LETTER_DAYS = 90
TOKEN_GRACE_DAYS = 7


def _run(conn: Any, sql: str, params: tuple[Any, ...], dry: bool, count_sql: str | None = None) -> int:
    if dry:
        return int(conn.execute(count_sql or "SELECT 0 AS n", params).fetchone()["n"])
    return int(conn.execute(sql, params).rowcount)


def purge_tenant(conn: Any, tenant_id: str, retention_days: int, report_dir: Path, dry: bool = False) -> dict[str, int]:
    cutoff = f"now() - make_interval(days => {int(retention_days)})"  # an int, never user text
    out: dict[str, int] = {}
    out["alerts"] = _run(
        conn, f"DELETE FROM alerts WHERE tenant_id = %s AND created_at < {cutoff}", (tenant_id,), dry,  # nosec B608
        f"SELECT count(*) AS n FROM alerts WHERE tenant_id = %s AND created_at < {cutoff}")  # nosec B608
    out["risk_scores"] = _run(
        conn,
        f"DELETE FROM risk_scores r WHERE r.tenant_id = %s AND r.computed_at < {cutoff} AND EXISTS "  # nosec B608
        "(SELECT 1 FROM risk_scores n WHERE n.supplier_id = r.supplier_id AND "
        "(n.computed_at, n.id) > (r.computed_at, r.id))", (tenant_id,), dry,
        f"SELECT count(*) AS n FROM risk_scores r WHERE r.tenant_id = %s AND r.computed_at < {cutoff} AND EXISTS "  # nosec B608
        "(SELECT 1 FROM risk_scores n WHERE n.supplier_id = r.supplier_id AND "
        "(n.computed_at, n.id) > (r.computed_at, r.id))")
    out["reviews"] = _run(
        conn, f"DELETE FROM resolution_reviews WHERE tenant_id = %s AND status <> 'open' AND decided_at < {cutoff}",  # nosec B608
        (tenant_id,), dry,
        f"SELECT count(*) AS n FROM resolution_reviews WHERE tenant_id = %s AND status <> 'open' AND decided_at < {cutoff}")  # nosec B608
    out["corrections"] = _run(
        conn, f"DELETE FROM corrections WHERE tenant_id = %s AND status <> 'open' AND decided_at < {cutoff}",  # nosec B608
        (tenant_id,), dry,
        f"SELECT count(*) AS n FROM corrections WHERE tenant_id = %s AND status <> 'open' AND decided_at < {cutoff}")  # nosec B608
    old = conn.execute(f"SELECT id, storage_path FROM reports WHERE tenant_id = %s AND created_at < {cutoff}",  # nosec B608
                       (tenant_id,)).fetchall()
    out["reports"] = len(old)
    if not dry and old:
        for r in old:
            path = Path(r["storage_path"]).resolve() if r["storage_path"] else None
            if path and report_dir.resolve() in path.parents and path.is_file():  # only files under the report directory
                path.unlink()
        conn.execute("DELETE FROM reports WHERE id = ANY(%s)", ([r["id"] for r in old],))
    return out


def purge_global(conn: Any, dry: bool = False) -> dict[str, int]:
    g = f"now() - interval '{TOKEN_GRACE_DAYS} days'"
    out = {
        "refresh_tokens": _run(conn, f"DELETE FROM refresh_tokens WHERE expires_at < {g}", (), dry,  # nosec B608
                               f"SELECT count(*) AS n FROM refresh_tokens WHERE expires_at < {g}"),  # nosec B608
        "reset_tokens": _run(conn, f"DELETE FROM password_reset_tokens WHERE expires_at < {g} OR used_at < {g}", (), dry,  # nosec B608
                             f"SELECT count(*) AS n FROM password_reset_tokens WHERE expires_at < {g} OR used_at < {g}"),  # nosec B608
        "dead_letters": _run(
            conn, f"DELETE FROM dead_letters WHERE status <> 'open' AND resolved_at < now() - interval '{DEAD_LETTER_DAYS} days'",  # nosec B608
            (), dry, f"SELECT count(*) AS n FROM dead_letters WHERE status <> 'open' AND resolved_at < now() - interval '{DEAD_LETTER_DAYS} days'"),  # nosec B608
    }
    return out


def purge_all(db: Database, report_dir: Path, dry: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"dry_run": dry, "tenants": {}}
    with db.system() as conn:
        tenants = conn.execute("SELECT id, retention_days FROM tenants").fetchall()
        for t in tenants:
            counts = purge_tenant(conn, str(t["id"]), int(t["retention_days"]), report_dir, dry)
            if any(counts.values()):
                result["tenants"][str(t["id"])] = counts
        result["global"] = purge_global(conn, dry)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set.")
    print(json.dumps(purge_all(Database(normalize_url(url), 1, 2), Path(os.environ.get("REPORT_DIR", "var/reports")), a.dry_run)))


if __name__ == "__main__":
    main()
