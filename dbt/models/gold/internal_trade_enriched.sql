{# -
    gold.internal_trade_enriched — the firm's own fills joined to the public
    floor sheet + price history, one row per internal fill. Surveillance spine.

    Recovers (by contract_number) the broker the fund used and the counterparty
    broker, then attaches every execution/outcome benchmark downstream scoring
    needs — all date-aligned to the trade, not snapshots:

      * day VWAP + day range        — from the floor sheet itself
      * interval VWAP (±15 min)     — the prevailing market around the fill,
                                      excluding the fill's own contract; far
                                      fairer than whole-day VWAP on trending days
      * vol_20d                     — stdev of daily log-returns over the 20
                                      trading days up to the trade date, so
                                      slippage can be scored in sigmas, not a
                                      one-size-fits-all percent
      * prior 20d high/low          — was the fund buying at the top of the range?
      * markouts (T+1/T+5/T+20)     — post-trade price drift, signed so NEGATIVE
                                      is adverse for the fund on either side
                                      (we bought and it fell / we sold and it rose).
                                      Systematically negative markouts are the
                                      "we keep ending up the bagholder" signal.
- #}
{{
    config(
        location=gold_external_location(),
        description='Per internal fill: broker/counterparty + day & interval VWAP, vol, prior range, post-trade markouts.',
    )
}}

with it as (
    select
        scrip, contract_number, client_code, client_name, side,
        quantity as our_qty, price as our_price, value as our_value,
        order_id, traded_at, trade_date,
        cast(trade_date as date) as trade_date_d
    from {{ source('silver', 'internal_trades') }}
),

fs as (
    select contract_number, buyer_broker, seller_broker
    from {{ source('silver', 'floorsheet') }}
),

-- Per scrip/day VWAP + traded range straight from the floor sheet.
day_fs as (
    select
        scrip,
        trade_date,
        sum(amount) / nullif(sum(quantity), 0) as day_vwap,
        min(rate) as day_low_fs,
        max(rate) as day_high_fs
    from {{ source('silver', 'floorsheet') }}
    group by scrip, trade_date
),

-- The prevailing market ±15 minutes around each fill, excluding the fill's own
-- contract so a thinly-traded scrip can't benchmark a fill against itself.
ivwap as (
    select
        it.contract_number, it.client_code, it.side,
        sum(f.amount) / nullif(sum(f.quantity), 0) as interval_vwap,
        count(*) as n_interval_trades
    from it
    join {{ source('silver', 'floorsheet') }} f
      on f.scrip = it.scrip
     and f.trade_date = it.trade_date
     and f.contract_number != it.contract_number
     and abs(date_diff('second', f.traded_at, it.traded_at)) <= 900
    group by 1, 2, 3
),

-- Daily price history with trading-day row numbers (for markout offsets).
-- Two CTEs because DuckDB rejects nested window functions.
px_base as (
    select
        scrip, date, close,
        ln(close * 1.0 / nullif(lag(close) over (partition by scrip order by date), 0)) as log_ret
    from {{ source('silver', 'prices') }}
),
px as (
    select
        scrip, date, close,
        row_number() over (partition by scrip order by date) as rn,
        stddev_samp(log_ret) over (
            partition by scrip order by date rows between 19 preceding and current row
        ) as vol_20d,
        max(close) over (
            partition by scrip order by date rows between 20 preceding and 1 preceding
        ) as prior_high_20d,
        min(close) over (
            partition by scrip order by date rows between 20 preceding and 1 preceding
        ) as prior_low_20d
    from px_base
),

-- The price row at-or-before each fill's trade date (ASOF = latest such bar).
base as (
    select
        it.*,
        p.rn as base_rn,
        p.vol_20d,
        p.prior_high_20d,
        p.prior_low_20d,
        p.close as day_close,
        p.date as base_px_date
    from it
    asof left join px p
      on p.scrip = it.scrip and p.date <= it.trade_date_d
)

select
    b.contract_number,
    b.scrip,
    b.trade_date,
    b.client_code,
    b.client_name,
    b.side,
    b.our_qty,
    b.our_price,
    b.our_value,
    b.order_id,
    b.traded_at,
    case when b.side = 'B' then fs.buyer_broker else fs.seller_broker end as our_broker,
    case when b.side = 'B' then fs.seller_broker else fs.buyer_broker end as counterparty_broker,
    d.day_vwap,
    d.day_high_fs,
    d.day_low_fs,
    iv.interval_vwap,
    coalesce(iv.n_interval_trades, 0) as n_interval_trades,
    b.vol_20d,
    b.prior_high_20d,
    b.prior_low_20d,
    b.day_close,
    t1.close  as close_t1,
    t5.close  as close_t5,
    t20.close as close_t20,
    -- Markouts: negative = adverse for the fund on either side.
    case when t1.close is not null then
        (case when b.side = 'B' then (t1.close - b.our_price) else (b.our_price - t1.close) end) / b.our_price
    end as markout_1d_pct,
    case when t5.close is not null then
        (case when b.side = 'B' then (t5.close - b.our_price) else (b.our_price - t5.close) end) / b.our_price
    end as markout_5d_pct,
    case when t20.close is not null then
        (case when b.side = 'B' then (t20.close - b.our_price) else (b.our_price - t20.close) end) / b.our_price
    end as markout_20d_pct,
    (fs.contract_number is not null) as matched_floorsheet,
    current_timestamp as computed_at
from base b
left join fs on fs.contract_number = b.contract_number
left join day_fs d on d.scrip = b.scrip and d.trade_date = b.trade_date
left join ivwap iv
       on iv.contract_number = b.contract_number
      and iv.client_code = b.client_code
      and iv.side = b.side
left join px t1  on t1.scrip = b.scrip and t1.rn  = b.base_rn + 1
left join px t5  on t5.scrip = b.scrip and t5.rn  = b.base_rn + 5
left join px t20 on t20.scrip = b.scrip and t20.rn = b.base_rn + 20
