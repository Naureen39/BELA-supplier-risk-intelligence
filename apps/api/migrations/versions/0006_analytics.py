"""Analytics: revenue views, metric refresh log, throughput column, platform-only grants.

mrr_monthly now covers the first subscription month through the latest month with billing data
(not a fixed window). mrr_movements classifies every tenant-month change as new, expansion,
contraction, or churn, so the movements of a month always sum to the MRR change of that month.

The revenue views and marketing tables are platform data. Materialized views cannot carry row
level security, so the tenant role loses direct access and the revenue API reads them with the
system connection after a permission check.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

MRR_MONTHLY = """
CREATE MATERIALIZED VIEW mrr_monthly AS
WITH bounds AS (
    SELECT date_trunc('month', min(started_on))::date AS first_month,
           date_trunc('month', greatest(max(started_on), max(ended_on),
                                        (SELECT max(period_month) FROM invoices)))::date AS last_month
    FROM subscriptions
),
months AS (
    SELECT (generate_series(first_month, last_month, interval '1 month'))::date AS month_start
    FROM bounds WHERE first_month IS NOT NULL
)
SELECT m.month_start,
       (m.month_start + interval '1 month - 1 day')::date AS month_end,
       s.tenant_id,
       s.plan_code,
       sum(s.monthly_equivalent) AS mrr
FROM months m
JOIN subscriptions s
  ON s.started_on <= (m.month_start + interval '1 month - 1 day')::date
 AND (s.ended_on IS NULL OR s.ended_on > (m.month_start + interval '1 month - 1 day')::date)
GROUP BY m.month_start, s.tenant_id, s.plan_code;
CREATE UNIQUE INDEX mrr_monthly_key ON mrr_monthly (month_start, tenant_id, plan_code);
"""

MRR_MOVEMENTS = """
CREATE MATERIALIZED VIEW mrr_movements AS
WITH tenant_month AS (
    SELECT month_start, tenant_id, sum(mrr) AS mrr, (array_agg(plan_code ORDER BY mrr DESC))[1] AS plan_code
    FROM mrr_monthly GROUP BY month_start, tenant_id
),
grid AS (
    SELECT m.month_start, t.tenant_id
    FROM (SELECT DISTINCT month_start FROM mrr_monthly) m
    CROSS JOIN (SELECT DISTINCT tenant_id FROM mrr_monthly) t
),
joined AS (
    SELECT g.month_start, g.tenant_id, coalesce(tm.mrr, 0) AS mrr, tm.plan_code
    FROM grid g LEFT JOIN tenant_month tm USING (month_start, tenant_id)
),
lagged AS (
    SELECT month_start, tenant_id, mrr, plan_code,
           coalesce(lag(mrr) OVER w, 0) AS prev_mrr, lag(plan_code) OVER w AS prev_plan
    FROM joined WINDOW w AS (PARTITION BY tenant_id ORDER BY month_start)
)
SELECT month_start, tenant_id, coalesce(plan_code, prev_plan) AS plan_code, prev_mrr, mrr,
       CASE WHEN prev_mrr = 0 AND mrr > 0 THEN mrr ELSE 0 END AS new_mrr,
       CASE WHEN prev_mrr > 0 AND mrr > prev_mrr THEN mrr - prev_mrr ELSE 0 END AS expansion_mrr,
       CASE WHEN prev_mrr > 0 AND mrr > 0 AND mrr < prev_mrr THEN prev_mrr - mrr ELSE 0 END AS contraction_mrr,
       CASE WHEN prev_mrr > 0 AND mrr = 0 THEN prev_mrr ELSE 0 END AS churn_mrr
FROM lagged WHERE mrr > 0 OR prev_mrr > 0;
CREATE UNIQUE INDEX mrr_movements_key ON mrr_movements (month_start, tenant_id);
CREATE INDEX mrr_movements_tenant ON mrr_movements (tenant_id, month_start);
"""

COHORT = """
CREATE MATERIALIZED VIEW cohort_retention AS
WITH first_month AS (
    SELECT tenant_id, date_trunc('month', min(started_on))::date AS cohort_month
    FROM subscriptions GROUP BY tenant_id
),
tenant_mrr AS (
    SELECT tenant_id, month_start, sum(mrr) AS mrr FROM mrr_monthly GROUP BY 1, 2
),
base AS (
    SELECT f.cohort_month, sum(t.mrr) AS cohort_start_mrr
    FROM first_month f JOIN tenant_mrr t
      ON t.tenant_id = f.tenant_id AND t.month_start = f.cohort_month
    GROUP BY f.cohort_month
)
SELECT f.cohort_month,
       ((extract(year FROM t.month_start) - extract(year FROM f.cohort_month)) * 12
        + extract(month FROM t.month_start) - extract(month FROM f.cohort_month))::int AS months_since_signup,
       sum(t.mrr) AS mrr,
       round(100 * sum(t.mrr) / nullif(b.cohort_start_mrr, 0), 2) AS retention_pct
