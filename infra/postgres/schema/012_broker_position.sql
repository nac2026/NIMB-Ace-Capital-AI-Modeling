-- ============================================================================
-- 012_broker_position.sql — broker position TIMELINE + phase summary.
--
-- broker_accumulation is a single cumulative aggregate (no trajectory). These
-- two operational tables add the "when": the running cumulative net position
-- per broker over time, and a derived phase summary (when accumulation started,
-- when the position peaked, when the broker flipped to distributing).
--
-- Computed directly from the serving broker_flow_daily table by
-- nrc_processing.broker_positions.refresh_broker_positions() — NOT synced from
-- the lakehouse (so a Gold→Postgres sync won't wipe them).
-- ============================================================================

-- Per (scrip, broker, day): that day's net + the running cumulative position.
CREATE TABLE IF NOT EXISTS broker_position_timeline (
    scrip          VARCHAR(20) NOT NULL,
    broker         INTEGER NOT NULL,
    trade_date     DATE NOT NULL,
    daily_net_qty  DOUBLE PRECISION,
    cum_net_qty    DOUBLE PRECISION,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scrip, broker, trade_date)
);
CREATE INDEX IF NOT EXISTS ix_bpt_scrip ON broker_position_timeline (scrip);

-- Phase summary per (scrip, broker).
CREATE TABLE IF NOT EXISTS broker_position (
    scrip            VARCHAR(20) NOT NULL,
    broker           INTEGER NOT NULL,
    phase            TEXT,                 -- 'accumulating' | 'distributing' | 'flat'
    accum_start_date DATE,                 -- first net-buy day
    peak_date        DATE,                 -- day the running cum position was highest
    peak_cum_qty     DOUBLE PRECISION,
    dist_start_date  DATE,                 -- first net-sell day AFTER the peak (the flip)
    days_since_peak  INTEGER,
    cum_net_qty      DOUBLE PRECISION,     -- latest cumulative net position
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scrip, broker)
);
CREATE INDEX IF NOT EXISTS ix_bpos_scrip ON broker_position (scrip);
