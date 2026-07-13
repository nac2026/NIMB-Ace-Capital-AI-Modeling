-- Speculative Analysis tables — operational data (not refreshed by sync).
-- Owns: per-CEO analysis sessions, per-ticker red/amber/green verdicts,
--       and persistent (multi-day) chat history scoped to each analysis.
--
-- Unlike Gold tables, these are NEVER truncated by the daily sync. They are
-- the CEO's permanent workspace.

-- ============================================================ analysis_sessions
-- One row per uploaded analysis run. The list view on /speculative reads this.
CREATE TABLE IF NOT EXISTS analysis_sessions (
    session_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT,                                     -- stub: 'ceo' literal; real auth later
    title             TEXT NOT NULL,
    notes             TEXT,
    source_filename   TEXT NOT NULL,
    source_object_key TEXT,                                     -- MinIO key for raw upload (audit)
    tickers           TEXT[] NOT NULL DEFAULT '{}',
    n_tickers         INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','running','succeeded','partial','failed')),
    error_message     TEXT,
    narrative_md      TEXT,                                     -- LLM-generated markdown report
    narrative_model   TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_analysis_sessions_created ON analysis_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_analysis_sessions_status  ON analysis_sessions(status);

-- ============================================================ analysis_results
-- One row per (session, ticker). Holds the verdict + the snapshot of Gold-table
-- values used at evaluation time so historic flags don't drift later.
CREATE TABLE IF NOT EXISTS analysis_results (
    result_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID NOT NULL REFERENCES analysis_sessions(session_id) ON DELETE CASCADE,
    scrip         VARCHAR(20) NOT NULL,
    company_name  TEXT,
    sector        TEXT,
    flag          TEXT NOT NULL CHECK (flag IN ('green','amber','red','unknown')),
    flag_score    DOUBLE PRECISION,                             -- 0-100 aggregated
    rule_outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,           -- per-rule {rule,status,value,threshold}
    snapshot      JSONB NOT NULL DEFAULT '{}'::jsonb,           -- gold-table values at eval time
    headline      TEXT,
    error         TEXT,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, scrip)
);
CREATE INDEX IF NOT EXISTS ix_analysis_results_session ON analysis_results(session_id);
CREATE INDEX IF NOT EXISTS ix_analysis_results_flag    ON analysis_results(flag);
CREATE INDEX IF NOT EXISTS ix_analysis_results_scrip   ON analysis_results(scrip);

-- ============================================================ analysis_chat_turns
-- Postgres-persistent chat (not Redis-ephemeral) scoped to one analysis.
-- The CEO returns days later and sees the full thread he had about it.
CREATE TABLE IF NOT EXISTS analysis_chat_turns (
    turn_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES analysis_sessions(session_id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content    TEXT NOT NULL,
    trace_id   UUID,                                            -- loose ref to query_traces.trace_id
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_chat_session ON analysis_chat_turns(session_id, created_at);
