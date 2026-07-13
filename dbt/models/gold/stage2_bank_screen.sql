{# -
    gold.stage2_bank_screen — sector-aware deep screen (ALL sectors).

    Despite the legacy "bank" name (kept to avoid churning the serving
    table / API route / agent tool), this screen now covers every active
    sector. Each scrip is scored on percentiles computed WITHIN its own
    sector per (fiscal_year, quarter), so a hydropower company is ranked
    against hydropower peers, a bank against banks, etc.

    Two screen families, by what metrics the sector actually reports:

    * BFI family — Commercial Bank, Development Bank, Finance, Microfinance.
      Deposit-takers that report the regulatory ratios. Composite = mean of
      four percentiles:
        ROE        (higher better)
        NPL ratio  (lower better — percentile flipped)
        CAR        (higher better)
        CD ratio   (lower better — percentile flipped)
      Flags (absolute, decimal scale — ratios are decimals e.g. 0.0425 = 4.25%):
        NPL_HIGH npl>0.05, CAR_LOW car<0.11, CD_HIGH cd>0.85, ROE_LOW roe<0.10.

    * General family — everyone else (hydro, manufacturing, hotels,
      investment, life & non-life insurance, …). No NPL/CAR/CD exist, so the
      composite = mean of three profitability percentiles:
        ROE, ROA, net margin (net_profit / total_revenue).
      Flags: LOSS (net_profit<0), ROE_LOW (roe<0.10), THIN_MARGIN (margin<0.05).

    composite_score is in [0,1]; higher = healthier within its sector. The
    BFI-only percentile columns (npl/car/cd) are NULL for general-family rows.
- #}
{{
    config(
        location=gold_external_location(),
        description='Sector-aware deep screen — sector-relative percentiles + family-specific flags (all sectors).',
    )
}}

with

base as (
    select
        fs.scrip,
        sm.sector,
        fs.fiscal_year_bs,
        fs.quarter,
        fs.roe,
        fs.roa,
        fs.npl_ratio,
        fs.car,
        fs.cd_ratio,
        fs.net_profit,
        fs.total_revenue,
        case
            when fs.total_revenue is not null and fs.total_revenue <> 0
            then fs.net_profit / fs.total_revenue
        end                                          as net_margin,
        case
            when sm.sector in (
                'Commercial Bank', 'Development Bank', 'Finance', 'Microfinance'
            ) then 'bfi' else 'general'
        end                                          as family
    from {{ source('silver', 'fundamentals_snapshots') }} fs
    join {{ source('silver', 'scrip_master') }}           sm using (scrip)
    where sm.is_active
),

-- PERCENT_RANK returns [0, 1] within each sector / fiscal-year / quarter
-- cohort. For lower-is-better ratios we flip via (1 - rank).
pct as (
    select
        *,
        percent_rank() over w_roe          as roe_percentile,
        percent_rank() over w_roa          as roa_percentile,
        percent_rank() over w_nm           as net_margin_percentile,
        1.0 - percent_rank() over w_npl    as npl_percentile,
        percent_rank() over w_car          as car_percentile,
        1.0 - percent_rank() over w_cd     as cd_percentile
    from base
    window
        w_roe as (partition by sector, fiscal_year_bs, quarter order by roe),
        w_roa as (partition by sector, fiscal_year_bs, quarter order by roa),
        w_nm  as (partition by sector, fiscal_year_bs, quarter order by net_margin),
        w_npl as (partition by sector, fiscal_year_bs, quarter order by npl_ratio),
        w_car as (partition by sector, fiscal_year_bs, quarter order by car),
        w_cd  as (partition by sector, fiscal_year_bs, quarter order by cd_ratio)
)

select
    scrip,
    sector,
    fiscal_year_bs,
    quarter,
    roe,           roe_percentile,
    roa,           roa_percentile,
    net_margin,    net_margin_percentile,
    npl_ratio,
    case when family = 'bfi' then npl_percentile end as npl_percentile,
    car,
    case when family = 'bfi' then car_percentile end as car_percentile,
    cd_ratio,
    case when family = 'bfi' then cd_percentile end  as cd_percentile,
    -- Mean of the family's relevant percentiles, ignoring any that are NULL
    -- (e.g. a general-family scrip missing net margin) so a data gap doesn't
    -- unfairly drag the composite toward 0. BFIs always have all four, so this
    -- is identical to a plain /4 average for them.
    coalesce(
        case
            when family = 'bfi' then list_avg([
                x for x in [roe_percentile, npl_percentile, car_percentile, cd_percentile]
                if x is not null
            ])
            else list_avg([
                x for x in [roe_percentile, roa_percentile, net_margin_percentile]
                if x is not null
            ])
        end,
        0
    )                                                as composite_score,
    [x for x in [
        case when family = 'bfi' and npl_ratio  > 0.05 then 'NPL_HIGH'    end,
        case when family = 'bfi' and car        < 0.11 then 'CAR_LOW'     end,
        case when family = 'bfi' and cd_ratio   > 0.85 then 'CD_HIGH'     end,
        case when roe < 0.10                            then 'ROE_LOW'     end,
        case when family = 'general' and net_profit < 0 then 'LOSS'        end,
        case when family = 'general' and net_margin < 0.05 then 'THIN_MARGIN' end
    ] if x is not null]                              as flags,
    current_timestamp                                as computed_at
from pct
order by sector, fiscal_year_bs, quarter, composite_score desc
