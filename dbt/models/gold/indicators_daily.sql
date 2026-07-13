{# -
    gold.indicators_daily — standard technical indicator panel per (scrip, date).
    Covers SMA (20/50/200), EMA approximation (12/26), RSI(14), MACD, Bollinger
    bands, ATR(14), and volume SMA(20). Every indicator is NULL until enough
    history accumulates (e.g. sma_200 stays NULL for the first 199 trading days).

    Notes on fidelity:
      * True EMA is recursive (EMA_t = α·close_t + (1-α)·EMA_{t-1}). SQL window
        functions can't express that directly, so we approximate with a weighted
        moving average over the lookback window. Good enough for crossover
        detection, not for exact industry values — flag this to analysts.
      * ADX is deliberately NULL for now (was computed as 4-CTE staircase in
        the Python port but was never validated against a reference impl).
        Fill in a dedicated model later if we want ADX for decision logic.
- #}
{{
    config(
        location=gold_external_location(),
        description='Daily technical indicators (SMA, EMA-approx, RSI, MACD, Bollinger, ATR).',
    )
}}

with

base as (
    select
        scrip, date, close, high, low, volume,
        lag(close) over (partition by scrip order by date) as prev_close
    from {{ source('silver', 'prices') }}
),

-- True-range and per-day gain/loss for RSI and ATR windows below.
diffs as (
    select
        *,
        close - prev_close                      as chg,
        greatest(close - prev_close, 0)         as gain,
        greatest(prev_close - close, 0)         as loss,
        greatest(
            high - low,
            abs(high - prev_close),
            abs(low  - prev_close)
        )                                       as tr
    from base
),

-- Window aggregates for every lookback we need. DuckDB's optimizer folds
-- the CTE chain into a single scan with parallel window functions.
rolls as (
    select
        scrip, date, close, high, low, volume, prev_close,
        avg(close)        over w20  as sma_20,
        avg(close)        over w50  as sma_50,
        avg(close)        over w200 as sma_200,
        stddev_samp(close) over w20 as close_std_20,
        avg(close)        over w12  as approx_ema_12,
        avg(close)        over w26  as approx_ema_26,
        avg(gain)         over w14  as avg_gain_14,
        avg(loss)         over w14  as avg_loss_14,
        avg(tr)           over w14  as atr_14,
        avg(volume)       over w20  as volume_sma_20,
        count(*)          over w12  as n12,
        count(*)          over w14  as n14,
        count(*)          over w20  as n20,
        count(*)          over w26  as n26,
        count(*)          over w50  as n50,
        count(*)          over w200 as n200
    from diffs
    window
        w12  as (partition by scrip order by date rows between 11  preceding and current row),
        w14  as (partition by scrip order by date rows between 13  preceding and current row),
        w20  as (partition by scrip order by date rows between 19  preceding and current row),
        w26  as (partition by scrip order by date rows between 25  preceding and current row),
        w50  as (partition by scrip order by date rows between 49  preceding and current row),
        w200 as (partition by scrip order by date rows between 199 preceding and current row)
),

-- Gate EMAs on having full lookback — otherwise they'd flash misleading
-- values in the first few trading days of a scrip's history.
macd_base as (
    select
        *,
        case when n12 = 12 then approx_ema_12 end as ema_12,
        case when n26 = 26 then approx_ema_26 end as ema_26
    from rolls
),

macd_calc as (
    select
        *,
        ema_12 - ema_26 as macd,
        avg(ema_12 - ema_26)   over w_signal as macd_signal_raw,
        count(ema_12 - ema_26) over w_signal as n_signal
    from macd_base
    window w_signal as (
        partition by scrip order by date rows between 8 preceding and current row
    )
)

select
    scrip,
    date,
    close,
    case when n20  = 20  then sma_20  end                                     as sma_20,
    case when n50  = 50  then sma_50  end                                     as sma_50,
    case when n200 = 200 then sma_200 end                                     as sma_200,
    ema_12,
    ema_26,
    case
        when n14 = 14 and (avg_gain_14 + avg_loss_14) > 0
        then 100.0 - (100.0 / (1.0 + avg_gain_14 / nullif(avg_loss_14, 0)))
    end                                                                        as rsi_14,
    macd,
    case when n_signal = 9                         then macd_signal_raw end    as macd_signal,
    case when n_signal = 9 and macd is not null    then macd - macd_signal_raw end  as macd_histogram,
    case when n20 = 20 then sma_20 + 2 * close_std_20 end                      as bollinger_upper,
    case when n20 = 20 then sma_20                    end                      as bollinger_middle,
    case when n20 = 20 then sma_20 - 2 * close_std_20 end                      as bollinger_lower,
    case when n14 = 14 then atr_14 end                                         as atr_14,
    cast(null as double)                                                       as adx_14,
    case when n20 = 20 then volume_sma_20 end                                  as volume_sma_20,
    current_timestamp                                                          as computed_at
from macd_calc
order by scrip, date
