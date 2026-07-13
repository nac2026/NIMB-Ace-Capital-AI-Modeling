-- Generic cross-sector snapshot columns.
--
-- The multi-sector "Data for Automation" dump (client_csv_automation) feeds
-- fundamentals for all sectors, not just Commercial Banks. These columns hold
-- the cross-sector key metrics that have no bank-centric home in the original
-- fundamental_snapshots schema. Idempotent so it is safe on databases that
-- already created the table from 001_serving_tables.sql.

ALTER TABLE fundamental_snapshots ADD COLUMN IF NOT EXISTS total_revenue          DOUBLE PRECISION;
ALTER TABLE fundamental_snapshots ADD COLUMN IF NOT EXISTS total_assets           DOUBLE PRECISION;
ALTER TABLE fundamental_snapshots ADD COLUMN IF NOT EXISTS shareholders_equity    DOUBLE PRECISION;
ALTER TABLE fundamental_snapshots ADD COLUMN IF NOT EXISTS market_value_per_share DOUBLE PRECISION;
ALTER TABLE fundamental_snapshots ADD COLUMN IF NOT EXISTS dividend_per_share     DOUBLE PRECISION;
