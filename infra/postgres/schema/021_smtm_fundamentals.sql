-- ============================================================================
-- 021_smtm_fundamentals.sql — full-universe fundamentals from SMTM.
--
-- The CSV-sourced `fundamental_snapshots` covers ~233 scrips shallowly. SMTM
-- exposes deep key-stats (up to ~19y) for EVERY listed equity, so this table
-- holds the whole universe's per-period key metrics — bulk-ingested by
-- refresh_fundamentals.py — enabling cross-universe screening/ranking on SMTM
-- data (e.g. every scrip with ROE > 20% and NPL < 3%). One row per
-- (scrip, frequency, fiscal year, quarter). Monetary fields are in NPR '000
-- (×1000 for absolute NPR), matching the live SMTM key-stats payload.
-- ============================================================================

CREATE TABLE IF NOT EXISTS smtm_fundamentals (
    scrip                TEXT    NOT NULL,
    frequency            TEXT    NOT NULL,             -- 'annual' | 'quarterly'
    fiscal_year          TEXT    NOT NULL,             -- 'YYYY/YY' (Bikram Sambat)
    quarter              INTEGER NOT NULL DEFAULT 0,   -- 1-4; 0 when frequency='annual' has no Q
    data_source          TEXT,                         -- 'Audited' | 'Published'
    eps                  DOUBLE PRECISION,
    pe                   DOUBLE PRECISION,
    roe                  DOUBLE PRECISION,             -- fraction (0.15 = 15%)
    roa                  DOUBLE PRECISION,             -- fraction
    bvps                 DOUBLE PRECISION,
    dps                  DOUBLE PRECISION,
    total_revenue        DOUBLE PRECISION,             -- NPR '000
    net_income           DOUBLE PRECISION,             -- NPR '000
    net_income_margin    DOUBLE PRECISION,             -- fraction
    gross_profit_margin  DOUBLE PRECISION,             -- fraction
    market_cap           DOUBLE PRECISION,             -- NPR '000
    mps                  DOUBLE PRECISION,
    npl                  DOUBLE PRECISION,             -- fraction (BFIs only)
    capital_adequacy     DOUBLE PRECISION,             -- fraction (BFIs only)
    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source               TEXT NOT NULL DEFAULT 'smtm',
    PRIMARY KEY (scrip, frequency, fiscal_year, quarter)
);

CREATE INDEX IF NOT EXISTS ix_smtm_fund_scrip ON smtm_fundamentals (scrip);
CREATE INDEX IF NOT EXISTS ix_smtm_fund_freq  ON smtm_fundamentals (frequency);
