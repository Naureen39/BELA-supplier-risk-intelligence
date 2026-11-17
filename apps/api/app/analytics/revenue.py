"""Platform revenue metrics. The definitions live in SQL here and in migration 0006 (single source
of truth, documented in docs/metrics.md). Python only slices the monthly series and shapes output.

All functions take a system connection: the revenue views hold platform data and cannot carry row
level security, so the API checks the permission and then reads with the owner connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.analytics.common import add_months, change, month_floor, plain

GROSS_MARGIN = 0.80  # fixed demo assumption, shown to the user
VIEWS = ("mrr_monthly", "mrr_movements", "cohort_retention", "revenue_by_dimension")
DIMENSIONS = ("plan", "region", "industry", "channel")


@dataclass(frozen=True)
class Filters:
    plan: str | None = None
    region: str | None = None
    industry: str | None = None

    @property
    def unfiltered(self) -> bool:
        return not (self.plan or self.region or self.industry)

    def params(self) -> dict[str, Any]:
        return {"plan": self.plan, "region": self.region, "industry": self.industry,
                "unfiltered": self.unfiltered, "margin": GROSS_MARGIN}

    def key(self) -> str:
        return f"{self.plan}|{self.region}|{self.industry}"


FILTERED = """
SELECT m.* FROM mrr_movements m JOIN tenants t ON t.id = m.tenant_id
WHERE (%(plan)s::text IS NULL OR m.plan_code = %(plan)s)
  AND (%(region)s::text IS NULL OR t.region = %(region)s)
  AND (%(industry)s::text IS NULL OR t.industry = %(industry)s)
