{# -
    gold.price_returns — one row per scrip with trailing-period returns
    and drawdown metrics, as of the latest observable close.

    Emit a snapshot per scrip rather than a historical time-series —
    a time-series of trailing returns is ~30M rows and has marginal use
    over silver.closes + indicators_daily, which are already there.
    The snapshot form is what the LLM tool layer + UI cards want.

    Columns:
      return_{1m,3m,6m,1y,3y,5y}    — close vs close N trading days ago
      drawdown_from_peak            — current close vs all-time high
      realized_vol_20d              — stdev of log returns over last 20
      in_20d_range_high             — close / 20d high, flag proximity to breakout
      in_20d_range_low              — close / 20d low

    Sources silver.prices — the canonical all-sector OHLCV series (same
    source indicators_daily uses). Deep history comes from the SMTM live
    feed plus the GitHub community backfill (github_nepse_data, scraped
    tier); sectors/scrips without enough history simply get NULL long-window
    returns until more accrues.
- #}
{{
    config(
        location=gold_external_location(),
        description='Snapshot per scrip: trailing returns, drawdown, realized vol.',
    )
}}

with base as (
    select scrip, date, close
    from {{ source('silver', 'prices') }}
),

-- Step 1: compute daily log-returns. We need this in its own CTE because
-- DuckDB rejects nested window functions — can't stddev() over a window
-- of lag() values in the same select.
with_log_returns as (
    select
        scrip, date, close,
        ln(close * 1.0 / nullif(lag(close, 1) over (partition by scrip order by date), 0)) as log_return
    from base
),

with_lags as (
    select
        scrip, date, close, log_return,
        -- Lookback in TRADING days (~252/yr, ~22/mo).
        lag(close, 22)   over w as close_1m_ago,
        lag(close, 66)   over w as close_3m_ago,
        lag(close, 132)  over w as close_6m_ago,
        lag(close, 252)  over w as close_1y_ago,
        lag(close, 756)  over w as close_3y_ago,
        lag(close, 1260) over w as close_5y_ago,
        -- Peak-to-date for drawdown.
        max(close) over (partition by scrip order by date rows between unbounded preceding and current row) as running_peak,
        -- 20-day envelope.
        min(close) over w20 as low_20d,
        max(close) over w20 as high_20d,
        -- 20-day volatility = stdev of log-returns (already computed above).
        stddev_samp(log_return) over w20 as realized_vol_20d
    from with_log_returns
    window
        w   as (partition by scrip order by date),
        w20 as (partition by scrip order by date rows between 19 preceding and current row)
)

-- Emit only the latest row per scrip.
select
    scrip,
    date                                                     as as_of,
    close,
    (close - close_1m_ago)  / nullif(close_1m_ago,  0)       as return_1m,
    (close - close_3m_ago)  / nullif(close_3m_ago,  0)       as return_3m,
    (close - close_6m_ago)  / nullif(close_6m_ago,  0)       as return_6m,
    (close - close_1y_ago)  / nullif(close_1y_ago,  0)       as return_1y,
    (close - close_3y_ago)  / nullif(close_3y_ago,  0)       as return_3y,
    (close - close_5y_ago)  / nullif(close_5y_ago,  0)       as return_5y,
    (close - running_peak)  / nullif(running_peak,  0)       as drawdown_from_peak,
    realized_vol_20d,
    -- Position within the 20-day channel: 1.0 = at 20d high, 0.0 = at 20d low.
    case
        when high_20d - low_20d > 0
        then (close - low_20d) * 1.0 / (high_20d - low_20d)
    end                                                       as position_in_20d_range,
    current_timestamp                                         as computed_at
from with_lags
qualify row_number() over (partition by scrip order by date desc) = 1
