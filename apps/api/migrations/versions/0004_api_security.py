"""API tables, row level security, and the restricted application role.

Revision ID: 0004
Revises: 0003

Design: authentication and platform jobs connect as the table owner (the "system" connection).
Tenant requests run `SET LOCAL ROLE app_user` plus `SET LOCAL app.tenant_id`, so row level security
policies bind every tenant query. app_user can only read global tables and has no access to
refresh tokens, MFA secrets, or reset tokens.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "users", "api_keys", "supplier_uploads", "suppliers", "resolution_reviews", "risk_scores",
    "alert_rules", "alerts", "reports", "subscriptions", "invoices", "usage_daily",
    "portfolio_stats_daily", "risk_configs", "audit_log",
)
# (child table, SQL joining to the parent that carries tenant_id)
CHILD_POLICIES = (
    ("alert_events", "alert_id IN (SELECT id FROM alerts)"),
    ("risk_score_components", "risk_score_id IN (SELECT id FROM risk_scores)"),
    ("invoice_lines", "invoice_id IN (SELECT id FROM invoices)"),
)
GLOBAL_READ = (
    "companies", "company_aliases", "company_relationships", "facilities", "events",
    "event_entities", "link_candidates", "articles", "mentions", "plans", "source_records",
    "platform_stats_daily", "marketing_spend", "business_events", "mrr_monthly", "cohort_retention",
)
WRITE = {
    "users": "SELECT, INSERT, UPDATE", "api_keys": "SELECT, INSERT, UPDATE",
    "supplier_uploads": "SELECT, INSERT, UPDATE", "suppliers": "SELECT, INSERT, UPDATE, DELETE",
    "resolution_reviews": "SELECT, INSERT, UPDATE", "risk_scores": "SELECT, INSERT",
    "risk_score_components": "SELECT, INSERT", "alert_rules": "SELECT, INSERT, UPDATE, DELETE",
    "alerts": "SELECT, INSERT, UPDATE", "alert_events": "SELECT, INSERT",
    "reports": "SELECT, INSERT, UPDATE", "risk_configs": "SELECT, INSERT",
    "subscriptions": "SELECT", "invoices": "SELECT", "invoice_lines": "SELECT",
    "usage_daily": "SELECT", "portfolio_stats_daily": "SELECT", "audit_log": "SELECT",
    "tenants": "SELECT, UPDATE",
}

TENANT_POLICY = "tenant_id = app_tenant() OR app_is_platform()"


def upgrade() -> None:
    op.execute("""
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user NOLOGIN;
  END IF;
END $$;

ALTER TABLE user_mfa ADD COLUMN last_used_step bigint;

CREATE TABLE password_reset_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used_at timestamptz
);

CREATE TABLE risk_configs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    version integer NOT NULL,
    config jsonb NOT NULL,
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, version)
);

CREATE TABLE demo_requests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    work_email text NOT NULL,
    organization text NOT NULL,
    role text,
    industry text,
    message text,
    consent boolean NOT NULL CHECK (consent),
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE supplier_uploads ADD COLUMN errors jsonb NOT NULL DEFAULT '[]';
ALTER TABLE alerts ADD COLUMN detail text, ADD COLUMN dedup_key text,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
CREATE UNIQUE INDEX alerts_dedup ON alerts (tenant_id, dedup_key) WHERE dedup_key IS NOT NULL;
CREATE INDEX alerts_tenant_created ON alerts (tenant_id, created_at DESC, id);
CREATE INDEX suppliers_tenant_created ON suppliers (tenant_id, created_at DESC, id);
CREATE UNIQUE INDEX api_keys_prefix_idx ON api_keys (prefix);

CREATE FUNCTION app_tenant() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;
CREATE FUNCTION app_is_platform() RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(current_setting('app.platform', true), '') = 'on' $$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
""")
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING ({TENANT_POLICY}) "
                   f"WITH CHECK ({TENANT_POLICY})")
    for t, cond in CHILD_POLICIES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING ({cond}) WITH CHECK ({cond})")
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON tenants USING (id = app_tenant() OR "
               "app_is_platform()) WITH CHECK (id = app_tenant() OR app_is_platform())")
    for t in GLOBAL_READ:
        op.execute(f"GRANT SELECT ON {t} TO app_user")
    for t, privs in WRITE.items():
        op.execute(f"GRANT {privs} ON {t} TO app_user")


def downgrade() -> None:
    for t, _ in CHILD_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    for t in (*TENANT_TABLES, "tenants"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute("""
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_user;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM app_user;
REVOKE ALL ON SCHEMA public FROM app_user;
DROP INDEX IF EXISTS api_keys_prefix_idx, suppliers_tenant_created, alerts_tenant_created, alerts_dedup;
ALTER TABLE supplier_uploads DROP COLUMN errors;
ALTER TABLE alerts DROP COLUMN detail, DROP COLUMN dedup_key, DROP COLUMN updated_at;
DROP TABLE demo_requests, risk_configs, password_reset_tokens;
ALTER TABLE user_mfa DROP COLUMN last_used_step;
DROP FUNCTION app_is_platform(), app_tenant();
""")