"""

KPI_SQL = f"""
WITH f AS ({FILTERED}),
spine AS (SELECT DISTINCT month_start FROM mrr_movements),
monthly AS (
    SELECT s.month_start,
           coalesce(sum(f.mrr), 0) AS mrr,
           count(f.tenant_id) FILTER (WHERE f.mrr > 0) AS customers,
           count(f.tenant_id) FILTER (WHERE f.prev_mrr > 0) AS start_customers,
           count(f.tenant_id) FILTER (WHERE f.new_mrr > 0) AS new_logos,
           count(f.tenant_id) FILTER (WHERE f.churn_mrr > 0) AS churned_logos,
           coalesce(sum(f.new_mrr), 0) AS new_mrr,
           coalesce(sum(f.expansion_mrr), 0) AS expansion_mrr,
           coalesce(sum(f.contraction_mrr), 0) AS contraction_mrr,
           coalesce(sum(f.churn_mrr), 0) AS churn_mrr
    FROM spine s LEFT JOIN f ON f.month_start = s.month_start GROUP BY s.month_start
),
retention AS (
    SELECT (p.month_start + interval '12 months')::date AS month_start,
           sum(p.mrr) AS base, sum(least(coalesce(c.mrr, 0), p.mrr)) AS gross,
           sum(coalesce(c.mrr, 0)) AS net
    FROM f p LEFT JOIN mrr_movements c
      ON c.tenant_id = p.tenant_id AND c.month_start = (p.month_start + interval '12 months')::date
    WHERE p.mrr > 0 GROUP BY 1
),
spend AS (SELECT month AS month_start, sum(spend) AS spend FROM marketing_spend GROUP BY 1),
joined AS (
    SELECT m.*, r.base, r.gross, r.net, coalesce(sp.spend, 0) AS spend
    FROM monthly m LEFT JOIN retention r USING (month_start) LEFT JOIN spend sp USING (month_start)
),
rolled AS (
    SELECT j.*,
           sum(j.new_logos) OVER w3 AS new_logos_3m, sum(j.spend) OVER w3 AS spend_3m,
           sum(j.churned_logos) OVER w3 AS churned_3m, sum(j.start_customers) OVER w3 AS start_3m,
           sum(j.new_mrr + j.expansion_mrr) OVER w3 AS growth_3m,
           sum(j.contraction_mrr + j.churn_mrr) OVER w3 AS loss_3m
    FROM joined j WINDOW w3 AS (ORDER BY month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
)
SELECT month_start, mrr, mrr * 12 AS arr, customers, new_logos, churned_logos,
       new_mrr, expansion_mrr, contraction_mrr, churn_mrr,
       new_mrr + expansion_mrr - contraction_mrr - churn_mrr AS net_new_mrr,
       mrr / nullif(customers, 0) AS arpa,
       100 * churned_logos::numeric / nullif(start_customers, 0) AS logo_churn_pct,
       growth_3m / nullif(loss_3m, 0) AS quick_ratio,
       100 * net / nullif(base, 0) AS nrr_pct,
       100 * gross / nullif(base, 0) AS grr_pct,
       CASE WHEN %(unfiltered)s THEN spend_3m / nullif(new_logos_3m, 0) END AS cac,
       CASE WHEN %(unfiltered)s THEN (spend_3m / nullif(new_logos_3m, 0))
            / nullif(mrr / nullif(customers, 0) * %(margin)s, 0) END AS cac_payback_months,
       (mrr / nullif(customers, 0)) * %(margin)s
            / nullif(churned_3m::numeric / nullif(start_3m, 0), 0) AS ltv
FROM rolled ORDER BY month_start
"""

KPI_DEFS: tuple[tuple[str, str, str, str], ...] = (
    # key, label, unit, direction of improvement
    ("mrr", "MRR", "usd", "up"),
    ("arr", "ARR", "usd", "up"),
    ("net_new_mrr", "Net new MRR", "usd", "up"),
    ("nrr_pct", "Net revenue retention", "percent", "up"),
    ("grr_pct", "Gross revenue retention", "percent", "up"),
    ("logo_churn_pct", "Logo churn", "percent", "down"),
    ("arpa", "ARPA", "usd", "up"),
    ("customers", "Active customers", "count", "up"),
    ("quick_ratio", "Quick ratio (trailing 3 months)", "ratio", "up"),
    ("cac_payback_months", "CAC payback", "months", "down"),
)


def kpi_series(conn: Any, f: Filters) -> list[dict[str, Any]]:
    rows = [dict(r) for r in conn.execute(KPI_SQL, f.params()).fetchall()]
    for r in rows:
        ltv, cac = r.get("ltv"), r.get("cac")
        r["ltv_to_cac"] = float(ltv) / float(cac) if ltv and cac else None
    return plain(rows)


def window_months(series: list[dict[str, Any]], start: date | None, end: date | None
                  ) -> list[dict[str, Any]]:
    lo = month_floor(start).isoformat() if start else ""
    hi = month_floor(end).isoformat() if end else "9999-12-31"
    return [r for r in series if lo <= r["month_start"] <= hi]


def kpis(series: list[dict[str, Any]], start: date | None, end: date | None, compare: bool
         ) -> dict[str, Any]:
    """Each KPI at the last month of the window, its change versus the same metric one window
    earlier, and the monthly sparkline over the window."""
    win = window_months(series, start, end)
    if not win:
        return {"month": None, "items": []}
    by_month = {r["month_start"]: r for r in series}
    last = date.fromisoformat(win[-1]["month_start"])
    prev_row = by_month.get(add_months(last, -len(win)).isoformat()) if compare else None
    items = []
    for key, label, unit, better in KPI_DEFS:
        cur = win[-1].get(key)
        prev = prev_row.get(key) if prev_row else None
        items.append({
            "key": key, "label": label, "unit": unit, "better": better, "value": cur,
            "previous": prev, "change_pct": change(cur, prev),
            "sparkline": [r.get(key) for r in win]})
    return {"month": win[-1]["month_start"], "compare_month": prev_row["month_start"] if prev_row else None,
            "items": items}


# --------------------------------------------------------------------------------- breakdowns
def mrr_by_plan(conn: Any, f: Filters, start: date | None, end: date | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT m.month_start, m.plan_code, sum(m.mrr) AS mrr, count(DISTINCT m.tenant_id) AS customers "
        "FROM mrr_monthly m JOIN tenants t ON t.id = m.tenant_id "
        "WHERE (%(plan)s::text IS NULL OR m.plan_code = %(plan)s) "
        "AND (%(region)s::text IS NULL OR t.region = %(region)s) "
        "AND (%(industry)s::text IS NULL OR t.industry = %(industry)s) "
        "AND (%(start)s::date IS NULL OR m.month_start >= %(start)s::date) "
        "AND (%(end)s::date IS NULL OR m.month_start <= %(end)s::date) "
        "GROUP BY 1, 2 ORDER BY 1, 2",
        {**f.params(), "start": start and month_floor(start), "end": end and month_floor(end)}).fetchall()
    return plain([dict(r) for r in rows])


def revenue_mix(conn: Any, f: Filters, start: date | None, end: date | None) -> list[dict[str, Any]]:
    """Invoiced amounts per month: subscription, overage, and credits. Overage is not MRR."""
    rows = conn.execute(
        "SELECT i.period_month AS month_start, "
        "coalesce(sum(l.amount) FILTER (WHERE l.line_type = 'subscription'), 0) AS subscription, "
        "coalesce(sum(l.amount) FILTER (WHERE l.line_type = 'overage'), 0) AS overage, "
        "coalesce(sum(l.amount) FILTER (WHERE l.line_type = 'credit'), 0) AS credit "
        "FROM invoices i JOIN invoice_lines l ON l.invoice_id = i.id JOIN tenants t ON t.id = i.tenant_id "
        "JOIN mrr_movements m ON m.tenant_id = i.tenant_id AND m.month_start = i.period_month "
        "WHERE (%(plan)s::text IS NULL OR m.plan_code = %(plan)s) "
        "AND (%(region)s::text IS NULL OR t.region = %(region)s) "
        "AND (%(industry)s::text IS NULL OR t.industry = %(industry)s) "
        "AND (%(start)s::date IS NULL OR i.period_month >= %(start)s::date) "
        "AND (%(end)s::date IS NULL OR i.period_month <= %(end)s::date) "
        "GROUP BY 1 ORDER BY 1",
        {**f.params(), "start": start and month_floor(start), "end": end and month_floor(end)}).fetchall()
    return plain([dict(r) for r in rows])


COHORT_LIVE = """
WITH first AS (
    SELECT m.tenant_id, min(m.month_start) AS cohort_month,
           (array_agg(m.plan_code ORDER BY m.month_start))[1] AS plan_code
    FROM mrr_movements m WHERE m.new_mrr > 0 GROUP BY m.tenant_id
),
rows AS (
    SELECT fi.cohort_month, m.month_start, m.mrr
    FROM first fi JOIN mrr_movements m ON m.tenant_id = fi.tenant_id AND m.mrr > 0
                                      AND m.month_start >= fi.cohort_month
    JOIN tenants t ON t.id = fi.tenant_id
    WHERE (%(plan)s::text IS NULL OR fi.plan_code = %(plan)s)
      AND (%(region)s::text IS NULL OR t.region = %(region)s)
      AND (%(industry)s::text IS NULL OR t.industry = %(industry)s)
),
base AS (SELECT cohort_month, sum(mrr) AS base_mrr, count(*) AS cohort_size
         FROM rows WHERE month_start = cohort_month GROUP BY 1)
SELECT r.cohort_month,
       ((extract(year FROM r.month_start) - extract(year FROM r.cohort_month)) * 12
        + extract(month FROM r.month_start) - extract(month FROM r.cohort_month))::int AS months_since_signup,
       sum(r.mrr) AS mrr, round(100 * sum(r.mrr) / nullif(b.base_mrr, 0), 2) AS retention_pct,
       b.cohort_size
FROM rows r JOIN base b USING (cohort_month)
GROUP BY r.cohort_month, r.month_start, b.base_mrr, b.cohort_size ORDER BY 1, 2
"""


def cohorts(conn: Any, f: Filters, live: bool = False) -> list[dict[str, Any]]:
    if f.unfiltered and not live:
        rows = conn.execute("SELECT cohort_month, months_since_signup, mrr, retention_pct "
                            "FROM cohort_retention ORDER BY 1, 2").fetchall()
    else:
        rows = conn.execute(COHORT_LIVE, f.params()).fetchall()
    return plain([dict(r) for r in rows])


def breakdown(conn: Any, dimension: str, month: date, f: Filters, live: bool = False
              ) -> list[dict[str, Any]]:
    """MRR, ARR, customers, and share by plan, region, industry, or acquisition channel."""
    if dimension not in DIMENSIONS:
        raise ValueError(dimension)
    month = month_floor(month)
    if f.unfiltered and not live:
        rows = conn.execute(
            "SELECT value, mrr, customers FROM revenue_by_dimension WHERE dimension = %s AND month_start = %s",
            (dimension, month)).fetchall()
    else:
        col = {"plan": "m.plan_code", "region": "t.region", "industry": "t.industry",
               "channel": "t.acquisition_channel"}[dimension]  # fixed identifiers, never user input
        rows = conn.execute(
            f"SELECT coalesce({col}, 'unknown') AS value, sum(m.mrr) AS mrr, "
            "count(DISTINCT m.tenant_id) AS customers FROM mrr_movements m JOIN tenants t ON t.id = m.tenant_id "
            "WHERE m.month_start = %(month)s AND m.mrr > 0 "
            "AND (%(plan)s::text IS NULL OR m.plan_code = %(plan)s) "
            "AND (%(region)s::text IS NULL OR t.region = %(region)s) "
            "AND (%(industry)s::text IS NULL OR t.industry = %(industry)s) "
            f"GROUP BY coalesce({col}, 'unknown')", {**f.params(), "month": month}).fetchall()
    items = sorted((dict(r) for r in rows), key=lambda r: (-float(r["mrr"]), str(r["value"])))
    total = sum(float(r["mrr"]) for r in items)
    for r in items:
        r["arr"] = float(r["mrr"]) * 12
        r["share_pct"] = round(100 * float(r["mrr"]) / total, 2) if total else 0.0
    return plain(items)


def concentration(conn: Any, month: date, f: Filters, top: int = 10) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT t.id, t.name, m.plan_code, m.mrr FROM mrr_movements m JOIN tenants t ON t.id = m.tenant_id "
        "WHERE m.month_start = %(month)s AND m.mrr > 0 "
        "AND (%(plan)s::text IS NULL OR m.plan_code = %(plan)s) "
        "AND (%(region)s::text IS NULL OR t.region = %(region)s) "
        "AND (%(industry)s::text IS NULL OR t.industry = %(industry)s) ORDER BY m.mrr DESC, t.name",
        {**f.params(), "month": month_floor(month)}).fetchall()
    total = sum(float(r["mrr"]) for r in rows)
    out, running = [], 0.0
    for r in rows[:top]:
        running += float(r["mrr"])
        out.append({"tenant_id": r["id"], "name": r["name"], "plan_code": r["plan_code"],
                    "arr": float(r["mrr"]) * 12,
                    "share_pct": round(100 * float(r["mrr"]) / total, 2) if total else 0.0,
                    "cumulative_share_pct": round(100 * running / total, 2) if total else 0.0})
    return plain({"month": month_floor(month), "customers": len(rows), "total_arr": total * 12,
                  "top_share_pct": out[-1]["cumulative_share_pct"] if out else 0.0, "items": out})


def as_of_billing(conn: Any) -> date | None:
    row = conn.execute("SELECT max(issued_on) AS d FROM invoices").fetchone()
    return row["d"] if row else None


BUCKETS = (("current", 0, 0), ("1-30", 1, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, 100000))


def billing_health(conn: Any, f: Filters, as_of: date | None = None, limit: int = 100) -> dict[str, Any]:
    """Open and overdue invoices as of the latest invoice date in the data (not today's date)."""
    as_of = as_of or as_of_billing(conn)
    if as_of is None:
        return {"as_of": None, "buckets": [], "items": []}
    rows = conn.execute(
        "SELECT i.id, i.tenant_id, t.name, i.period_month, i.issued_on, i.due_on, i.status, i.total, "
        "(%(as_of)s::date - i.issued_on) AS days_outstanding, "
        "greatest(%(as_of)s::date - i.due_on, 0) AS days_overdue "
        "FROM invoices i JOIN tenants t ON t.id = i.tenant_id "
        "LEFT JOIN mrr_movements m ON m.tenant_id = i.tenant_id AND m.month_start = i.period_month "
        "WHERE i.status IN ('open','overdue') "
        "AND (%(plan)s::text IS NULL OR m.plan_code = %(plan)s) "
        "AND (%(region)s::text IS NULL OR t.region = %(region)s) "
        "AND (%(industry)s::text IS NULL OR t.industry = %(industry)s) "
        "ORDER BY days_overdue DESC, i.total DESC, i.id", {**f.params(), "as_of": as_of}).fetchall()
    buckets = []
    for label, lo, hi in BUCKETS:
        members = [r for r in rows if lo <= int(r["days_overdue"]) <= hi]
        buckets.append({"bucket": label, "invoices": len(members),
                        "amount": round(sum(float(r["total"]) for r in members), 2)})
    return plain({"as_of": as_of, "buckets": buckets, "total_outstanding": round(
        sum(float(r["total"]) for r in rows), 2), "items": [dict(r) for r in rows[:limit]]})


HEALTH_ORDER = {"over_limit": 0, "overdue": 1, "declining": 2, "healthy": 3, "churned": 4}


def customers(conn: Any, month: date, f: Filters, status: str = "active") -> list[dict[str, Any]]:
    rows = conn.execute(
        "WITH last_usage AS (SELECT DISTINCT ON (tenant_id) tenant_id, day, monitored_suppliers "
        "FROM usage_daily ORDER BY tenant_id, day DESC) "
        "SELECT t.id, t.name, t.industry, t.region, c.plan_code, coalesce(c.mrr, 0) AS mrr, "
        "pl.supplier_limit, lu.monitored_suppliers, lu.day AS last_activity, t.churned_at, "
        "(SELECT array_agg(m2.mrr ORDER BY m2.month_start) FROM mrr_movements m2 WHERE m2.tenant_id = t.id "
        "  AND m2.month_start > %(month)s - interval '12 months' AND m2.month_start <= %(month)s) AS mrr_trend, "
        "(SELECT count(*) FROM invoices i WHERE i.tenant_id = t.id AND i.status = 'overdue') AS overdue_invoices, "
        "(SELECT avg(u.api_calls) FROM usage_daily u WHERE u.tenant_id = t.id AND u.day > lu.day - 30) AS calls_recent, "
        "(SELECT avg(u.api_calls) FROM usage_daily u WHERE u.tenant_id = t.id "
        "  AND u.day > lu.day - 60 AND u.day <= lu.day - 30) AS calls_prior "
        "FROM tenants t LEFT JOIN mrr_movements c ON c.tenant_id = t.id AND c.month_start = %(month)s "
        "LEFT JOIN plans pl ON pl.code = c.plan_code LEFT JOIN last_usage lu ON lu.tenant_id = t.id "
        "WHERE EXISTS (SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.id) "
        "AND (%(plan)s::text IS NULL OR c.plan_code = %(plan)s) "
        "AND (%(region)s::text IS NULL OR t.region = %(region)s) "
        "AND (%(industry)s::text IS NULL OR t.industry = %(industry)s) LIMIT 5000",
        {**f.params(), "month": month_floor(month)}).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        active = float(d["mrr"]) > 0
        if (status == "active" and not active) or (status == "churned" and active):
            continue
        if not active:
            health = "churned"
        elif d["supplier_limit"] and d["monitored_suppliers"] and d["monitored_suppliers"] > d["supplier_limit"]:
            health = "over_limit"
        elif d["overdue_invoices"]:
            health = "overdue"
        elif d["calls_prior"] and d["calls_recent"] is not None and \
                float(d["calls_recent"]) < 0.7 * float(d["calls_prior"]):
            health = "declining"
        else:
            health = "healthy"
        d["health"] = health
        d["arr"] = float(d["mrr"]) * 12
        del d["calls_recent"], d["calls_prior"]
        out.append(d)
    return plain(out)


def customer_detail(conn: Any, tenant_id: str) -> dict[str, Any] | None:
    t = conn.execute("SELECT id, name, industry, region, country, acquisition_channel, created_at, "
                     "churned_at FROM tenants WHERE id = %s", (tenant_id,)).fetchone()
    if not t:
        return None
    subs = conn.execute("SELECT plan_code, billing_cycle, price, monthly_equivalent, started_on, ended_on, "
                        "change_reason FROM subscriptions WHERE tenant_id = %s ORDER BY started_on",
                        (tenant_id,)).fetchall()
    inv = conn.execute("SELECT period_month, issued_on, due_on, status, total FROM invoices "
                       "WHERE tenant_id = %s ORDER BY period_month DESC LIMIT 24", (tenant_id,)).fetchall()
    usage = conn.execute("SELECT day, monitored_suppliers, resolutions, events_matched, alerts, api_calls "
                         "FROM usage_daily WHERE tenant_id = %s ORDER BY day DESC LIMIT 90",
                         (tenant_id,)).fetchall()
    mrr = conn.execute("SELECT month_start, mrr, plan_code FROM mrr_movements WHERE tenant_id = %s "
                       "ORDER BY month_start", (tenant_id,)).fetchall()
    return plain({"tenant": dict(t), "subscriptions": [dict(r) for r in subs],
                  "invoices": [dict(r) for r in inv], "usage": [dict(r) for r in reversed(usage)],
                  "mrr_history": [dict(r) for r in mrr]})


def business_events(conn: Any, start: date | None, end: date | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT day, label FROM business_events WHERE (%(s)s::date IS NULL OR day >= %(s)s::date) "
        "AND (%(e)s::date IS NULL OR day <= %(e)s::date) ORDER BY day", {"s": start, "e": end}).fetchall()
    return plain([dict(r) for r in rows])


# --------------------------------------------------------------------------------- refresh
def refresh_views(conn: Any) -> dict[str, int]:
    """Rebuild the revenue views in dependency order and record when. Names come from VIEWS."""
    counts: dict[str, int] = {}
    for view in VIEWS:
        conn.execute(f"REFRESH MATERIALIZED VIEW {view}")
        n = int(conn.execute(f"SELECT count(*) AS n FROM {view}").fetchone()["n"])
        conn.execute(
            "INSERT INTO metric_refresh_log (view_name, refreshed_at, row_count) VALUES (%s, now(), %s) "
            "ON CONFLICT (view_name) DO UPDATE SET refreshed_at = now(), row_count = EXCLUDED.row_count",
            (view, n))
        counts[view] = n
    return counts


def freshness(conn: Any) -> dict[str, Any]:
    log = conn.execute("SELECT min(refreshed_at) AS refreshed_at FROM metric_refresh_log").fetchone()
    through = conn.execute("SELECT max(month_start) AS m FROM mrr_movements").fetchone()
    return plain({"views_refreshed_at": log["refreshed_at"] if log else None,
                  "data_through": through["m"] if through else None})
