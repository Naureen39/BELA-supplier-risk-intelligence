"""Product workflow tables: corrections, report status, training feedback, alert deliveries.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE reports
    ADD COLUMN status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','ready','failed')),
    ADD COLUMN error text,
    ADD COLUMN completed_at timestamptz;

ALTER TABLE suppliers ADD COLUMN duplicate_of uuid REFERENCES suppliers(id) ON DELETE SET NULL;
CREATE INDEX suppliers_duplicate_of ON suppliers (duplicate_of) WHERE duplicate_of IS NOT NULL;

CREATE TABLE corrections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    supplier_id uuid REFERENCES suppliers(id) ON DELETE SET NULL,
    event_id bigint REFERENCES events(id) ON DELETE SET NULL,
    company_id bigint REFERENCES companies(id) ON DELETE SET NULL,
    kind text NOT NULL CHECK (kind IN ('wrong_link','outdated_record','other')),
    description text NOT NULL CHECK (length(description) BETWEEN 1 AND 2000),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','accepted','rejected','closed')),
    response text,
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_by uuid REFERENCES users(id),
    decided_at timestamptz
);
CREATE INDEX corrections_tenant ON corrections (tenant_id, created_at DESC);
CREATE INDEX corrections_open ON corrections (status, created_at) WHERE status = 'open';

-- Labeled reviewer decisions for later training. No tenant identifier is stored, and rows are
-- written only for tenants that opted in (tenants.share_feedback_for_training).
CREATE TABLE training_feedback (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    query jsonb NOT NULL,
    candidates jsonb NOT NULL,
    label text NOT NULL CHECK (label IN ('match','nil','unsure')),
    label_company_id bigint REFERENCES companies(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE alert_deliveries (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_id uuid NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    rule_id uuid REFERENCES alert_rules(id) ON DELETE SET NULL,
    channel text NOT NULL CHECK (channel IN ('in_app','email','webhook')),
    status text NOT NULL CHECK (status IN ('sent','failed','skipped')),
    detail text,
    attempted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX alert_deliveries_alert ON alert_deliveries (alert_id);

ALTER TABLE corrections ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON corrections USING (tenant_id = app_tenant() OR app_is_platform())
    WITH CHECK (tenant_id = app_tenant() OR app_is_platform());
ALTER TABLE alert_deliveries ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON alert_deliveries
    USING (alert_id IN (SELECT id FROM alerts)) WITH CHECK (alert_id IN (SELECT id FROM alerts));

GRANT SELECT, INSERT ON corrections TO app_user;
GRANT SELECT ON alert_deliveries TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
""")


def downgrade() -> None:
    op.execute("""
DROP TABLE alert_deliveries, training_feedback, corrections;
DROP INDEX IF EXISTS suppliers_duplicate_of;
ALTER TABLE suppliers DROP COLUMN duplicate_of;
ALTER TABLE reports DROP COLUMN status, DROP COLUMN error, DROP COLUMN completed_at;
""")
