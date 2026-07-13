{# -
    gold.stage1_screen_results — sector-relative composite z-score.

    Three components, averaged into composite_score:
      * profitability_score     = z-score of ROE within sector/quarter
      * revenue_growth_score    = z-score of YoY growth of NII
                                  (placeholder 0.0 until multi-year
                                   fundamentals are backfilled)
      * return_ratio_score      = z-score of ROA within sector/quarter

    `passed` flags scrips in the top (1 - pass_threshold) of composite_score
    per sector/quarter. pass_threshold is a var exposed through
    dbt_project.yml (default 0.5 = top half).

    `rank` = sector-relative composite rank, 1 = best-in-sector.
- #}
{{
    config(
        location=gold_external_location(),
        description='Sector-relative Stage-1 screen (z-score composite).',
    )
}}

{%- set pass_threshold = var('stage1_pass_threshold', 0.5) -%}

with

-- Join fundamentals to sector master; drop rows missing core inputs.
snap as (
    select
        fs.scrip, sm.sector, fs.fiscal_year_bs, fs.quarter,
        fs.roe, fs.roa, fs.net_interest_income
    from {{ source('silver', 'fundamentals_snapshots') }} fs
    join {{ source('silver', 'scrip_master') }}           sm using (scrip)
    where sm.is_active
      and fs.roe is not null
      and fs.roa is not null
),

-- Sector-relative z-scores. NULLIF on the stddev guards against
-- single-scrip sectors where stddev = 0 (divide-by-zero).
zs as (
    select
        *,
        (roe - avg(roe) over sector_window)
            / nullif(stddev_samp(roe) over sector_window, 0) as profitability_score,
        cast(0.0 as double)                                   as revenue_growth_score,
        (roa - avg(roa) over sector_window)
            / nullif(stddev_samp(roa) over sector_window, 0) as return_ratio_score
    from snap
    window sector_window as (partition by sector, fiscal_year_bs, quarter)
),

with_composite as (
    select
        *,
        (coalesce(profitability_score, 0) + revenue_growth_score + coalesce(return_ratio_score, 0)) / 3.0
            as composite_score
    from zs
)

select
    scrip,
    sector,
    fiscal_year_bs,
    quarter,
    coalesce(profitability_score, 0.0) as profitability_score,
    revenue_growth_score,
    coalesce(return_ratio_score, 0.0)  as return_ratio_score,
    composite_score,
    percent_rank() over (partition by sector, fiscal_year_bs, quarter order by composite_score) >= {{ pass_threshold }}
        as passed,
    cast(
        row_number() over (partition by sector, fiscal_year_bs, quarter order by composite_score desc)
        as integer
    )                                   as rank,
    current_timestamp                   as computed_at
from with_composite
order by sector, fiscal_year_bs, quarter, rank
