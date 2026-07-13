{# -
    gold.broker_flow_daily — per-broker buy/sell/net flow per scrip per day.

    The atomic building block for every downstream microstructure model
    (concentration, accumulation, smart-money). Each floorsheet trade
    contributes to TWO broker rows: the buyer accumulates buy-side volume,
    the seller accumulates sell-side volume. We unpivot the trade into its
    two sides, then aggregate.

    net_qty > 0  ⇒ broker was a net accumulator of the scrip that day.
    Research Q1 ("broker-wise net buying / selling pattern").
- #}
{{
    config(
        location=gold_external_location(),
        description='Per (scrip, broker, trade_date): buy/sell/net quantity + amount and trade counts.',
    )
}}

with sides as (
    select scrip, trade_date, buyer_broker  as broker, quantity, amount, 'B' as side
    from {{ source('silver', 'floorsheet') }}
    union all
    select scrip, trade_date, seller_broker as broker, quantity, amount, 'S' as side
    from {{ source('silver', 'floorsheet') }}
)

select
    scrip,
    broker,
    trade_date,
    sum(case when side = 'B' then quantity else 0 end)            as buy_qty,
    sum(case when side = 'S' then quantity else 0 end)            as sell_qty,
    sum(case when side = 'B' then quantity else -quantity end)    as net_qty,
    sum(case when side = 'B' then amount   else 0 end)            as buy_amount,
    sum(case when side = 'S' then amount   else 0 end)            as sell_amount,
    sum(case when side = 'B' then amount   else -amount end)      as net_amount,
    cast(sum(case when side = 'B' then 1 else 0 end) as bigint)   as buy_trades,
    cast(sum(case when side = 'S' then 1 else 0 end) as bigint)   as sell_trades,
    cast(count(*) as bigint)                                      as trade_sides,
    current_timestamp                                            as computed_at
from sides
group by scrip, broker, trade_date
