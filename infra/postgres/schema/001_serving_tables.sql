-- NEPSE Research Copilot — Postgres serving schema.
-- Owns: (1) mirrored Gold tables (the tool layer's primary read path),
--       (2) a hot slice of Silver (daily_bars for get_quote),
--       (3) operational tables Postgres owns outright (query_traces).
--
-- Every sync run: TRUNCATE + COPY. No UPSERT logic — Gold is recomputed
-- fully each pipeline, so the serving layer is a pure projection.

-- ----------------------------------------------------------------- scrips
CREATE TABLE IF NOT EXISTS scrips (
    scrip             VARCHAR(20) PRIMARY KEY,
    company_name      TEXT NOT NULL,
    sector            TEXT NOT NULL,
    sub_sector        TEXT,
    listed_shares     DOUBLE PRECISION,
    paid_up_value     DOUBLE PRECISION,
    paid_up_capital   DOUBLE PRECISION,
    registered_date   DATE,
    company_id        INTEGER,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_scrips_sector ON scrips(sector);

-- ------------------------------------------------------------- daily_bars
-- One row per (scrip, date). Hot table: updated after every price sync.
CREATE TABLE IF NOT EXISTS daily_bars (
    scrip         VARCHAR(20) NOT NULL,
    date          DATE NOT NULL,
    open          DOUBLE PRECISION NOT NULL,
    high          DOUBLE PRECISION NOT NULL,
    low           DOUBLE PRECISION NOT NULL,
    close         DOUBLE PRECISION NOT NULL,
    volume        BIGINT NOT NULL,
    turnover      DOUBLE PRECISION NOT NULL,
    ingested_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, date)
);
CREATE INDEX IF NOT EXISTS ix_daily_bars_date ON daily_bars(date DESC);

-- ------------------------------------------------------ corporate_actions
CREATE TABLE IF NOT EXISTS corporate_actions (
    scrip                VARCHAR(20) NOT NULL,
    action_type          TEXT NOT NULL,
    ratio                DOUBLE PRECISION,
    amount               DOUBLE PRECISION,
    announcement_date    DATE,
    book_closure_date    DATE,
    ex_date              DATE,
    fiscal_year_bs       INTEGER,
    source               TEXT NOT NULL DEFAULT 'sharesansar'
);
CREATE INDEX IF NOT EXISTS ix_corp_actions_scrip ON corporate_actions(scrip);
CREATE INDEX IF NOT EXISTS ix_corp_actions_fy   ON corporate_actions(fiscal_year_bs DESC);

-- ---------------------------------------------------- fundamental_snapshots
CREATE TABLE IF NOT EXISTS fundamental_snapshots (
    scrip                 VARCHAR(20) NOT NULL,
    fiscal_year_bs        INTEGER NOT NULL,
    quarter               INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    net_profit            DOUBLE PRECISION,
    operating_profit      DOUBLE PRECISION,
    net_interest_income   DOUBLE PRECISION,
    eps                   DOUBLE PRECISION,
    bvps                  DOUBLE PRECISION,
    roe                   DOUBLE PRECISION,
    roa                   DOUBLE PRECISION,
    npl_ratio             DOUBLE PRECISION,
    car                   DOUBLE PRECISION,
    cd_ratio              DOUBLE PRECISION,
    total_deposits        DOUBLE PRECISION,
    total_loans           DOUBLE PRECISION,
    paid_up_capital       DOUBLE PRECISION,
    pe_ratio              DOUBLE PRECISION,
    pb_ratio              DOUBLE PRECISION,
    total_revenue         DOUBLE PRECISION,
    total_assets          DOUBLE PRECISION,
    shareholders_equity   DOUBLE PRECISION,
    market_value_per_share DOUBLE PRECISION,
    dividend_per_share    DOUBLE PRECISION,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ------------------------------------------------------- indicators_daily
CREATE TABLE IF NOT EXISTS indicators_daily (
    scrip             VARCHAR(20) NOT NULL,
    date              DATE NOT NULL,
    close             DOUBLE PRECISION NOT NULL,
    sma_20            DOUBLE PRECISION,
    sma_50            DOUBLE PRECISION,
    sma_200           DOUBLE PRECISION,
    ema_12            DOUBLE PRECISION,
    ema_26            DOUBLE PRECISION,
    rsi_14            DOUBLE PRECISION,
    macd              DOUBLE PRECISION,
    macd_signal       DOUBLE PRECISION,
    macd_histogram    DOUBLE PRECISION,
    bollinger_upper   DOUBLE PRECISION,
    bollinger_middle  DOUBLE PRECISION,
    bollinger_lower   DOUBLE PRECISION,
    atr_14            DOUBLE PRECISION,
    adx_14            DOUBLE PRECISION,
    volume_sma_20     DOUBLE PRECISION,
    computed_at       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, date)
);
CREATE INDEX IF NOT EXISTS ix_indicators_date ON indicators_daily(date DESC);

-- --------------------------------------------------- peer_rankings_quarterly
CREATE TABLE IF NOT EXISTS peer_rankings_quarterly (
    scrip                   VARCHAR(20) NOT NULL,
    sector                  TEXT NOT NULL,
    fiscal_year_bs          INTEGER NOT NULL,
    quarter                 INTEGER NOT NULL,
    metric_name             TEXT NOT NULL,
    value                   DOUBLE PRECISION NOT NULL,
    rank_in_sector          INTEGER NOT NULL,
    percentile_in_sector    DOUBLE PRECISION NOT NULL,
    sector_median           DOUBLE PRECISION NOT NULL,
    sector_mean             DOUBLE PRECISION NOT NULL,
    computed_at             TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter, metric_name)
);
CREATE INDEX IF NOT EXISTS ix_peer_metric ON peer_rankings_quarterly(metric_name, fiscal_year_bs, quarter);

