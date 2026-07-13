{# -
    gold.peer_rankings_quarterly — one row per (sector, fy, quarter, metric,
    scrip) giving that scrip's rank vs its sector peers plus sector median
    and mean.

    Direction handling: for most metrics higher is better (ROE, ROA, EPS)
    — rank 1 = best. For NPL ratio (and any future 'lower is better'
    metric), the direction flips so the best performer still gets
    rank=1 / percentile=1.0. The LOWER_IS_BETTER var lives in
    dbt_project.yml if you need to extend it.
- #}
{{
    config(
        location=gold_external_location(),
        description='Quarterly peer rankings per metric per sector.',
    )
}}

with

-- Silver + scrip master join, filtered to active universe. scrip_master
-- already canonicalized (NICA→NICASIA) so this join is clean.
enriched as (
    select
        fl.scrip,
        sm.sector,
        fl.fiscal_year_bs,
        fl.quarter,
        fl.metric_name,
        fl.value
    from {{ source('silver', 'fundamentals_long') }} fl
    join {{ source('silver', 'scrip_master') }}     sm using (scrip)
    where sm.is_active
),

-- Windowed rank + peer statistics. The two CASE expressions inside
-- ORDER BY give us per-metric direction flipping without branching into
-- separate subqueries. Rank 1 = best-in-sector regardless of direction.
ranked as (
    select
        scrip,
        sector,
        fiscal_year_bs,
        quarter,
        metric_name,
        value,
        row_number() over (
            partition by sector, fiscal_year_bs, quarter, metric_name
            order by
                case when metric_name in ('npl_ratio') then value end asc,
                case when metric_name not in ('npl_ratio') then value end desc
        )                                                                                as rank_in_sector,
        count(*) over  (partition by sector, fiscal_year_bs, quarter, metric_name)       as n_peers,
        median(value) over (partition by sector, fiscal_year_bs, quarter, metric_name)   as sector_median,
        avg(value) over    (partition by sector, fiscal_year_bs, quarter, metric_name)   as sector_mean
    from enriched
)

select
    scrip,
    sector,
    fiscal_year_bs,
    quarter,
    metric_name,
    value,
    rank_in_sector,
    -- percentile = (n - rank + 1) / n → rank 1 maps to 1.0, rank n to 1/n.
    cast((n_peers - rank_in_sector + 1.0) / n_peers as double) as percentile_in_sector,
    sector_median,
    sector_mean,
    current_timestamp as computed_at
from ranked
order by metric_name, fiscal_year_bs, quarter, rank_in_sector
