-- ============================================================================
-- 018_surveillance_case_responses.sql — human findings on surveillance cases.
--
-- Operational table (NOT lakehouse-synced — owned by the orchestrator). The
-- CEO / reviewers record what they actually found when investigating a flagged
-- case ("confirmed with the desk — negotiated block with a known seller").
-- Replies render as a thread under the LLM case note, and are fed back into
-- the LLM prompt as analyst context whenever the note regenerates, so the
-- model's framing improves with human ground truth.
-- ============================================================================

CREATE TABLE IF NOT EXISTS surveillance_case_responses (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_key    TEXT NOT NULL,             -- '<client_code>:<scrip>:<trade_date>'
    author      TEXT NOT NULL DEFAULT 'CEO',
    body        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_surv_responses_case ON surveillance_case_responses (case_key, created_at);
