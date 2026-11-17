"""Public site: newsletter subscribers with double opt-in.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE newsletter_subscribers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    token_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz
);
CREATE UNIQUE INDEX newsletter_email ON newsletter_subscribers (lower(email));
CREATE UNIQUE INDEX newsletter_token ON newsletter_subscribers (token_hash);
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS newsletter_subscribers")
