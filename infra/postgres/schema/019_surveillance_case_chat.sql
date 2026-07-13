-- ============================================================================
-- 019_surveillance_case_chat.sql — persistent per-case analyst chat.
--
-- Operational table (NOT lakehouse-synced — owned by the orchestrator). Each
-- flagged surveillance case has its own chat thread: the reviewer opens the
-- case chat (floating panel on the board), the agent answers with the full
-- case context pre-loaded, and every turn persists here so reopening the
-- panel restores the thread. Mirrors analysis_chat_turns (speculative chat).
-- ============================================================================

CREATE TABLE IF NOT EXISTS surveillance_case_chat (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_key    TEXT NOT NULL,             -- '<client_code>:<scrip>:<trade_date>'
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    trace_id    TEXT,                      -- loose ref to query_traces (assistant turns)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_surv_chat_case ON surveillance_case_chat (case_key, created_at);
