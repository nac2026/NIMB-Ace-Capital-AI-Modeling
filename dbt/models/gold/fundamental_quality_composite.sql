{# -
    gold.fundamental_quality_composite — the 0-100 quality score the
    SOW M3 explicitly asks for, with QoQ trend preserved (one row per
    scrip/quarter, so you can chart the trajectory).

    Six components, blended:
      Profitability (25%)   percentile rank on ROE within sector
      Asset quality (20%)   1 – percentile on NPL (lower = better)
      Growth        (20%)   percentile on net-profit YoY growth
      Capital       (15%)   percentile on CAR
      Efficiency    (10%)   1 – percentile on cost-to-income (lower = better)
      Piotroski     (10%)   f_score / 9

    Percentile ranks are computed within the scrip's SECTOR for the
    same (fiscal_year_bs, quarter) cohort so the score is peer-relative.
    Scrips with missing inputs for a component default to 0.5 (median)
    so they don't silently score 0 on a data gap.

    Composite is rescaled to 0..100. Score tier bucket:
      >=70 → TOP-DECILE    (flag for analyst deep-dive)
      50-70 → STRONG
      30-50 → AVERAGE
      <30  → WEAK

    Depends on three upstream Gold models — dbt resolves the DAG
    automatically so composite runs after its inputs.
- #}
{{
    config(
        location=gold_external_location(),
        description='Weighted 0–100 fundamental quality composite (6 components, peer-relative).',
    )
}}

with inputs as (
    select
        fs.scrip,
        sm.sector,
        fs.fiscal_year_bs,
        fs.quarter,
        fs.roe,
        fs.roa,
        fs.npl_ratio,
        fs.car,
        qg.net_profit_yoy_pct,
        ce.cost_to_income_ratio,
        pi.f_score,
        pi.n_signals_available
    from {{ source('silver', 'fundamentals_snapshots') }} fs
    join {{ source('silver', 'scrip_master') }}           sm using (scrip)
    left join {{ ref('quarterly_growth') }}   qg using (scrip, fiscal_year_bs, quarter)
    left join {{ ref('cost_efficiency') }}    ce using (scrip, fiscal_year_bs, quarter)
    left join {{ ref('piotroski_f_score') }}  pi using (scrip, fiscal_year_bs, quarter)
    where sm.is_active
),

-- Percentile rank within (sector, fy, quarter) cohort. PERCENT_RANK
-- returns [0, 1]; for lower-is-better metrics we flip via (1 - rank).
ranked as (
    select
        *,
        percent_rank() over (partition by sector, fiscal_year_bs, quarter order by roe)                  as p_profitability,
        1 - percent_rank() over (partition by sector, fiscal_year_bs, quarter order by npl_ratio)         as p_asset_quality,
        percent_rank() over (partition by sector, fiscal_year_bs, quarter order by net_profit_yoy_pct)   as p_growth,
        percent_rank() over (partition by sector, fiscal_year_bs, quarter order by car)                  as p_capital,
        1 - percent_rank() over (partition by sector, fiscal_year_bs, quarter order by cost_to_income_ratio) as p_efficiency,
        f_score * 1.0 / 9.0                                                                                as p_piotroski
    from inputs
)

select
    scrip,
    sector,
    fiscal_year_bs,
    quarter,
    -- Emit each normalized component so analysts can see WHICH driver
    -- made the total go up or down without re-deriving them.
    coalesce(p_profitability, 0.5)  as profitability_pct,
    coalesce(p_asset_quality, 0.5)  as asset_quality_pct,
    coalesce(p_growth,        0.5)  as growth_pct,
    coalesce(p_capital,       0.5)  as capital_pct,
    coalesce(p_efficiency,    0.5)  as efficiency_pct,
    coalesce(p_piotroski,     0.5)  as piotroski_pct,
    -- Weighted composite, rescaled to 0..100.
    cast(round(100.0 * (
        0.25 * coalesce(p_profitability, 0.5)
      + 0.20 * coalesce(p_asset_quality, 0.5)
      + 0.20 * coalesce(p_growth,        0.5)
      + 0.15 * coalesce(p_capital,       0.5)
      + 0.10 * coalesce(p_efficiency,    0.5)
      + 0.10 * coalesce(p_piotroski,     0.5)
    ), 2) as double)                as quality_score_0_100,
    -- Bucketed tier.
    case
        when 100.0 * (
            0.25 * coalesce(p_profitability, 0.5)
          + 0.20 * coalesce(p_asset_quality, 0.5)
          + 0.20 * coalesce(p_growth,        0.5)
          + 0.15 * coalesce(p_capital,       0.5)
          + 0.10 * coalesce(p_efficiency,    0.5)
          + 0.10 * coalesce(p_piotroski,     0.5)
        ) >= 70                              then 'TOP_DECILE'
        when 100.0 * (
            0.25 * coalesce(p_profitability, 0.5)
          + 0.20 * coalesce(p_asset_quality, 0.5)
          + 0.20 * coalesce(p_growth,        0.5)
          + 0.15 * coalesce(p_capital,       0.5)
          + 0.10 * coalesce(p_efficiency,    0.5)
          + 0.10 * coalesce(p_piotroski,     0.5)
        ) >= 50                              then 'STRONG'
        when 100.0 * (
            0.25 * coalesce(p_profitability, 0.5)
          + 0.20 * coalesce(p_asset_quality, 0.5)
          + 0.20 * coalesce(p_growth,        0.5)
          + 0.15 * coalesce(p_capital,       0.5)
          + 0.10 * coalesce(p_efficiency,    0.5)
          + 0.10 * coalesce(p_piotroski,     0.5)
        ) >= 30                              then 'AVERAGE'
        else                                      'WEAK'
    end                              as quality_tier,
    current_timestamp                as computed_at
from ranked
order by sector, fiscal_year_bs, quarter, quality_score_0_100 desc
