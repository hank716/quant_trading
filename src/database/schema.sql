-- fin v7 Supabase schema
-- Apply with: psql $DATABASE_URL -f src/database/schema.sql

-- ------------------------------------------------------------------ --
-- Pipeline runs
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT        NOT NULL UNIQUE,
    trade_date  DATE        NOT NULL,
    mode        TEXT        NOT NULL CHECK (mode IN ('daily', 'backfill', 'retrain')),
    status      TEXT        NOT NULL CHECK (status IN ('running', 'success', 'failed', 'partial')),
    git_commit  TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_trade_date ON pipeline_runs (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status     ON pipeline_runs (status);

CREATE TABLE IF NOT EXISTS run_steps (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT        NOT NULL REFERENCES pipeline_runs (run_id),
    step_name   TEXT        NOT NULL,
    status      TEXT        NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    error_msg   TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_steps_run_id ON run_steps (run_id);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT        NOT NULL REFERENCES pipeline_runs (run_id),
    artifact    TEXT        NOT NULL,
    uri         TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ --
-- Coverage snapshots
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS coverage_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    trade_date          DATE        NOT NULL,
    run_id              TEXT,
    revenue_coverage    FLOAT,
    financial_coverage  FLOAT,
    missing_critical    JSONB       DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_coverage_snapshots_date ON coverage_snapshots (trade_date DESC);

-- ------------------------------------------------------------------ --
-- Model registry
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS model_versions (
    id                   BIGSERIAL PRIMARY KEY,
    model_id             TEXT        NOT NULL UNIQUE,
    family               TEXT        NOT NULL,
    feature_set_version  TEXT        NOT NULL,
    metrics              JSONB       DEFAULT '{}',
    artifact_uri         TEXT,
    status               TEXT        NOT NULL CHECK (status IN ('candidate', 'champion', 'retired')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_model_versions_family ON model_versions (family);

CREATE TABLE IF NOT EXISTS model_promotions (
    id            BIGSERIAL PRIMARY KEY,
    model_id      TEXT        NOT NULL REFERENCES model_versions (model_id),
    promoted_by   TEXT,
    reason        TEXT,
    promoted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ --
-- Daily results
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS daily_candidates (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT        NOT NULL,
    trade_date      DATE        NOT NULL,
    instrument      TEXT        NOT NULL,
    list_type       TEXT        NOT NULL CHECK (list_type IN ('eligible', 'watch')),
    score           FLOAT,
    selection_reason TEXT,
    metrics         JSONB       DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_daily_candidates_date ON daily_candidates (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_candidates_run  ON daily_candidates (run_id);

CREATE TABLE IF NOT EXISTS daily_positions (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT        NOT NULL,
    trade_date      DATE        NOT NULL,
    instrument      TEXT        NOT NULL,
    target_weight   FLOAT,
    score           FLOAT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_trades (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT        NOT NULL,
    trade_date      DATE        NOT NULL,
    instrument      TEXT        NOT NULL,
    action          TEXT        NOT NULL CHECK (action IN ('BUY', 'SELL', 'HOLD')),
    delta_weight    FLOAT,
    prev_weight     FLOAT,
    new_weight      FLOAT,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_reports_index (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT        NOT NULL,
    trade_date      DATE        NOT NULL UNIQUE,
    markdown_uri    TEXT,
    html_uri        TEXT,
    json_uri        TEXT,
    status          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports_index (trade_date DESC);

-- ------------------------------------------------------------------ --
-- Alerts
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS system_alerts (
    id          BIGSERIAL PRIMARY KEY,
    level       TEXT        NOT NULL CHECK (level IN ('info', 'warning', 'error')),
    source      TEXT,
    message     TEXT        NOT NULL,
    resolved    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_system_alerts_resolved ON system_alerts (resolved, created_at DESC);

-- ------------------------------------------------------------------ --
-- Phase 8: Qlib training run registry
-- Note: model_versions, model_promotions, pipeline_runs, run_steps will be dropped in Phase 11
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS qlib_runs (
    id BIGSERIAL PRIMARY KEY,
    mlflow_run_id TEXT UNIQUE NOT NULL,
    experiment_name TEXT,
    family TEXT,
    workflow_config TEXT,
    status TEXT CHECK (status IN ('running', 'success', 'failed')),
    metrics JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_qlib_runs_family ON qlib_runs (family);
CREATE INDEX IF NOT EXISTS ix_qlib_runs_status ON qlib_runs (status);
CREATE INDEX IF NOT EXISTS ix_qlib_runs_created_at ON qlib_runs (created_at DESC);
