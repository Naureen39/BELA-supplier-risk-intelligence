"""Business tables and materialized views mrr_monthly, cohort_retention.

Metric definitions: MRR is the sum of monthly-equivalent recurring fees of subscriptions active
at month end (annual billing divided by 12). Overage is reported separately in invoice_lines.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE plans (
    code text PRIMARY KEY,
    name text NOT NULL,
    monthly_price numeric(12,2) NOT NULL CHECK (monthly_price >= 0),
    supplier_limit integer NOT NULL CHECK (supplier_limit > 0),
    overage_per_100 numeric(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE subscriptions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan_code text NOT NULL REFERENCES plans(code),
    billing_cycle text NOT NULL CHECK (billing_cycle IN ('monthly','annual')),
    price numeric(12,2) NOT NULL CHECK (price >= 0),  -- amount per billing cycle
    started_on date NOT NULL,
    ended_on date,
    change_reason text,
    monthly_equivalent numeric(12,2) GENERATED ALWAYS AS
        (CASE WHEN billing_cycle = 'annual' THEN round(price / 12, 2) ELSE price END) STORED,
    CHECK (ended_on IS NULL OR ended_on >= started_on)
);
CREATE INDEX subscriptions_tenant ON subscriptions (tenant_id, started_on);

CREATE TABLE invoices (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period_month date NOT NULL CHECK (period_month = date_trunc('month', period_month)::date),
    issued_on date NOT NULL,
    due_on date NOT NULL,
    status text NOT NULL CHECK (status IN ('paid','open','overdue')),
    total numeric(12,2) NOT NULL,
    UNIQUE (tenant_id, period_month)
);

CREATE TABLE invoice_lines (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id bigint NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    line_type text NOT NULL CHECK (line_type IN ('subscription','overage','credit')),
    description text,
    amount numeric(12,2) NOT NULL
);

CREATE TABLE usage_daily (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    day date NOT NULL,
    monitored_suppliers integer NOT NULL,
    resolutions integer NOT NULL,
    events_matched integer NOT NULL,
    alerts integer NOT NULL,
    api_calls integer NOT NULL,
    PRIMARY KEY (tenant_id, day)
);

CREATE TABLE portfolio_stats_daily (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    day date NOT NULL,
    risk_index numeric(5,2) NOT NULL,
    suppliers_by_level jsonb NOT NULL,
    auto_resolved integer NOT NULL,
    reviewed integer NOT NULL,
    unresolved integer NOT NULL,
    median_review_minutes numeric(8,2),
    PRIMARY KEY (tenant_id, day)
);

CREATE TABLE platform_stats_daily (
    day date PRIMARY KEY,
    p50_latency_ms numeric(8,2) NOT NULL,
    p95_latency_ms numeric(8,2) NOT NULL,
    false_links_per_1000 numeric(8,3) NOT NULL,
    review_rate numeric(6,4) NOT NULL
);

CREATE TABLE marketing_spend (
    month date NOT NULL CHECK (month = date_trunc('month', month)::date),
    channel text NOT NULL,
    spend numeric(12,2) NOT NULL CHECK (spend >= 0),
    PRIMARY KEY (month, channel)
);

CREATE TABLE business_events (
    day date NOT NULL,
    label text NOT NULL,
    PRIMARY KEY (day, label)
);

-- One row per month end and subscription-active tenant.
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

-- Revenue retention by signup cohort and months since signup.
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
       ((extract(year FROM age(t.month_start, f.cohort_month)) * 12)
        + extract(month FROM age(t.month_start, f.cohort_month)))::int AS months_since_signup,
       sum(t.mrr) AS mrr,
       round(100 * sum(t.mrr) / nullif(b.cohort_start_mrr, 0), 2) AS retention_pct
FROM first_month f
JOIN tenant_mrr t ON t.tenant_id = f.tenant_id AND t.month_start >= f.cohort_month
JOIN base b ON b.cohort_month = f.cohort_month
GROUP BY f.cohort_month, t.month_start, b.cohort_start_mrr;
CREATE UNIQUE INDEX cohort_retention_key ON cohort_retention (cohort_month, months_since_signup);
"""

DROP = """
DROP MATERIALIZED VIEW IF EXISTS cohort_retention;
DROP MATERIALIZED VIEW IF EXISTS mrr_monthly;
DROP TABLE IF EXISTS business_events, marketing_spend, platform_stats_daily,
    portfolio_stats_daily, usage_daily, invoice_lines, invoices, subscriptions, plans CASCADE;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
