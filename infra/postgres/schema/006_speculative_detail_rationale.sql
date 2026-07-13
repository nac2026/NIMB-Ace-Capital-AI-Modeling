-- LLM-generated descriptive verdict per ticker.
-- Shown inside the per-ticker detail modal as the "Why this verdict" section.
-- 3-5 sentences explaining cohort placement + flag rationale + key signals.
-- Null when the LLM call failed or the DETAILS block wasn't parseable —
-- in that case the UI renders a templated fallback composed from
-- cohort_reason + rule_outcomes.

ALTER TABLE analysis_results
  ADD COLUMN IF NOT EXISTS detail_rationale TEXT;
