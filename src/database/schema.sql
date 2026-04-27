-- fin v7 Supabase schema (post-Phase-11 — legacy tables dropped)
-- Apply with: psql $DATABASE_URL -f src/database/schema.sql
-- To drop legacy tables first: psql $DATABASE_URL -f scripts/sql/001_drop_legacy.sql

-- ------------------------------------------------------------------ --
-- Qlib training run registry
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

-- ------------------------------------------------------------------ --
-- Backtest results
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              BIGSERIAL PRIMARY KEY,
    mlflow_run_id   TEXT UNIQUE NOT NULL,
    strategy        TEXT,
    start_date      DATE,
    end_date        DATE,
    metrics         JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_backtest_runs_created_at ON backtest_runs (created_at DESC);

-- ------------------------------------------------------------------ --
-- Data quality monitoring
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
