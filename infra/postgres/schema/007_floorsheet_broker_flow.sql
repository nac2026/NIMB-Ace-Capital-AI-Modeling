-- Floor-sheet broker-flow Gold tables — written by dbt models at
-- dbt/models/gold/{broker_flow_daily,broker_concentration_daily,
-- broker_accumulation,broker_pair_graph,speculation_score}.sql as Parquet on
-- MinIO, synced into Postgres via nrc_processing.sync_postgres.
--
-- Column order MUST match the `_SYNC` entry in sync_postgres.py so COPY can
-- load without naming columns. TRUNCATE + COPY semantics; computed_at is the
-- only non-data column. These power the broker tools, the research
-- floor-sheet tab, and the speculative-analysis engine.

-- ---------------------------------------------------------- broker_flow_daily
-- Per (scrip, broker, day): buy/sell/net flow. High-volume — sync recent days.
CREATE TABLE IF NOT EXISTS broker_flow_daily (
    scrip           VARCHAR(20) NOT NULL,
    broker          INTEGER NOT NULL,
    trade_date      DATE NOT NULL,
    buy_qty         DOUBLE PRECISION,
    sell_qty        DOUBLE PRECISION,
    net_qty         DOUBLE PRECISION,
    buy_amount      DOUBLE PRECISION,
    sell_amount     DOUBLE PRECISION,
    net_amount      DOUBLE PRECISION,
    buy_trades      BIGINT,
    sell_trades     BIGINT,
    trade_sides     BIGINT,
    computed_at     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, broker, trade_date)
);
CREATE INDEX IF NOT EXISTS ix_broker_flow_scrip_date ON broker_flow_daily (scrip, trade_date DESC);
CREATE INDEX IF NOT EXISTS ix_broker_flow_broker     ON broker_flow_daily (broker, trade_date DESC);

-- ------------------------------------------------- broker_concentration_daily
-- Per (scrip, day): HHI + dominance/control flags. "Is one hand on a side?"
CREATE TABLE IF NOT EXISTS broker_concentration_daily (
    scrip                VARCHAR(20) NOT NULL,
    trade_date           DATE NOT NULL,
    n_brokers            BIGINT,
    total_buy_qty        DOUBLE PRECISION,
    total_sell_qty       DOUBLE PRECISION,
    hhi_buy              DOUBLE PRECISION,
    hhi_sell             DOUBLE PRECISION,
    hhi_combined         DOUBLE PRECISION,
    top1_buy_share       DOUBLE PRECISION,
    top1_sell_share      DOUBLE PRECISION,
    top3_buy_share       DOUBLE PRECISION,
    top3_sell_share      DOUBLE PRECISION,
    buy_dominance_flag   BOOLEAN,
    sell_dominance_flag  BOOLEAN,
    buy_control_flag     BOOLEAN,
    sell_control_flag    BOOLEAN,
    concentration_flag   BOOLEAN,
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, trade_date)
);
CREATE INDEX IF NOT EXISTS ix_broker_conc_flag ON broker_concentration_daily (concentration_flag, trade_date DESC);

-- ---------------------------------------------------------- broker_accumulation
-- Per (scrip, broker) over the loaded window: who is building/distributing.
CREATE TABLE IF NOT EXISTS broker_accumulation (
    scrip               VARCHAR(20) NOT NULL,
    broker              INTEGER NOT NULL,
    cum_net_qty         DOUBLE PRECISION,
    cum_net_amount      DOUBLE PRECISION,
    cum_buy_qty         DOUBLE PRECISION,
    cum_sell_qty        DOUBLE PRECISION,
    broker_volume       DOUBLE PRECISION,
    volume_share        DOUBLE PRECISION,
    days_active         BIGINT,
    days_net_buy        BIGINT,
    days_net_sell       BIGINT,
    first_day           DATE,
    last_day            DATE,
    accumulation_rank   BIGINT,
    distribution_rank   BIGINT,
    accumulation_flag   BOOLEAN,
    distribution_flag   BOOLEAN,
    computed_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, broker)
);
CREATE INDEX IF NOT EXISTS ix_broker_accum_scrip ON broker_accumulation (scrip, accumulation_rank);
CREATE INDEX IF NOT EXISTS ix_broker_accum_flag  ON broker_accumulation (accumulation_flag) WHERE accumulation_flag;

-- ---------------------------------------------------------- broker_pair_graph
-- Per (scrip, broker pair): directional volumes + reciprocal/wash circular score.
CREATE TABLE IF NOT EXISTS broker_pair_graph (
    scrip               VARCHAR(20) NOT NULL,
    broker_lo           INTEGER NOT NULL,
    broker_hi           INTEGER NOT NULL,
    self_trade          BOOLEAN,
    qty_lo_buys         DOUBLE PRECISION,
    qty_hi_buys         DOUBLE PRECISION,
    pair_qty            DOUBLE PRECISION,
    pair_amount         DOUBLE PRECISION,
    pair_trades         BIGINT,
    reciprocal_balance  DOUBLE PRECISION,
    pair_volume_share   DOUBLE PRECISION,
    circular_score      DOUBLE PRECISION,
    computed_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, broker_lo, broker_hi)
);
CREATE INDEX IF NOT EXISTS ix_broker_pair_circular ON broker_pair_graph (scrip, circular_score DESC);

-- ---------------------------------------------------------- speculation_score
-- Per scrip: 0-100 composite manipulation/operator-driven score + tier.
CREATE TABLE IF NOT EXISTS speculation_score (
    scrip               VARCHAR(20) NOT NULL,
    n_days              BIGINT,
    c_concentration     DOUBLE PRECISION,
    c_control           DOUBLE PRECISION,
    c_circular          DOUBLE PRECISION,
    c_accumulation      DOUBLE PRECISION,
    c_block             DOUBLE PRECISION,
    has_self_trade      INTEGER,
    speculation_score   DOUBLE PRECISION,
    speculation_tier    VARCHAR(12),
    computed_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip)
);
CREATE INDEX IF NOT EXISTS ix_speculation_tier ON speculation_score (speculation_tier, speculation_score DESC);

-- ---------------------------------------------------------- feed_cursors
-- Operational table (NOT synced from lakehouse) — the marketfeed floorsheet
-- puller persists its incremental cursor (last ingested contract_number) here
-- so it can resume mid-day and across restarts.
CREATE TABLE IF NOT EXISTS feed_cursors (
    feed        VARCHAR(64) PRIMARY KEY,
    cursor      TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
