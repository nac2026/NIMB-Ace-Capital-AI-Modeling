-- ============================================================================
-- 017_surveillance_explanations.sql — LLM-written explanations for flagged
-- internal-trade surveillance cases.
--
-- Operational table (NOT lakehouse-synced — owned by the orchestrator). One
-- row per surveillance CASE (flagged fills grouped by fund × scrip × day).
-- `signature` fingerprints the case's score/reasons/fill-count at generation
-- time: when the nightly rebuild changes the case, the signature stops
-- matching and the API regenerates the explanation lazily.
-- ============================================================================

CREATE TABLE IF NOT EXISTS surveillance_explanations (
    case_key     TEXT PRIMARY KEY,         -- '<client_code>:<scrip>:<trade_date>'
    signature    TEXT NOT NULL,            -- md5 of (score | reasons | n_fills)
    explanation  TEXT NOT NULL,            -- 2-4 plain-language sentences
    model        TEXT,                     -- LLM model that wrote it
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
