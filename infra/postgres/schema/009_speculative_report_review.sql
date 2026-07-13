-- Speculative Analysis "review mode": validate an uploaded WRITTEN research
-- report (PDF/DOCX). Extends analysis_sessions and adds claim-verification,
-- multi-aspect assessment, and bull/bear/judge debate tables. The existing
-- "screen mode" (ticker shortlist → rule flags) is unchanged; `mode`
-- distinguishes them.

ALTER TABLE analysis_sessions ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'screen'
    CHECK (mode IN ('screen', 'review'));
ALTER TABLE analysis_sessions ADD COLUMN IF NOT EXISTS parsed_report      JSONB;
ALTER TABLE analysis_sessions ADD COLUMN IF NOT EXISTS verdict            TEXT;   -- GREEN | AMBER | RED
ALTER TABLE analysis_sessions ADD COLUMN IF NOT EXISTS verdict_confidence DOUBLE PRECISION; -- 0..1
ALTER TABLE analysis_sessions ADD COLUMN IF NOT EXISTS target_price       DOUBLE PRECISION;

-- ============================================================ analysis_claims
-- Each factual/thesis claim extracted from the report, verified against
-- ground-truth data: supported | contradicted | unverifiable.
CREATE TABLE IF NOT EXISTS analysis_claims (
    claim_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL REFERENCES analysis_sessions(session_id) ON DELETE CASCADE,
    scrip        VARCHAR(20),
    claim_text   TEXT NOT NULL,
    claim_type   TEXT,                 -- metric | thesis | recommendation | sector | other
    verdict      TEXT CHECK (verdict IN ('supported','contradicted','unverifiable')),
    actual_value TEXT,                 -- the real figure/finding from our data
    evidence     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_claims_session ON analysis_claims(session_id);

-- ============================================================ analysis_aspects
-- Independent multi-aspect assessment per scrip (fundamentals, valuation,
-- technicals, floorsheet/manipulation, liquidity, governance, regulatory,
-- macro, news). Each rated positive/neutral/negative with cited evidence.
CREATE TABLE IF NOT EXISTS analysis_aspects (
    aspect_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES analysis_sessions(session_id) ON DELETE CASCADE,
    scrip       VARCHAR(20),
    aspect      TEXT NOT NULL,
    rating      TEXT CHECK (rating IN ('positive','neutral','negative')),
    score       DOUBLE PRECISION,      -- -1..1
    assessment  TEXT,
    evidence    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_aspects_session ON analysis_aspects(session_id);

-- ============================================================ analysis_debate
-- The bull/bear/judge transcript that produces the unbiased verdict.
CREATE TABLE IF NOT EXISTS analysis_debate (
    debate_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES analysis_sessions(session_id) ON DELETE CASCADE,
    scrip       VARCHAR(20),
    role        TEXT NOT NULL CHECK (role IN ('bull','bear','judge')),
    round       INTEGER NOT NULL DEFAULT 1,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_debate_session ON analysis_debate(session_id);
