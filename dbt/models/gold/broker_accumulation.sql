{# -
    gold.broker_accumulation — which brokers are steadily accumulating (or
    distributing) a scrip across the available floor-sheet window.

    For each (scrip, broker) over all loaded days:
      * cumulative net_qty (buy − sell) and net_amount
      * the broker's share of the scrip's total traded volume
      * days active, days net-buying (persistence of the behaviour)
      * accumulation_rank (1 = biggest net accumulator of the scrip)

    accumulation_flag fires when a broker is a *persistent, material* net
    buyer: net-positive on the majority of its active days, ≥ 15% of the
    scrip's traded volume, and a positive cumulative net. That is the
    "an operator is quietly building a position" signal the desk wants.
    Symmetrically, distribution_flag marks persistent net sellers.

    As more days load, this naturally becomes a longer-window view; with a
    single day it reduces to that day's net. Research Q1 (accumulation /
    distribution zones, operator behaviour) + Q12 (continuous monitoring).
- #}
{{
    config(
        location=gold_external_location(),
        description='Per (scrip, broker): cumulative net flow, volume share, persistence, accumulation/distribution rank + flags.',
    )
}}

with flow as (
    select scrip, broker, trade_date, buy_qty, sell_qty, net_qty, net_amount
    from {{ ref('broker_flow_daily') }}
),

scrip_totals as (
    select scrip, sum(buy_qty + sell_qty) as scrip_total_sides
    from flow group by scrip
),

per_broker as (
    select
        scrip,
        broker,
        sum(net_qty)                                    as cum_net_qty,
        sum(net_amount)                                 as cum_net_amount,
        sum(buy_qty)                                    as cum_buy_qty,
        sum(sell_qty)                                   as cum_sell_qty,
        sum(buy_qty + sell_qty)                         as broker_volume,
        cast(count(distinct trade_date) as bigint)             as days_active,
        cast(sum(case when net_qty > 0 then 1 else 0 end) as bigint) as days_net_buy,
        cast(sum(case when net_qty < 0 then 1 else 0 end) as bigint) as days_net_sell,
        min(trade_date)                                 as first_day,
        max(trade_date)                                 as last_day
    from flow
    group by scrip, broker
)

select
    b.scrip,
    b.broker,
    b.cum_net_qty,
    b.cum_net_amount,
    b.cum_buy_qty,
    b.cum_sell_qty,
    b.broker_volume,
    case when t.scrip_total_sides > 0
         then b.broker_volume / t.scrip_total_sides else 0 end as volume_share,
    b.days_active,
    b.days_net_buy,
    b.days_net_sell,
    b.first_day,
    b.last_day,
    rank() over (partition by b.scrip order by b.cum_net_qty desc) as accumulation_rank,
    rank() over (partition by b.scrip order by b.cum_net_qty asc)  as distribution_rank,
    (
        b.cum_net_qty > 0
        and b.days_net_buy >= greatest(1, ceil(b.days_active * 0.6))
        and (t.scrip_total_sides > 0 and b.broker_volume / t.scrip_total_sides >= 0.15)
    ) as accumulation_flag,
    (
        b.cum_net_qty < 0
        and b.days_net_sell >= greatest(1, ceil(b.days_active * 0.6))
        and (t.scrip_total_sides > 0 and b.broker_volume / t.scrip_total_sides >= 0.15)
    ) as distribution_flag,
    current_timestamp as computed_at
from per_broker b
join scrip_totals t using (scrip)
