-- Cohort taxonomy on top of the existing red/amber/green flag.
-- Mirrors the research team's three cohorts from BFIs - Fundamental Universe:
--   value_universe       — PE<25 + clean fundamentals + EPS>0 + growth ≥ 5%
--   fundamental_universe — usable but with caveats (default for clean data)
--   out_of_universe      — disqualified by any hard signal (NPL>6%, PE>40, …)
--   unknown              — ticker not in active universe

ALTER TABLE analysis_results
  ADD COLUMN IF NOT EXISTS cohort        TEXT
    CHECK (cohort IN ('value_universe','fundamental_universe','out_of_universe','unknown')),
  ADD COLUMN IF NOT EXISTS cohort_reason TEXT;

CREATE INDEX IF NOT EXISTS ix_analysis_results_cohort ON analysis_results(cohort);
