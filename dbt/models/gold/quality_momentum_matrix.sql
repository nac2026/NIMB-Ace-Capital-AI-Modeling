{# -
    gold.quality_momentum_matrix — 2x2 quadrant classification, as-of
    the latest quarter + latest price.

    Quadrants:

      Quality (y)
          ^
     HIGH |  CONTRARIAN_BET  |  QUALITY_LEADER
          |  (cheap quality, |  (deserves the
          |   awaiting       |   premium — often
          |   rerating)      |   highest-priced)
     -----+------------------+------------------
      LOW |  AVOID           |  MOMENTUM_TRAP
          |  (weak + losing  |  (weak fundamentals
          |   money — no     |   rallying on
          |   thesis)        |   speculation)
          +------------------+------------------>
             NEGATIVE          POSITIVE      Momentum (x, 6m return)

    Thresholds:
      Quality — sector-relative: above or below the sector median
                quality_score in the latest quarter.
      Momentum — return_6m above or below sector median.

    One row per active scrip. This is the analyst-facing output the
    SOW M3 highlights as "quality-momentum classification".
- #}
{{
    config(
        location=gold_external_location(),
        description='4-quadrant quality × 6-month momentum classification (per scrip, latest snapshot).',
    )
}}

with latest_quality as (
    -- Most recent fundamental_quality_composite row per scrip.
    select *
    from {{ ref('fundamental_quality_composite') }}
    qualify row_number() over (partition by scrip order by fiscal_year_bs desc, quarter desc) = 1
),

joined as (
    select
        lq.scrip,
        lq.sector,
        lq.fiscal_year_bs,
        lq.quarter,
        lq.quality_score_0_100,
        lq.quality_tier,
        pr.return_6m,
        pr.as_of as price_as_of
    from latest_quality     lq
    left join {{ ref('price_returns') }} pr using (scrip)
),

-- Sector-relative thresholds. Absolute thresholds (e.g. "quality_score
-- > 50" and "return_6m > 0") would tag every bank as LOW-quality when
-- the sector is depressed; peer-relative keeps the quadrants balanced.
with_thresholds as (
    select
        *,
        median(quality_score_0_100) over (partition by sector) as sector_quality_median,
        median(return_6m)            over (partition by sector) as sector_return_6m_median
    from joined
)

select
    scrip,
    sector,
    fiscal_year_bs                  as latest_fy,
    quarter                         as latest_quarter,
    quality_score_0_100,
    quality_tier,
    return_6m,
    price_as_of,
    sector_quality_median,
    sector_return_6m_median,
    -- Booleans make the quadrant expression readable.
    quality_score_0_100 >= sector_quality_median as is_high_quality,
    return_6m >= sector_return_6m_median          as is_high_momentum,
    case
        when quality_score_0_100 is null or return_6m is null              then 'UNCLASSIFIED'
        when quality_score_0_100 >= sector_quality_median
         and return_6m            >= sector_return_6m_median                then 'QUALITY_LEADER'
        when quality_score_0_100 >= sector_quality_median
         and return_6m            <  sector_return_6m_median                then 'CONTRARIAN_BET'
        when quality_score_0_100 <  sector_quality_median
         and return_6m            >= sector_return_6m_median                then 'MOMENTUM_TRAP'
        else                                                                     'AVOID'
    end                              as quadrant,
    current_timestamp                as computed_at
from with_thresholds
order by sector, quality_score_0_100 desc
