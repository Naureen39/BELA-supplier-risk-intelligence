"""Events and NLP tables, portfolio tables.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DDL = """
-- Events and NLP -----------------------------------------------------------
CREATE TABLE articles (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    url text NOT NULL UNIQUE,
    title text,
    domain text,
    language text,
    published_at timestamptz,
    snippet text CHECK (snippet IS NULL OR length(snippet) <= 300),
    source text NOT NULL DEFAULT 'gdelt',
    fetched_at timestamptz
);

CREATE TABLE article_embeddings (
    article_id bigint PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    model text NOT NULL,
    embedding vector(1024) NOT NULL
);
CREATE INDEX article_embeddings_hnsw ON article_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE TABLE mentions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_id bigint NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    span_start integer NOT NULL,
    span_end integer NOT NULL,
    surface text NOT NULL,
    qid text,
    md_score real,
    el_score real,
    route text,
    decision text CHECK (decision IN ('accepted','review','nil')),
    model_version text,
    CHECK (span_end > span_start)
);
CREATE INDEX mentions_article ON mentions (article_id);

CREATE TABLE events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL,
    source_id text NOT NULL,
    event_type text NOT NULL,
    severity smallint NOT NULL CHECK (severity BETWEEN 1 AND 4),
    occurred_at timestamptz,
    reported_at timestamptz NOT NULL,
    title text NOT NULL,
    summary text,
    url text,
    raw_ref jsonb NOT NULL DEFAULT '{}',
    state text,
    city text,
    latitude double precision,
    longitude double precision,
    cluster_id bigint,
    rules_version text,
    UNIQUE (source, source_id)
);
CREATE INDEX events_reported ON events (reported_at DESC);
CREATE INDEX events_type ON events (event_type);

CREATE TABLE event_entities (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    company_id bigint REFERENCES companies(id),
    mention_id bigint REFERENCES mentions(id) ON DELETE SET NULL,
    role text NOT NULL,
    method text NOT NULL,
    score real NOT NULL CHECK (score BETWEEN 0 AND 1),
    route text NOT NULL CHECK (route IN ('accepted','review','nil'))
);
CREATE INDEX event_entities_company ON event_entities (company_id);
CREATE INDEX event_entities_event ON event_entities (event_id);

CREATE TABLE link_candidates (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_entity_id bigint REFERENCES event_entities(id) ON DELETE CASCADE,
    mention_id bigint REFERENCES mentions(id) ON DELETE CASCADE,
    rank smallint NOT NULL,
    company_id bigint NOT NULL REFERENCES companies(id),
    bela_score real,
    blink_score real,
    splink_score real,
    llm_label text,
    CHECK (event_entity_id IS NOT NULL OR mention_id IS NOT NULL)
);

-- Portfolio -----------------------------------------------------------------
CREATE TABLE supplier_uploads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    uploaded_by uuid REFERENCES users(id),
    filename text NOT NULL,
    idempotency_key text,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','processing','complete','failed')),
    row_count integer NOT NULL DEFAULT 0,
    auto_resolved integer NOT NULL DEFAULT 0,
    needs_review integer NOT NULL DEFAULT 0,
    unresolved integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE suppliers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    upload_id uuid REFERENCES supplier_uploads(id) ON DELETE SET NULL,
    uploaded_name text NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}',
    identifiers_encrypted bytea,
    tier text,
    resolved_company_id bigint REFERENCES companies(id),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','auto_resolved','needs_review','resolved','unresolved')),
    confidence real CHECK (confidence BETWEEN 0 AND 1),
    resolution_detail jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX suppliers_tenant ON suppliers (tenant_id, status);
CREATE INDEX suppliers_company ON suppliers (resolved_company_id);

CREATE TABLE resolution_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    supplier_id uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    candidates jsonb NOT NULL DEFAULT '[]',
    status text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','accepted','rejected','chose_other','unresolved')),
    chosen_company_id bigint REFERENCES companies(id),
    reviewer_id uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);

CREATE TABLE risk_scores (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    supplier_id uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    score numeric(5,2) NOT NULL CHECK (score BETWEEN 0 AND 100),
    level text NOT NULL CHECK (level IN ('low','medium','high','critical')),
    config_version text NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX risk_scores_supplier ON risk_scores (supplier_id, computed_at DESC);

CREATE TABLE risk_score_components (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    risk_score_id bigint NOT NULL REFERENCES risk_scores(id) ON DELETE CASCADE,
    event_id bigint NOT NULL REFERENCES events(id),
    category text NOT NULL,
    severity_weight real NOT NULL,
    recency_decay real NOT NULL,
    link_confidence real NOT NULL,
    relation_weight real NOT NULL,
    source_reliability real NOT NULL,
    event_impact real NOT NULL
);

CREATE TABLE alert_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name text NOT NULL,
    event_types text[] NOT NULL DEFAULT '{}',
    min_severity smallint NOT NULL DEFAULT 3 CHECK (min_severity BETWEEN 1 AND 4),
    supplier_tiers text[] NOT NULL DEFAULT '{}',
    states text[] NOT NULL DEFAULT '{}',
    channels text[] NOT NULL DEFAULT '{in_app}',
    webhook_url text,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    supplier_id uuid NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    rule_id uuid REFERENCES alert_rules(id) ON DELETE SET NULL,
    kind text NOT NULL CHECK (kind IN ('threshold_crossing','high_severity_event')),
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN ('new','in_review','acknowledged','dismissed','escalated')),
    assignee_id uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE alert_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_id uuid NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    event_id bigint REFERENCES events(id),
    actor_user_id uuid REFERENCES users(id),
    change text NOT NULL,
    reason text,
    comment text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (alert_id, event_id, change)
);

CREATE TABLE reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('supplier','portfolio')),
    supplier_id uuid REFERENCES suppliers(id) ON DELETE SET NULL,
    storage_path text,
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
"""

DROP = """
DROP TABLE IF EXISTS reports, alert_events, alerts, alert_rules, risk_score_components,
    risk_scores, resolution_reviews, suppliers, supplier_uploads, link_candidates,
    event_entities, events, mentions, article_embeddings, articles CASCADE;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
