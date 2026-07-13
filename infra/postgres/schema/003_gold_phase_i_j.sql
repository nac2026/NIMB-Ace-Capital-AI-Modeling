-- Phase-I + Phase-J Gold tables — written by dbt models at dbt/models/gold/*.sql
-- as Parquet files on MinIO. Synced into Postgres via nrc_processing.sync_postgres.
--
-- Column order here MUST match the `_SYNC` entry in sync_postgres.py so
-- COPY can load without naming columns. Every table is TRUNCATE + COPY
-- semantics — no UPSERT. `computed_at` is the only non-data column.

-- =====================================================================
-- Phase I — bank financial analytics
-- =====================================================================

-- ---------------------------------------------------------- ttm_fundamentals
CREATE TABLE IF NOT EXISTS ttm_fundamentals (
    scrip                       VARCHAR(20) NOT NULL,
    fiscal_year_bs              INTEGER NOT NULL,
    quarter                     SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    ttm_net_profit              DOUBLE PRECISION,
    ttm_operating_profit        DOUBLE PRECISION,
    ttm_profit_before_tax       DOUBLE PRECISION,
    ttm_interest_income         DOUBLE PRECISION,
    ttm_interest_expense        DOUBLE PRECISION,
    ttm_net_interest_income     DOUBLE PRECISION,
    ttm_fees_income             DOUBLE PRECISION,
    ttm_net_fees_income         DOUBLE PRECISION,
    ttm_net_trading_income      DOUBLE PRECISION,
    ttm_other_operating_income  DOUBLE PRECISION,
    ttm_total_operating_income  DOUBLE PRECISION,
    ttm_net_operating_income    DOUBLE PRECISION,
    ttm_impairment_charge       DOUBLE PRECISION,
    ttm_staff_expenses          DOUBLE PRECISION,
    ttm_other_opex              DOUBLE PRECISION,
    ttm_depreciation            DOUBLE PRECISION,
    ttm_income_tax              DOUBLE PRECISION,
    total_assets                DOUBLE PRECISION,
    total_loans                 DOUBLE PRECISION,
    loans_to_customers          DOUBLE PRECISION,
    total_deposits              DOUBLE PRECISION,
    shareholders_equity         DOUBLE PRECISION,
    paid_up_capital             DOUBLE PRECISION,
    retained_earnings           DOUBLE PRECISION,
    ttm_roa                     DOUBLE PRECISION,
    ttm_roe                     DOUBLE PRECISION,
    ttm_nim                     DOUBLE PRECISION,
    n_quarters_in_window        BIGINT,
    computed_at                 TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- quarterly_growth
-- 48 columns — 11 metrics × 4 values each (current + QoQ/YoY/3y growth) + scrip/fy/q + computed_at.
CREATE TABLE IF NOT EXISTS quarterly_growth (
    scrip                              VARCHAR(20) NOT NULL,
    fiscal_year_bs                     INTEGER NOT NULL,
    quarter                            SMALLINT NOT NULL,
    net_profit                         DOUBLE PRECISION,
    net_profit_qoq_pct                 DOUBLE PRECISION,
    net_profit_yoy_pct                 DOUBLE PRECISION,
    net_profit_3y_pct                  DOUBLE PRECISION,
    operating_profit                   DOUBLE PRECISION,
    operating_profit_qoq_pct           DOUBLE PRECISION,
    operating_profit_yoy_pct           DOUBLE PRECISION,
    operating_profit_3y_pct            DOUBLE PRECISION,
    profit_before_tax                  DOUBLE PRECISION,
    profit_before_tax_qoq_pct          DOUBLE PRECISION,
    profit_before_tax_yoy_pct          DOUBLE PRECISION,
    profit_before_tax_3y_pct           DOUBLE PRECISION,
    net_interest_income                DOUBLE PRECISION,
    net_interest_income_qoq_pct        DOUBLE PRECISION,
    net_interest_income_yoy_pct        DOUBLE PRECISION,
    net_interest_income_3y_pct         DOUBLE PRECISION,
    total_operating_income             DOUBLE PRECISION,
    total_operating_income_qoq_pct     DOUBLE PRECISION,
    total_operating_income_yoy_pct     DOUBLE PRECISION,
    total_operating_income_3y_pct      DOUBLE PRECISION,
    net_fees_income                    DOUBLE PRECISION,
    net_fees_income_qoq_pct            DOUBLE PRECISION,
    net_fees_income_yoy_pct            DOUBLE PRECISION,
    net_fees_income_3y_pct             DOUBLE PRECISION,
    staff_expenses                     DOUBLE PRECISION,
    staff_expenses_qoq_pct             DOUBLE PRECISION,
    staff_expenses_yoy_pct             DOUBLE PRECISION,
    staff_expenses_3y_pct              DOUBLE PRECISION,
    total_assets                       DOUBLE PRECISION,
    total_assets_qoq_pct               DOUBLE PRECISION,
    total_assets_yoy_pct               DOUBLE PRECISION,
    total_assets_3y_pct                DOUBLE PRECISION,
    total_loans                        DOUBLE PRECISION,
    total_loans_qoq_pct                DOUBLE PRECISION,
    total_loans_yoy_pct                DOUBLE PRECISION,
    total_loans_3y_pct                 DOUBLE PRECISION,
    total_deposits                     DOUBLE PRECISION,
    total_deposits_qoq_pct             DOUBLE PRECISION,
    total_deposits_yoy_pct             DOUBLE PRECISION,
    total_deposits_3y_pct              DOUBLE PRECISION,
    shareholders_equity                DOUBLE PRECISION,
    shareholders_equity_qoq_pct        DOUBLE PRECISION,
    shareholders_equity_yoy_pct        DOUBLE PRECISION,
    shareholders_equity_3y_pct         DOUBLE PRECISION,
    computed_at                        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- dupont_decomposition
CREATE TABLE IF NOT EXISTS dupont_decomposition (
    scrip              VARCHAR(20) NOT NULL,
    fiscal_year_bs     INTEGER NOT NULL,
    quarter            SMALLINT NOT NULL,
    roe_computed       DOUBLE PRECISION,
    roa                DOUBLE PRECISION,
    equity_multiplier  DOUBLE PRECISION,
    net_profit_margin  DOUBLE PRECISION,
    asset_turnover     DOUBLE PRECISION,
    tax_burden         DOUBLE PRECISION,
    interest_burden    DOUBLE PRECISION,
    operating_margin   DOUBLE PRECISION,
    nim                DOUBLE PRECISION,
    computed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- cost_efficiency
CREATE TABLE IF NOT EXISTS cost_efficiency (
    scrip                    VARCHAR(20) NOT NULL,
    fiscal_year_bs           INTEGER NOT NULL,
    quarter                  SMALLINT NOT NULL,
    cost_to_income_ratio     DOUBLE PRECISION,
    staff_cost_ratio         DOUBLE PRECISION,
    other_opex_ratio         DOUBLE PRECISION,
    depreciation_ratio       DOUBLE PRECISION,
    revenue_per_asset        DOUBLE PRECISION,
    operating_margin         DOUBLE PRECISION,
    total_opex               DOUBLE PRECISION,
    total_operating_income   DOUBLE PRECISION,
    computed_at              TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- revenue_quality
CREATE TABLE IF NOT EXISTS revenue_quality (
    scrip                           VARCHAR(20) NOT NULL,
    fiscal_year_bs                  INTEGER NOT NULL,
    quarter                         SMALLINT NOT NULL,
    nii_share                       DOUBLE PRECISION,
    fees_share                      DOUBLE PRECISION,
    trading_share                   DOUBLE PRECISION,
    other_income_share              DOUBLE PRECISION,
    revenue_diversification_score   DOUBLE PRECISION,
    earnings_cv_8q                  DOUBLE PRECISION,
    n_quarters_in_cv_window         BIGINT,
    computed_at                     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- asset_quality_trends
CREATE TABLE IF NOT EXISTS asset_quality_trends (
    scrip                     VARCHAR(20) NOT NULL,
    fiscal_year_bs            INTEGER NOT NULL,
    quarter                   SMALLINT NOT NULL,
    npl_ratio                 DOUBLE PRECISION,
    llp_to_npl_ratio          DOUBLE PRECISION,
    npl_qoq_change_abs        DOUBLE PRECISION,
    npl_yoy_change_abs        DOUBLE PRECISION,
    llp_coverage_yoy_change   DOUBLE PRECISION,
    credit_loss_rate_ttm      DOUBLE PRECISION,
    asset_quality_tier        TEXT,
    computed_at               TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- capital_strength
CREATE TABLE IF NOT EXISTS capital_strength (
    scrip            VARCHAR(20) NOT NULL,
    fiscal_year_bs   INTEGER NOT NULL,
    quarter          SMALLINT NOT NULL,
    car              DOUBLE PRECISION,
    tier1_capital    DOUBLE PRECISION,
    tier2_capital    DOUBLE PRECISION,
    total_capital    DOUBLE PRECISION,
    tier1_share      DOUBLE PRECISION,
    car_buffer       DOUBLE PRECISION,
    car_yoy_change   DOUBLE PRECISION,
    capital_tier     TEXT,
    computed_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- dividend_yield
-- Annual table — no quarter key.
CREATE TABLE IF NOT EXISTS dividend_yield (
    scrip                     VARCHAR(20) NOT NULL,
    fiscal_year_bs            INTEGER NOT NULL,
    annual_cash_div_pct       DOUBLE PRECISION,
    annual_bonus_pct          DOUBLE PRECISION,
    market_value_per_share    DOUBLE PRECISION,
    cash_dividend_yield       DOUBLE PRECISION,
    total_dividend_yield      DOUBLE PRECISION,
    yield_tier                TEXT,
    computed_at               TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs)
);

-- ---------------------------------------------------------- piotroski_f_score
CREATE TABLE IF NOT EXISTS piotroski_f_score (
    scrip                   VARCHAR(20) NOT NULL,
    fiscal_year_bs          INTEGER NOT NULL,
    quarter                 SMALLINT NOT NULL,
    p1_positive_profit      INTEGER,
    p2_positive_roa         INTEGER,
    p3_profit_grew          INTEGER,
    p4_roa_improved         INTEGER,
    p5_npl_not_worse        INTEGER,
    p6_car_not_worse        INTEGER,
    p7_no_large_issuance    INTEGER,
    p8_nim_improved         INTEGER,
    p9_cti_improved         INTEGER,
    f_score                 INTEGER,
    n_signals_available     INTEGER,
    computed_at             TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- price_returns
-- Snapshot table — one row per scrip.
CREATE TABLE IF NOT EXISTS price_returns (
    scrip                    VARCHAR(20) PRIMARY KEY,
    as_of                    DATE,
    close                    DOUBLE PRECISION,
    return_1m                DOUBLE PRECISION,
    return_3m                DOUBLE PRECISION,
    return_6m                DOUBLE PRECISION,
    return_1y                DOUBLE PRECISION,
    return_3y                DOUBLE PRECISION,
    return_5y                DOUBLE PRECISION,
    drawdown_from_peak       DOUBLE PRECISION,
    realized_vol_20d         DOUBLE PRECISION,
    position_in_20d_range    DOUBLE PRECISION,
    computed_at              TIMESTAMPTZ NOT NULL
);

-- ----------------------------------------------- fundamental_quality_composite
CREATE TABLE IF NOT EXISTS fundamental_quality_composite (
    scrip                  VARCHAR(20) NOT NULL,
    sector                 TEXT,
    fiscal_year_bs         INTEGER NOT NULL,
    quarter                SMALLINT NOT NULL,
    profitability_pct      DOUBLE PRECISION,
    asset_quality_pct      DOUBLE PRECISION,
    growth_pct             DOUBLE PRECISION,
    capital_pct            DOUBLE PRECISION,
    efficiency_pct         DOUBLE PRECISION,
    piotroski_pct          DOUBLE PRECISION,
    quality_score_0_100    DOUBLE PRECISION,
    quality_tier           TEXT,
    computed_at            TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);
CREATE INDEX IF NOT EXISTS ix_fqc_tier ON fundamental_quality_composite(quality_tier);

-- ---------------------------------------------------------- quality_momentum_matrix
-- Snapshot — one row per active scrip.
CREATE TABLE IF NOT EXISTS quality_momentum_matrix (
    scrip                     VARCHAR(20) PRIMARY KEY,
    sector                    TEXT,
    latest_fy                 INTEGER,
    latest_quarter            SMALLINT,
    quality_score_0_100       DOUBLE PRECISION,
    quality_tier              TEXT,
    return_6m                 DOUBLE PRECISION,
    price_as_of               DATE,
    sector_quality_median     DOUBLE PRECISION,
    sector_return_6m_median   DOUBLE PRECISION,
    is_high_quality           BOOLEAN,
    is_high_momentum          BOOLEAN,
    quadrant                  TEXT,
    computed_at               TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_qmm_quadrant ON quality_momentum_matrix(quadrant);

-- =====================================================================
-- Phase J — extended analytics
-- =====================================================================

-- ---------------------------------------------------------- valuation_history
CREATE TABLE IF NOT EXISTS valuation_history (
    scrip                     VARCHAR(20) NOT NULL,
    fiscal_year_bs            INTEGER NOT NULL,
    quarter                   SMALLINT NOT NULL,
    pe_ratio                  DOUBLE PRECISION,
    pb_ratio                  DOUBLE PRECISION,
    pe_self_pct_5y            DOUBLE PRECISION,
    pb_self_pct_5y            DOUBLE PRECISION,
    pe_self_pct_all           DOUBLE PRECISION,
    n_quarters_in_5y_window   BIGINT,
    self_valuation_tier       TEXT,
    computed_at               TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- operating_leverage
CREATE TABLE IF NOT EXISTS operating_leverage (
    scrip                VARCHAR(20) NOT NULL,
    fiscal_year_bs       INTEGER NOT NULL,
    quarter              SMALLINT NOT NULL,
    op_leverage_raw      DOUBLE PRECISION,
    op_leverage_4q_avg   DOUBLE PRECISION,
    n_valid_quarters     BIGINT,
    op_leverage_tier     TEXT,
    computed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scrip, fiscal_year_bs, quarter)
);

-- ---------------------------------------------------------- market_cap_metrics
-- Snapshot — one row per scrip.
CREATE TABLE IF NOT EXISTS market_cap_metrics (
    scrip                    VARCHAR(20) PRIMARY KEY,
    as_of                    DATE,
    latest_close             DOUBLE PRECISION,
    shares_outstanding       DOUBLE PRECISION,
    market_cap_npr           DOUBLE PRECISION,
    market_cap_tier          TEXT,
    paid_up_capital_npr      DOUBLE PRECISION,
    bvps                     DOUBLE PRECISION,
    price_to_face_value      DOUBLE PRECISION,
    price_to_book_computed   DOUBLE PRECISION,
    computed_at              TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------- beta_and_volatility
-- Snapshot — one row per scrip.
CREATE TABLE IF NOT EXISTS beta_and_volatility (
    scrip                VARCHAR(20) PRIMARY KEY,
    as_of                DATE,
    n_obs                BIGINT,
    beta                 DOUBLE PRECISION,
    alpha_annual         DOUBLE PRECISION,
    r_squared            DOUBLE PRECISION,
    annualized_vol       DOUBLE PRECISION,
    annualized_return    DOUBLE PRECISION,
    sharpe_ratio_2y      DOUBLE PRECISION,
    computed_at          TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------- total_shareholder_return
-- Snapshot — one row per scrip.
CREATE TABLE IF NOT EXISTS total_shareholder_return (
    scrip          VARCHAR(20) PRIMARY KEY,
    as_of          DATE,
    close_today    DOUBLE PRECISION,
    close_1y_ago   DOUBLE PRECISION,
    close_3y_ago   DOUBLE PRECISION,
    close_5y_ago   DOUBLE PRECISION,
    div_1y         DOUBLE PRECISION,
    div_3y         DOUBLE PRECISION,
    div_5y         DOUBLE PRECISION,
    tsr_1y         DOUBLE PRECISION,
    tsr_3y         DOUBLE PRECISION,
    tsr_5y         DOUBLE PRECISION,
    computed_at    TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------- technical_signal_summary
-- Snapshot — one row per scrip.
CREATE TABLE IF NOT EXISTS technical_signal_summary (
    scrip                   VARCHAR(20) PRIMARY KEY,
    latest_indicator_date   DATE,
    close                   DOUBLE PRECISION,
    r1_trend                INTEGER,
    r2_ma_align             INTEGER,
    r3_rsi                  INTEGER,
    r4_macd                 INTEGER,
    r5_bollinger            INTEGER,
    signal_sum              INTEGER,
    technical_signal        TEXT,
    computed_at             TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------- sector_momentum
-- One row per sector.
CREATE TABLE IF NOT EXISTS sector_momentum (
    sector                 TEXT PRIMARY KEY,
    n_scrips               BIGINT,
    avg_return_3m          DOUBLE PRECISION,
    avg_return_6m          DOUBLE PRECISION,
    avg_return_1y          DOUBLE PRECISION,
    median_return_6m       DOUBLE PRECISION,
    return_6m_dispersion   DOUBLE PRECISION,
    min_return_6m          DOUBLE PRECISION,
    max_return_6m          DOUBLE PRECISION,
    rank_by_6m             BIGINT,
    momentum_tier          TEXT,
    computed_at            TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------- investment_scorecard
-- Snapshot — one row per active scrip. `recommendation` preserved as a
-- column for the LLM tool layer + API consumers; the default UI hides it
-- per the "data not verdicts" product principle.
CREATE TABLE IF NOT EXISTS investment_scorecard (
    scrip                    VARCHAR(20) PRIMARY KEY,
    sector                   TEXT,
    quality_pct              DOUBLE PRECISION,
    valuation_pct            DOUBLE PRECISION,
    momentum_pct             DOUBLE PRECISION,
    risk_pct                 DOUBLE PRECISION,
    income_pct               DOUBLE PRECISION,
    quality_score_0_100      DOUBLE PRECISION,
    pe_self_pct_5y           DOUBLE PRECISION,
    return_6m                DOUBLE PRECISION,
    sharpe_ratio_2y          DOUBLE PRECISION,
    total_dividend_yield     DOUBLE PRECISION,
    scorecard_0_100          DOUBLE PRECISION,
    recommendation           TEXT,
    computed_at              TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scorecard_recommendation ON investment_scorecard(recommendation);
