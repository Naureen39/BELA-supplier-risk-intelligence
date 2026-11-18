"""Dead letter queue: work that failed after its retries, kept for a platform administrator to retry or discard.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE dead_letters (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('upload','webhook','email','ingest')),
    tenant_id uuid REFERENCES tenants(id) ON DELETE SET NULL,
    reference text,
    payload jsonb NOT NULL DEFAULT '{}',
    error text NOT NULL,
    attempts integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','retried','discarded')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);
CREATE INDEX dead_letters_open ON dead_letters (created_at) WHERE status = 'open';
CREATE UNIQUE INDEX dead_letters_ref ON dead_letters (kind, reference) WHERE status = 'open' AND reference IS NOT NULL;
-- Platform data: no grant to the tenant role, so only the system connection reads or writes it.
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dead_letters")