-- --------------------------------------------------- stage1_screen_results
CREATE TABLE IF NOT EXISTS stage1_screen_results (
    scrip                   VARCHAR(20) NOT NULL,
    sector                  TEXT NOT NULL,
    fiscal_year_bs          INTEGER NOT NULL,
    quarter                 INTEGER NOT NULL,
    profitability_score     DOUBLE PRECISION NOT NULL,
    revenue_growth_score    DOUBLE PRECISION NOT NULL,
    return_ratio_score      DOUBLE PRECISION NOT NULL,
    composite_score         DOUBLE PRECISION NOT NULL,
    passed                  BOOLEAN NOT NULL,
    rank                    INTEGER NOT NULL,
    computed_at             TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- --------------------------------------------------- stage2_bank_screen
CREATE TABLE IF NOT EXISTS stage2_bank_screen (
    scrip              VARCHAR(20) NOT NULL,
    sector             TEXT,
    fiscal_year_bs     INTEGER NOT NULL,
    quarter            INTEGER NOT NULL,
    roe                DOUBLE PRECISION,
    roe_percentile     DOUBLE PRECISION,
    roa                DOUBLE PRECISION,
    roa_percentile     DOUBLE PRECISION,
    net_margin         DOUBLE PRECISION,
    net_margin_percentile DOUBLE PRECISION,
    npl_ratio          DOUBLE PRECISION,
    npl_percentile     DOUBLE PRECISION,
    car                DOUBLE PRECISION,
    car_percentile     DOUBLE PRECISION,
    cd_ratio           DOUBLE PRECISION,
    cd_percentile      DOUBLE PRECISION,
    composite_score    DOUBLE PRECISION NOT NULL,
    flags              TEXT[] NOT NULL DEFAULT '{}',
    computed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------------- valuation
CREATE TABLE IF NOT EXISTS valuation (
    scrip                    VARCHAR(20) NOT NULL,
    date                     DATE NOT NULL,
    pe_trailing              DOUBLE PRECISION,
    pe_forward               DOUBLE PRECISION,
    pb                       DOUBLE PRECISION,
    peer_pe_median           DOUBLE PRECISION,
    peer_pb_median           DOUBLE PRECISION,
    pe_vs_peer_pct           DOUBLE PRECISION,
    fair_value_forward_eps   DOUBLE PRECISION,
    upside_pct               DOUBLE PRECISION,
    computed_at              TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, date)
);

-- ---------------------------------------------------------- index_snapshots
CREATE TABLE IF NOT EXISTS index_snapshots (
    index_name        TEXT NOT NULL,
    date              DATE NOT NULL,
    open              DOUBLE PRECISION NOT NULL,
    high              DOUBLE PRECISION NOT NULL,
    low               DOUBLE PRECISION NOT NULL,
    close             DOUBLE PRECISION NOT NULL,
    turnover          DOUBLE PRECISION,
    change            DOUBLE PRECISION,
    percent_change    DOUBLE PRECISION,
    computed_at       TIMESTAMPTZ,
    PRIMARY KEY (index_name, date)
);

-- ----------------------------------------------------------- news_articles
-- article_id = SHA1(url)[:16] from the silver transform; body stored here
-- NULL until news_embedder fetches it. Body embedding lives in a separate
-- table to keep news_articles hot for metadata lookups.
CREATE TABLE IF NOT EXISTS news_articles (
    article_id      VARCHAR(64) PRIMARY KEY,
    url             TEXT NOT NULL UNIQUE,
    source          TEXT NOT NULL,
    published_at    TIMESTAMPTZ NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    language        VARCHAR(8) NOT NULL DEFAULT 'en',
    scrip_tags      TEXT[] NOT NULL DEFAULT '{}',
    sector_tags     TEXT[] NOT NULL DEFAULT '{}',
    event_type      TEXT NOT NULL DEFAULT 'other',
    ingested_at     TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_news_scrip_tags    ON news_articles USING GIN (scrip_tags);
CREATE INDEX IF NOT EXISTS ix_news_published_at  ON news_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS ix_news_title_trgm    ON news_articles USING GIN (title gin_trgm_ops);

-- ------------------------------------------------------------ query_traces
-- Operational table — not synced from the lakehouse. Every agent turn
-- appends one row here for compliance + debug + evaluation.
CREATE TABLE IF NOT EXISTS query_traces (
    trace_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 TEXT,
    session_id              TEXT,
    query_text              TEXT NOT NULL,
    intent_classification   JSONB,
    tool_calls              JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_response          TEXT,
    total_latency_ms        INTEGER NOT NULL,
    input_tokens            INTEGER,
    output_tokens           INTEGER,
    model_used              TEXT,
    cache_hit               BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_query_traces_created_at ON query_traces(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_query_traces_session    ON query_traces(session_id);
