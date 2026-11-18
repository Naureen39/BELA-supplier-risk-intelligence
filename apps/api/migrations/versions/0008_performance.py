"""Indexes found missing by the Phase 10 query profile.

Measured on a synthetic database (20,000 companies, 60,000 events, 3,000 suppliers): the generic plans of
the slowest queries showed sequential scans on risk_score_components and link_candidates (looked up by their
parent id) and on companies (prefix and ticker arms of the company search). See docs/perf.md.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE INDEX IF NOT EXISTS risk_score_components_score ON risk_score_components (risk_score_id);
CREATE INDEX IF NOT EXISTS link_candidates_entity ON link_candidates (event_entity_id, rank);
CREATE INDEX IF NOT EXISTS companies_tickers ON companies USING gin (tickers);
CREATE INDEX IF NOT EXISTS companies_norm_prefix ON companies (normalized_name text_pattern_ops);
CREATE INDEX IF NOT EXISTS resolution_reviews_open ON resolution_reviews (tenant_id, created_at, id) WHERE status = 'open';

-- The list queries sort by (created_at DESC, id DESC). The original indexes ended in a plain `id`, so the planner
-- could not read a page straight from them: a bulk upload gives thousands of rows the same created_at, and it had
-- to read all of them to order by id. Same columns, matching direction.
DROP INDEX IF EXISTS suppliers_tenant_created;
CREATE INDEX suppliers_tenant_created ON suppliers (tenant_id, created_at DESC, id DESC);
DROP INDEX IF EXISTS alerts_tenant_created;
CREATE INDEX alerts_tenant_created ON alerts (tenant_id, created_at DESC, id DESC);
""")


def downgrade() -> None:
    op.execute("""
DROP INDEX IF EXISTS risk_score_components_score, link_candidates_entity, companies_tickers,
    companies_norm_prefix, resolution_reviews_open, suppliers_tenant_created, alerts_tenant_created;
CREATE INDEX suppliers_tenant_created ON suppliers (tenant_id, created_at DESC, id);
CREATE INDEX alerts_tenant_created ON alerts (tenant_id, created_at DESC, id);
""")
