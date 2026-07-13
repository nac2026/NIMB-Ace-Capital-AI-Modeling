{# -
    gold.sector_momentum — which sectors are attracting vs losing
    capital. Research Q9 ("Sector boom / slowdown cycle") and Q12
    (continuous monitoring).

    Averages the 3m and 6m returns from price_returns across scrips in
    the same sector, then ranks sectors by 6-month return. Emits one
    row per sector.

    Also computes dispersion (stddev of 6m returns within sector) — a
    high dispersion means "pick your stocks carefully, sector-wide
    rotation isn't happening"; low dispersion means the sector is
    moving as a block.
- #}
{{
    config(
        location=gold_external_location(),
        description='Per-sector momentum (avg 3m/6m return) with within-sector return dispersion.',
    )
}}

with returns_with_sector as (
    select
        pr.scrip,
        sm.sector,
        pr.return_3m,
        pr.return_6m,
        pr.return_1y
    from {{ ref('price_returns') }} pr
    join {{ source('silver', 'scrip_master') }} sm using (scrip)
    where sm.is_active
),

sector_agg as (
    select
        sector,
        count(distinct scrip)         as n_scrips,
        avg(return_3m)                as avg_return_3m,
        avg(return_6m)                as avg_return_6m,
        avg(return_1y)                as avg_return_1y,
        median(return_6m)             as median_return_6m,
        stddev_samp(return_6m)        as return_6m_dispersion,
        min(return_6m)                as min_return_6m,
        max(return_6m)                as max_return_6m
    from returns_with_sector
    group by sector
)

select
    sector,
    n_scrips,
    avg_return_3m,
    avg_return_6m,
    avg_return_1y,
    median_return_6m,
    return_6m_dispersion,
    min_return_6m,
    max_return_6m,
    rank() over (order by avg_return_6m desc nulls last) as rank_by_6m,
    -- Hot / cold classification. Thresholds are absolute (not peer-
    -- relative to the sector set) because we only have 1 sector in
    -- the prototype — peer-relative makes no sense with N=1.
    case
        when avg_return_6m is null           then null
        when avg_return_6m >=  0.20          then 'HOT'
        when avg_return_6m >=  0.05          then 'WARM'
        when avg_return_6m >= -0.05          then 'NEUTRAL'
        when avg_return_6m >= -0.20          then 'COOL'
        else                                      'COLD'
    end as momentum_tier,
    current_timestamp                                      as computed_at
from sector_agg
order by avg_return_6m desc nulls last
