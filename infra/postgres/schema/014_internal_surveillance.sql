-- Internal-trade surveillance Gold tables — written by dbt models at
-- dbt/models/gold/{internal_trade_enriched,internal_trade_surveillance}.sql as
-- Parquet on MinIO, synced into Postgres via nrc_processing.sync_postgres.
--
-- These join the firm's own trade book (silver.internal_trades) to the public
-- floor sheet (by contract_number) to flag suspicious internal trades for the
-- CEO surveillance board: bad fills vs day VWAP, and trades into scrips the
-- market signals already flag as operator-driven. A flag for review, not a
-- verdict. Grain is one row per internal fill (contract_number, client, side) —
-- the same fill can appear twice if two funds are the two sides of one trade.
--
-- Column order MUST match the `_SYNC` entries in sync_postgres.py so COPY can
-- load without naming columns.

-- ------------------------------------------------------ internal_trade_enriched
-- The firm's fills + recovered broker/counterparty + day VWAP/OHLC.
CREATE TABLE IF NOT EXISTS internal_trade_enriched (
    contract_number      BIGINT NOT NULL,
    scrip                VARCHAR(20) NOT NULL,
    trade_date           DATE NOT NULL,
    client_code          VARCHAR(32) NOT NULL,
    client_name          TEXT,
    side                 VARCHAR(1) NOT NULL,
    our_qty              DOUBLE PRECISION,
    our_price            DOUBLE PRECISION,
    our_value            DOUBLE PRECISION,
    order_id             BIGINT,
    traded_at            TIMESTAMP,
    our_broker           INTEGER,
    counterparty_broker  INTEGER,
    day_vwap             DOUBLE PRECISION,
    day_high_fs          DOUBLE PRECISION,
    day_low_fs           DOUBLE PRECISION,
    day_open             DOUBLE PRECISION,
    day_high             DOUBLE PRECISION,
    day_low              DOUBLE PRECISION,
    day_close            DOUBLE PRECISION,
    matched_floorsheet   BOOLEAN,
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (contract_number, client_code, side)
);
CREATE INDEX IF NOT EXISTS ix_internal_enriched_scrip_date ON internal_trade_enriched (scrip, trade_date DESC);
CREATE INDEX IF NOT EXISTS ix_internal_enriched_client     ON internal_trade_enriched (client_code);

-- -------------------------------------------------- internal_trade_surveillance
-- Per fill: 0-100 surveillance score + tier + flag reasons.
CREATE TABLE IF NOT EXISTS internal_trade_surveillance (
    contract_number           BIGINT NOT NULL,
    scrip                     VARCHAR(20) NOT NULL,
    trade_date                DATE NOT NULL,
    client_code               VARCHAR(32) NOT NULL,
    client_name               TEXT,
    side                      VARCHAR(1) NOT NULL,
    our_qty                   DOUBLE PRECISION,
    our_value                 DOUBLE PRECISION,
    our_broker                INTEGER,
    counterparty_broker       INTEGER,
    our_price                 DOUBLE PRECISION,
    day_vwap                  DOUBLE PRECISION,
    matched_floorsheet        BOOLEAN,
    slippage_vs_vwap_pct      DOUBLE PRECISION,
    slippage_npr              DOUBLE PRECISION,
    worse_than_range_flag     BOOLEAN,
    scrip_speculation_score   DOUBLE PRECISION,
    scrip_speculation_tier    VARCHAR(12),
    scrip_concentration_flag  BOOLEAN,
    scrip_circular_score      DOUBLE PRECISION,
    scrip_pump_flag           BOOLEAN,
    exec_component            DOUBLE PRECISION,
    manip_component           DOUBLE PRECISION,
    surveillance_score        DOUBLE PRECISION,
    surveillance_tier         VARCHAR(12),
    flag_reasons              TEXT[],
    computed_at               TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (contract_number, client_code, side)
);
CREATE INDEX IF NOT EXISTS ix_internal_surv_tier   ON internal_trade_surveillance (surveillance_tier, surveillance_score DESC);
CREATE INDEX IF NOT EXISTS ix_internal_surv_client ON internal_trade_surveillance (client_code);
CREATE INDEX IF NOT EXISTS ix_internal_surv_scrip  ON internal_trade_surveillance (scrip, trade_date DESC);
