-- Internal-trade surveillance v2 — five-component scoring (exec, manip,
-- counterparty, cross, outcome) with interval-VWAP benchmarks, vol-normalized
-- slippage, post-trade markouts, counterparty surprise statistics, exit-liquidity
-- detection and intra-firm cross/churn. Written by dbt models at
-- dbt/models/gold/internal_*.sql as Parquet on MinIO, synced via
-- nrc_processing.sync_postgres.
--
-- These are TRUNCATE+COPY serving mirrors, so dropping and recreating with the
-- new column set is safe (no operational data lives here). Column order MUST
-- match the `_SYNC` entries in sync_postgres.py.

DROP TABLE IF EXISTS internal_trade_enriched;
DROP TABLE IF EXISTS internal_trade_surveillance;

-- ------------------------------------------------------ internal_trade_enriched
-- Per fill: broker/counterparty + every execution & outcome benchmark.
CREATE TABLE internal_trade_enriched (
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
    interval_vwap        DOUBLE PRECISION,
    n_interval_trades    BIGINT,
    vol_20d              DOUBLE PRECISION,
    prior_high_20d       DOUBLE PRECISION,
    prior_low_20d        DOUBLE PRECISION,
    day_close            DOUBLE PRECISION,
    close_t1             DOUBLE PRECISION,
    close_t5             DOUBLE PRECISION,
    close_t20            DOUBLE PRECISION,
    markout_1d_pct       DOUBLE PRECISION,
    markout_5d_pct       DOUBLE PRECISION,
    markout_20d_pct      DOUBLE PRECISION,
    matched_floorsheet   BOOLEAN,
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (contract_number, client_code, side)
);
CREATE INDEX IF NOT EXISTS ix_internal_enriched_scrip_date ON internal_trade_enriched (scrip, trade_date DESC);
CREATE INDEX IF NOT EXISTS ix_internal_enriched_client     ON internal_trade_enriched (client_code);

-- -------------------------------------------------- internal_trade_surveillance
-- Per fill: five-component 0-100 score + tier + flag reasons.
CREATE TABLE internal_trade_surveillance (
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
    interval_vwap             DOUBLE PRECISION,
    n_interval_trades         BIGINT,
    matched_floorsheet        BOOLEAN,
    slippage_vs_vwap_pct      DOUBLE PRECISION,
    slippage_npr              DOUBLE PRECISION,
    worse_than_range_flag     BOOLEAN,
    markout_1d_pct            DOUBLE PRECISION,
    markout_5d_pct            DOUBLE PRECISION,
    markout_20d_pct           DOUBLE PRECISION,
    scrip_speculation_score   DOUBLE PRECISION,
    scrip_speculation_tier    VARCHAR(12),
    scrip_concentration_flag  BOOLEAN,
    scrip_circular_score      DOUBLE PRECISION,
    scrip_pump_flag           BOOLEAN,
    cp_n_trades               BIGINT,
    cp_share_of_fund          DOUBLE PRECISION,
    cp_market_share           DOUBLE PRECISION,
    cp_surprise_z             DOUBLE PRECISION,
    cp_flagged                BOOLEAN,
    repeat_counterparty_flag  BOOLEAN,
    exit_liquidity_flag       BOOLEAN,
    cross_flag                BOOLEAN,
    churn_flag                BOOLEAN,
    bought_near_peak_flag     BOOLEAN,
    exec_component            DOUBLE PRECISION,
    manip_component           DOUBLE PRECISION,
    counterparty_component    DOUBLE PRECISION,
    cross_component           DOUBLE PRECISION,
    outcome_component         DOUBLE PRECISION,
    surveillance_score        DOUBLE PRECISION,
    surveillance_tier         VARCHAR(12),
    flag_reasons              TEXT[],
    computed_at               TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (contract_number, client_code, side)
);
CREATE INDEX IF NOT EXISTS ix_internal_surv_tier   ON internal_trade_surveillance (surveillance_tier, surveillance_score DESC);
CREATE INDEX IF NOT EXISTS ix_internal_surv_client ON internal_trade_surveillance (client_code);
CREATE INDEX IF NOT EXISTS ix_internal_surv_scrip  ON internal_trade_surveillance (scrip, trade_date DESC);

-- ---------------------------------------------- internal_counterparty_exposure
-- Per (fund, counterparty broker, scrip): repeat-trading pattern statistics.
CREATE TABLE IF NOT EXISTS internal_counterparty_exposure (
    client_code          VARCHAR(32) NOT NULL,
    client_name          TEXT,
    counterparty_broker  INTEGER NOT NULL,
    scrip                VARCHAR(20) NOT NULL,
    n_trades             BIGINT,
    total_qty            DOUBLE PRECISION,
    total_amount         DOUBLE PRECISION,
    n_days               BIGINT,
    first_date           DATE,
    last_date            DATE,
    share_of_fund_qty    DOUBLE PRECISION,
    cp_market_share      DOUBLE PRECISION,
    surprise_z           DOUBLE PRECISION,
    cp_is_accumulator    BOOLEAN,
    cp_is_distributor    BOOLEAN,
    cp_in_wash_pair      BOOLEAN,
    cp_flagged           BOOLEAN,
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (client_code, counterparty_broker, scrip)
);
CREATE INDEX IF NOT EXISTS ix_internal_cpty_z ON internal_counterparty_exposure (surprise_z DESC NULLS LAST);

-- --------------------------------------------------------- internal_cross_trade
-- Near-simultaneous intra-firm buy/sell pairs (cross/wash candidates).
CREATE TABLE IF NOT EXISTS internal_cross_trade (
    scrip          VARCHAR(20) NOT NULL,
    trade_date     DATE NOT NULL,
    buy_client     VARCHAR(32) NOT NULL,
    sell_client    VARCHAR(32) NOT NULL,
    buy_contract   BIGINT NOT NULL,
    sell_contract  BIGINT NOT NULL,
    buy_qty        DOUBLE PRECISION,
    sell_qty       DOUBLE PRECISION,
    buy_price      DOUBLE PRECISION,
    sell_price     DOUBLE PRECISION,
    time_gap_s     BIGINT,
    same_client    BOOLEAN,
    computed_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (buy_contract, sell_contract, buy_client, sell_client)
);
CREATE INDEX IF NOT EXISTS ix_internal_cross_scrip ON internal_cross_trade (scrip, trade_date DESC);
