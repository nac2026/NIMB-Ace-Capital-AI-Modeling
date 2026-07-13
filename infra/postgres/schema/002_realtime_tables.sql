-- Real-time market data tables.
-- live_quotes  : one row per scrip, always the latest tick (UPSERT on write)
-- tick_history : append-only audit trail of every tick received

-- ---------------------------------------------------------- live_quotes
CREATE TABLE IF NOT EXISTS live_quotes (
    scrip          VARCHAR(20)      PRIMARY KEY REFERENCES scrips(scrip),
    price          DOUBLE PRECISION NOT NULL,
    open           DOUBLE PRECISION,
    high           DOUBLE PRECISION,
    low            DOUBLE PRECISION,
    volume         BIGINT           NOT NULL DEFAULT 0,
    turnover       DOUBLE PRECISION NOT NULL DEFAULT 0,
    change_abs     DOUBLE PRECISION,
    change_pct     DOUBLE PRECISION,
    prev_close     DOUBLE PRECISION,
    tick_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    source         VARCHAR(50)      NOT NULL DEFAULT 'simulator'
);
CREATE INDEX IF NOT EXISTS ix_live_quotes_tick_at ON live_quotes (tick_at DESC);

-- ---------------------------------------------------------- tick_history
CREATE TABLE IF NOT EXISTS tick_history (
    id       BIGSERIAL        PRIMARY KEY,
    scrip    VARCHAR(20)      NOT NULL,
    price    DOUBLE PRECISION NOT NULL,
    volume   BIGINT           NOT NULL DEFAULT 0,
    tick_at  TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    source   VARCHAR(50)      NOT NULL DEFAULT 'simulator'
);
CREATE INDEX IF NOT EXISTS ix_tick_history_scrip_time ON tick_history (scrip, tick_at DESC);