FROM first_month f
JOIN tenant_mrr t ON t.tenant_id = f.tenant_id AND t.month_start >= f.cohort_month
JOIN base b ON b.cohort_month = f.cohort_month
GROUP BY f.cohort_month, t.month_start, b.cohort_start_mrr;
CREATE UNIQUE INDEX cohort_retention_key ON cohort_retention (cohort_month, months_since_signup);
"""

BY_DIMENSION = """
CREATE MATERIALIZED VIEW revenue_by_dimension AS
SELECT month_start, 'plan'::text AS dimension, plan_code AS value, sum(mrr) AS mrr,
       count(DISTINCT tenant_id) AS customers
FROM mrr_monthly GROUP BY month_start, plan_code
UNION ALL
SELECT m.month_start, 'region', coalesce(t.region, 'unknown'), sum(m.mrr), count(DISTINCT m.tenant_id)
FROM mrr_monthly m JOIN tenants t ON t.id = m.tenant_id GROUP BY m.month_start, coalesce(t.region, 'unknown')
UNION ALL
SELECT m.month_start, 'industry', coalesce(t.industry, 'unknown'), sum(m.mrr), count(DISTINCT m.tenant_id)
FROM mrr_monthly m JOIN tenants t ON t.id = m.tenant_id GROUP BY m.month_start, coalesce(t.industry, 'unknown')
UNION ALL
SELECT m.month_start, 'channel', coalesce(t.acquisition_channel, 'unknown'), sum(m.mrr),
       count(DISTINCT m.tenant_id)
FROM mrr_monthly m JOIN tenants t ON t.id = m.tenant_id
GROUP BY m.month_start, coalesce(t.acquisition_channel, 'unknown');
CREATE UNIQUE INDEX revenue_by_dimension_key ON revenue_by_dimension (month_start, dimension, value);
"""

OLD_MRR = """
CREATE MATERIALIZED VIEW mrr_monthly AS
WITH months AS (
    SELECT (generate_series(date '2023-11-01', date '2026-10-01', interval '1 month'))::date
        AS month_start
)
SELECT m.month_start,
       (m.month_start + interval '1 month - 1 day')::date AS month_end,
       s.tenant_id,
       s.plan_code,
       sum(s.monthly_equivalent) AS mrr
FROM months m
JOIN subscriptions s
  ON s.started_on <= (m.month_start + interval '1 month - 1 day')::date
 AND (s.ended_on IS NULL OR s.ended_on > (m.month_start + interval '1 month - 1 day')::date)
GROUP BY m.month_start, s.tenant_id, s.plan_code;
CREATE UNIQUE INDEX mrr_monthly_key ON mrr_monthly (month_start, tenant_id, plan_code);
"""

OLD_COHORT = COHORT.replace(
    "((extract(year FROM t.month_start) - extract(year FROM f.cohort_month)) * 12\n"
    "        + extract(month FROM t.month_start) - extract(month FROM f.cohort_month))::int",
    "((extract(year FROM age(t.month_start, f.cohort_month)) * 12)\n"
    "        + extract(month FROM age(t.month_start, f.cohort_month)))::int")


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS cohort_retention")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mrr_monthly")
    op.execute(MRR_MONTHLY)
    op.execute(MRR_MOVEMENTS)
    op.execute(COHORT)
    op.execute(BY_DIMENSION)
    op.execute("""
ALTER TABLE platform_stats_daily ADD COLUMN throughput_rps numeric(8,2);

CREATE TABLE metric_refresh_log (
    view_name text PRIMARY KEY,
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    row_count integer NOT NULL
);

CREATE INDEX invoices_period ON invoices (period_month);
CREATE INDEX invoices_status ON invoices (status) WHERE status <> 'paid';
CREATE INDEX usage_daily_day ON usage_daily (day);
CREATE INDEX portfolio_stats_day ON portfolio_stats_daily (day);
CREATE INDEX subscriptions_started ON subscriptions (started_on);

REVOKE ALL ON marketing_spend, business_events FROM app_user;
""")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS revenue_by_dimension")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mrr_movements")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS cohort_retention")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mrr_monthly")
    op.execute(OLD_MRR)
    op.execute(OLD_COHORT)
    op.execute("""
DROP INDEX IF EXISTS invoices_period, invoices_status, usage_daily_day, portfolio_stats_day,
    subscriptions_started;
DROP TABLE IF EXISTS metric_refresh_log;
ALTER TABLE platform_stats_daily DROP COLUMN IF EXISTS throughput_rps;
GRANT SELECT ON marketing_spend, business_events, mrr_monthly, cohort_retention TO app_user;
""")
