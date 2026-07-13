{# -
    gold.broker_concentration_daily — how concentrated is trading in a few
    brokers' hands, per scrip per day.

    HHI (Herfindahl-Hirschman Index) = Σ(broker volume share)², on a 0..1
    scale where 1.0 = a single broker did all the volume. Computed
    separately for the buy side and sell side, plus combined.

    dominance_flag: the single biggest broker did > 30% of a side's volume.
    control_flag:   the top 3 brokers did > 60% of a side's volume.

    These are the per-day signals that feed broker_accumulation (sustained
    control across days) and speculation_score. Research Q1
    ("accumulation / distribution zones — operator behaviour").
- #}
{{
    config(
        location=gold_external_location(),
        description='Per (scrip, trade_date): buy/sell-side HHI, top1/top3 broker shares, dominance/control flags.',
    )
}}

with flow as (
    select scrip, trade_date, broker, buy_qty, sell_qty
    from {{ ref('broker_flow_daily') }}
),

totals as (
    select
        scrip, trade_date,
        sum(buy_qty)  as tot_buy,
        sum(sell_qty) as tot_sell,
        count(distinct broker) as n_brokers
    from flow
    group by scrip, trade_date
),

shares as (
    select
        f.scrip, f.trade_date, f.broker,
        case when t.tot_buy  > 0 then f.buy_qty  / t.tot_buy  else 0 end as buy_share,
        case when t.tot_sell > 0 then f.sell_qty / t.tot_sell else 0 end as sell_share
    from flow f
    join totals t using (scrip, trade_date)
),

ranked as (
    select
        scrip, trade_date, broker, buy_share, sell_share,
        row_number() over (partition by scrip, trade_date order by buy_share  desc) as buy_rank,
        row_number() over (partition by scrip, trade_date order by sell_share desc) as sell_rank
    from shares
),

agg as (
    select
        s.scrip,
        s.trade_date,
        sum(s.buy_share  * s.buy_share)  as hhi_buy,
        sum(s.sell_share * s.sell_share) as hhi_sell,
        max(s.buy_share)                 as top1_buy_share,
        max(s.sell_share)                as top1_sell_share,
        sum(case when r.buy_rank  <= 3 then s.buy_share  else 0 end) as top3_buy_share,
        sum(case when r.sell_rank <= 3 then s.sell_share else 0 end) as top3_sell_share
    from shares s
    join ranked r using (scrip, trade_date, broker)
    group by s.scrip, s.trade_date
)

select
    a.scrip,
    a.trade_date,
    t.n_brokers,
    t.tot_buy  as total_buy_qty,
    t.tot_sell as total_sell_qty,
    a.hhi_buy,
    a.hhi_sell,
    (a.hhi_buy + a.hhi_sell) / 2.0          as hhi_combined,
    a.top1_buy_share,
    a.top1_sell_share,
    a.top3_buy_share,
    a.top3_sell_share,
    (a.top1_buy_share  > 0.30) as buy_dominance_flag,
    (a.top1_sell_share > 0.30) as sell_dominance_flag,
    (a.top3_buy_share  > 0.60) as buy_control_flag,
    (a.top3_sell_share > 0.60) as sell_control_flag,
    (a.top1_buy_share > 0.30 or a.top1_sell_share > 0.30
        or a.top3_buy_share > 0.60 or a.top3_sell_share > 0.60) as concentration_flag,
    current_timestamp as computed_at
from agg a
join totals t using (scrip, trade_date)
