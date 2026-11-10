"""Extensions, tenancy and security tables, company knowledge tables.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Tenancy and security -----------------------------------------------------
CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    industry text,
    region text,
    country text,
    acquisition_channel text,
    retention_days integer NOT NULL DEFAULT 730,
    share_feedback_for_training boolean NOT NULL DEFAULT false,
    require_mfa boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    churned_at timestamptz
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
    email text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN
        ('viewer','analyst','manager','tenant_admin','finance_analyst','platform_admin')),
    is_active boolean NOT NULL DEFAULT true,
    failed_logins integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);
CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email));

CREATE TABLE user_mfa (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    secret_encrypted bytea NOT NULL,
    confirmed_at timestamptz,
    recovery_code_hashes text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE refresh_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id uuid NOT NULL,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    revoked_at timestamptz,
    user_agent text
);
CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id);

CREATE TABLE api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    prefix text NOT NULL UNIQUE,
    secret_hash text NOT NULL,
    name text NOT NULL,
    scopes text[] NOT NULL DEFAULT '{}',
    expires_at timestamptz,
    last_used_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Append-only, hash-chained audit log (privileges restricted in the API phase).
CREATE TABLE audit_log (
    seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    tenant_id uuid,
    actor_user_id uuid,
    action text NOT NULL,
    target_type text,
    target_id text,
    detail jsonb NOT NULL DEFAULT '{}',
    prev_hash text NOT NULL,
    row_hash text NOT NULL
);
CREATE FUNCTION audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END $$;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();

-- Company knowledge --------------------------------------------------------
CREATE TABLE companies (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name text NOT NULL,
    normalized_name text NOT NULL,
    legal_form text,
    cik bigint UNIQUE,
    lei text UNIQUE,
    wikidata_qid text UNIQUE,
    tickers text[] NOT NULL DEFAULT '{}',
    sic_code text,
    state_of_incorporation text,
    hq_city text,
    hq_state text,
    hq_country text,
    is_public boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','unknown')),
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(trim(canonical_name)) > 0)
);
CREATE INDEX companies_norm_trgm ON companies USING gin (normalized_name gin_trgm_ops);
CREATE INDEX companies_norm_state ON companies (normalized_name, hq_state);

CREATE TABLE company_aliases (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    alias text NOT NULL,
    alias_type text NOT NULL CHECK (alias_type IN
        ('legal','former','dba','subsidiary','abbreviation')),
    normalized text NOT NULL,
    source text NOT NULL,
    UNIQUE (company_id, normalized, alias_type)
);
CREATE INDEX company_aliases_norm_trgm ON company_aliases USING gin (normalized gin_trgm_ops);
CREATE INDEX company_aliases_norm ON company_aliases (normalized);

CREATE TABLE company_relationships (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    child_id bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    rel_type text NOT NULL CHECK (rel_type IN
        ('direct_parent','ultimate_parent','subsidiary','owned_by')),
    ownership_share numeric(6,3) CHECK (ownership_share BETWEEN 0 AND 100),
    source text NOT NULL,
    as_of date,
    CHECK (parent_id <> child_id),
    UNIQUE (parent_id, child_id, rel_type, source)
);
CREATE INDEX company_relationships_child ON company_relationships (child_id);

CREATE TABLE facilities (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry_id text NOT NULL UNIQUE,
    name text NOT NULL,
    normalized_name text NOT NULL,
    address text,
    city text,
    state text,
    postal_code text,
    latitude double precision CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision CHECK (longitude BETWEEN -180 AND 180),
    industry_code text,
    source text NOT NULL,
    company_id bigint REFERENCES companies(id) ON DELETE SET NULL,
    link_method text,
    link_confidence real CHECK (link_confidence BETWEEN 0 AND 1)
);
CREATE INDEX facilities_norm_trgm ON facilities USING gin (normalized_name gin_trgm_ops);
CREATE INDEX facilities_company ON facilities (company_id);
CREATE INDEX facilities_state ON facilities (state);

CREATE TABLE source_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL,
    source_key text NOT NULL,
    record_type text NOT NULL DEFAULT 'company',
    name text NOT NULL,
    state text,
    company_id bigint REFERENCES companies(id) ON DELETE CASCADE,
    method text NOT NULL,
    score real NOT NULL CHECK (score BETWEEN 0 AND 1),
    UNIQUE (source, source_key, record_type)
);
CREATE INDEX source_records_company ON source_records (company_id);

CREATE TABLE entity_embeddings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('name','alias','description')),
    text text NOT NULL,
    model text NOT NULL,
    embedding vector(1024) NOT NULL,
    UNIQUE (company_id, kind, text, model)
);
CREATE INDEX entity_embeddings_hnsw ON entity_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE TABLE canonical_conflicts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL,
    company_ids bigint[] NOT NULL DEFAULT '{}',
    details jsonb NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','ignored')),
    created_at timestamptz NOT NULL DEFAULT now()
);
"""

DROP = """
DROP TABLE IF EXISTS canonical_conflicts, entity_embeddings, source_records, facilities,
    company_relationships, company_aliases, companies, audit_log, api_keys, refresh_tokens,
    user_mfa, users, tenants CASCADE;
DROP FUNCTION IF EXISTS audit_log_immutable();
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
