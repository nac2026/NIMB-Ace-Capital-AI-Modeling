-- Stage-2 deep screen extended to all sectors.
--
-- gold.stage2_bank_screen now covers every sector (not just Commercial Banks).
-- Adds the sector label and the general-family profitability dimensions
-- (ROA, net margin) used to score non-BFI sectors. Idempotent — safe on
-- databases that already created the table from 001_serving_tables.sql.

ALTER TABLE stage2_bank_screen ADD COLUMN IF NOT EXISTS sector                TEXT;
ALTER TABLE stage2_bank_screen ADD COLUMN IF NOT EXISTS roa                   DOUBLE PRECISION;
ALTER TABLE stage2_bank_screen ADD COLUMN IF NOT EXISTS roa_percentile        DOUBLE PRECISION;
ALTER TABLE stage2_bank_screen ADD COLUMN IF NOT EXISTS net_margin            DOUBLE PRECISION;
ALTER TABLE stage2_bank_screen ADD COLUMN IF NOT EXISTS net_margin_percentile DOUBLE PRECISION;
