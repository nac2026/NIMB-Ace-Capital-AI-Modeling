{# -
    gold.technical_signal_summary — BUY / HOLD / SELL rollup per scrip
    from the technical indicator stack.

    Not a black-box ML prediction — just a transparent rules-based
    voting system. Each rule contributes -1 (bearish), 0 (neutral), or
    +1 (bullish). Sum ≥ 2 = BUY, ≤ -2 = SELL, in between = HOLD.

    Rules:
      R1 trend         close > sma_200             → +1
                       close < sma_200             → -1
      R2 ma_align      sma_20 > sma_50 > sma_200   → +1 (golden alignment)
                       sma_20 < sma_50 < sma_200   → -1 (death alignment)
      R3 momentum      rsi_14 < 30                 → +1 (oversold bounce)
                       rsi_14 > 70                 → -1 (overbought)
      R4 macd          macd > 0 & macd_histogram > 0 → +1
                       macd < 0 & macd_histogram < 0 → -1
      R5 bollinger     close < bollinger_lower    → +1 (oversold)
                       close > bollinger_upper    → -1 (overbought)

    Five rules. Sum range [-5, +5]. Publishes each sub-signal so the LLM
    can explain WHY the verdict came out the way it did.

    Depends on gold.indicators_daily (scraper-backed). If scraper data
    is stale, this reflects the stale state — caller should check
    `latest_indicator_date`.
- #}
{{
    config(
        location=gold_external_location(),
        description='Rules-based BUY/HOLD/SELL per scrip from technical indicators.',
    )
}}

with latest_indicators as (
    select *
    from {{ ref('indicators_daily') }}
    qualify row_number() over (partition by scrip order by date desc) = 1
),

signals as (
    select
        scrip,
        date                                                                as latest_indicator_date,
        close,
        sma_20, sma_50, sma_200,
        rsi_14, macd, macd_histogram,
        bollinger_upper, bollinger_lower,
        -- R1 Trend vs long MA
        case
            when sma_200 is null           then 0
            when close > sma_200           then  1
            when close < sma_200           then -1
            else                                0
        end as r1_trend,
        -- R2 MA alignment (golden / death)
        case
            when sma_20 is null or sma_50 is null or sma_200 is null then 0
            when sma_20 > sma_50 and sma_50 > sma_200                then  1
            when sma_20 < sma_50 and sma_50 < sma_200                then -1
            else                                                           0
        end as r2_ma_align,
        -- R3 RSI overbought/oversold
        case
            when rsi_14 is null             then 0
            when rsi_14 < 30                then  1
            when rsi_14 > 70                then -1
            else                                 0
        end as r3_rsi,
        -- R4 MACD direction
        case
            when macd is null or macd_histogram is null then 0
            when macd > 0 and macd_histogram > 0        then  1
            when macd < 0 and macd_histogram < 0        then -1
            else                                              0
        end as r4_macd,
        -- R5 Bollinger envelope
        case
            when bollinger_lower is null or bollinger_upper is null then 0
            when close < bollinger_lower                            then  1
            when close > bollinger_upper                            then -1
            else                                                          0
        end as r5_bollinger
    from latest_indicators
)

select
    scrip,
    latest_indicator_date,
    close,
    r1_trend, r2_ma_align, r3_rsi, r4_macd, r5_bollinger,
    r1_trend + r2_ma_align + r3_rsi + r4_macd + r5_bollinger as signal_sum,
    case
        when r1_trend + r2_ma_align + r3_rsi + r4_macd + r5_bollinger >=  3 then 'STRONG_BUY'
        when r1_trend + r2_ma_align + r3_rsi + r4_macd + r5_bollinger >=  1 then 'BUY'
        when r1_trend + r2_ma_align + r3_rsi + r4_macd + r5_bollinger <= -3 then 'STRONG_SELL'
        when r1_trend + r2_ma_align + r3_rsi + r4_macd + r5_bollinger <= -1 then 'SELL'
        else                                                                     'HOLD'
    end as technical_signal,
    current_timestamp as computed_at
from signals
order by scrip
