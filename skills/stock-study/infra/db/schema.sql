-- LynAI Mines · stock-study v3.2 · PostgreSQL schema
-- Loaded automatically on docker-compose up (mounted to docker-entrypoint-initdb.d)

CREATE SCHEMA IF NOT EXISTS stockstudy;
SET search_path TO stockstudy, public;

-- ───────── Cost ledger (every LLM call) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_calls (
    id              BIGSERIAL PRIMARY KEY,
    agent_id        TEXT        NOT NULL,
    model           TEXT        NOT NULL,
    prompt_version  TEXT        NOT NULL,
    input_tokens    INTEGER     NOT NULL,
    output_tokens   INTEGER     NOT NULL,
    cost_usd        NUMERIC(10,6) NOT NULL,
    duration_ms     INTEGER     NOT NULL,
    stop_reason     TEXT,
    trace_id        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_calls_created_at ON agent_calls (created_at);
CREATE INDEX IF NOT EXISTS idx_agent_calls_agent_id   ON agent_calls (agent_id);

-- ───────── Champion / calibrator registry ───────────────────────────────
CREATE TABLE IF NOT EXISTS calibrators (
    id               BIGSERIAL PRIMARY KEY,
    version          TEXT      NOT NULL UNIQUE,
    status           TEXT      NOT NULL CHECK (status IN ('champion','challenger','archived')),
    fitted_at        TIMESTAMPTZ NOT NULL,
    fitted_window    TEXT      NOT NULL,
    metrics_json     JSONB     NOT NULL,  -- {ic, brier, reliability_gap, n_periods}
    artifact_path    TEXT      NOT NULL,
    promoted_by      TEXT,
    promoted_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_calibrators_status ON calibrators (status);

-- ───────── Shadow runs (parallel v3.2 vs v2.0 output during S4) ─────────
CREATE TABLE IF NOT EXISTS shadow_runs (
    id              BIGSERIAL PRIMARY KEY,
    asof_date       DATE         NOT NULL,
    version_a       TEXT         NOT NULL,  -- e.g. v2.0
    version_b       TEXT         NOT NULL,  -- e.g. v3.2
    a_scores_json   JSONB        NOT NULL,
    b_scores_json   JSONB        NOT NULL,
    a_ic            NUMERIC(8,6),
    b_ic            NUMERIC(8,6),
    top10_overlap   NUMERIC(5,4),
    spearman        NUMERIC(8,6),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shadow_runs_asof ON shadow_runs (asof_date);

-- ───────── Incidents (PI hits, budget breaches, data outages) ───────────
CREATE TABLE IF NOT EXISTS incidents (
    id              BIGSERIAL PRIMARY KEY,
    incident_type   TEXT      NOT NULL,   -- IP-1..IP-5 or 'pi_critical'
    severity        TEXT      NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    payload_json    JSONB     NOT NULL,   -- arbitrary forensic detail
    matched_ids     TEXT[],
    source          TEXT,
    resolved_at     TIMESTAMPTZ,
    resolution      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents (created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_unresolved ON incidents (created_at) WHERE resolved_at IS NULL;

-- ───────── Published artifacts (audit trail) ────────────────────────────
CREATE TABLE IF NOT EXISTS published_artifacts (
    id              BIGSERIAL PRIMARY KEY,
    artifact_id     TEXT      NOT NULL UNIQUE,
    asof_date       DATE      NOT NULL,
    regime          TEXT      NOT NULL,
    excel_path      TEXT,
    sha256          TEXT,
    universe_size   INTEGER,
    n_blocked       INTEGER   DEFAULT 0,
    gate_decision_json JSONB,
    sentinel_warnings_json JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pub_asof ON published_artifacts (asof_date);

-- ───────── Adversarial test history (each red-team run) ──────────────────
CREATE TABLE IF NOT EXISTS adversarial_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    n_cases         INTEGER     NOT NULL,
    n_passed        INTEGER     NOT NULL,
    git_sha         TEXT,
    detail_json     JSONB
);
