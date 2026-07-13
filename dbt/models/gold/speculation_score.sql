{# -
    gold.speculation_score — per-scrip composite (0..100) of how
    manipulation-prone / operator-driven the trading looks, from
    floor-sheet microstructure alone.

    Five normalized (0..1) components, weighted:
      concentration (0.30) — avg daily top-broker dominance (one hand on a side)
      control       (0.15) — share of days flagged concentrated
      circular      (0.25) — strongest reciprocal/wash broker-pair score
      accumulation  (0.20) — largest single-broker share of the scrip's volume
      block         (0.10) — share of volume in oversized (block) trades

    score = 100 × Σ(weight × component); tier banded for quick triage. This
    is a *flag for review*, not a verdict — it tells the desk where operator
    behaviour is concentrated. Feeds the speculative-analysis engine and the
    research page's floor-sheet tab.
- #}
{{
    config(
        location=gold_external_location(),
        description='Per-scrip 0-100 speculation/manipulation score with component breakdown + tier.',
    )
}}

with conc as (
    select
        scrip,
        avg(greatest(top1_buy_share, top1_sell_share)) as avg_top1,
        avg(case when concentration_flag then 1.0 else 0.0 end) as control_frac,
        count(*) as n_days
    from {{ ref('broker_concentration_daily') }}
    group by scrip
),

circ as (
    select
        scrip,
        max(circular_score) as max_circular,
        max(case when self_trade and pair_qty > 0 then 1 else 0 end) as has_self_trade
    from {{ ref('broker_pair_graph') }}
    group by scrip
),

accum as (
    select scrip, max(volume_share) as max_broker_share
    from {{ ref('broker_accumulation') }}
    group by scrip
),

-- Block trades: single trades that are ≥ 2% of the scrip's total volume.
scrip_qty as (
    select scrip, sum(quantity) as scrip_qty
    from {{ source('silver', 'floorsheet') }}
    group by scrip
),
block as (
    select
        f.scrip,
        sum(case when f.quantity >= 0.02 * s.scrip_qty then f.quantity else 0 end)
            / nullif(s.scrip_qty, 0) as block_share
    from {{ source('silver', 'floorsheet') }} f
    join scrip_qty s using (scrip)
    group by f.scrip, s.scrip_qty
)

select
    c.scrip,
    c.n_days,
    coalesce(c.avg_top1, 0)              as c_concentration,
    coalesce(c.control_frac, 0)          as c_control,
    coalesce(ci.max_circular, 0)         as c_circular,
    coalesce(a.max_broker_share, 0)      as c_accumulation,
    coalesce(b.block_share, 0)           as c_block,
    coalesce(ci.has_self_trade, 0)       as has_self_trade,
    round(100 * (
        0.30 * coalesce(c.avg_top1, 0)
      + 0.15 * coalesce(c.control_frac, 0)
      + 0.25 * coalesce(ci.max_circular, 0)
      + 0.20 * coalesce(a.max_broker_share, 0)
      + 0.10 * coalesce(b.block_share, 0)
    ), 1) as speculation_score,
    case
        when 100 * (0.30*coalesce(c.avg_top1,0) + 0.15*coalesce(c.control_frac,0)
                  + 0.25*coalesce(ci.max_circular,0) + 0.20*coalesce(a.max_broker_share,0)
                  + 0.10*coalesce(b.block_share,0)) >= 70 then 'HIGH'
        when 100 * (0.30*coalesce(c.avg_top1,0) + 0.15*coalesce(c.control_frac,0)
                  + 0.25*coalesce(ci.max_circular,0) + 0.20*coalesce(a.max_broker_share,0)
                  + 0.10*coalesce(b.block_share,0)) >= 45 then 'ELEVATED'
        when 100 * (0.30*coalesce(c.avg_top1,0) + 0.15*coalesce(c.control_frac,0)
                  + 0.25*coalesce(ci.max_circular,0) + 0.20*coalesce(a.max_broker_share,0)
                  + 0.10*coalesce(b.block_share,0)) >= 25 then 'MODERATE'
        else 'LOW'
    end as speculation_tier,
    current_timestamp as computed_at
from conc c
left join circ  ci using (scrip)
left join accum a  using (scrip)
left join block b  using (scrip)
