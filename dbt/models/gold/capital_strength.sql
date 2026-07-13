{# -
    gold.capital_strength — Tier 1 / Tier 2 / Total CAR over time, with
    headroom vs the NRB 11% regulatory minimum.

    The NRB (Nepal Rastra Bank) minimum CAR for commercial banks is
    11% since FY 2080/81. Banks at or near that floor have limited
    headroom for loan growth and may need to raise capital — which
    dilutes existing shareholders. The car_buffer column makes this
    visible at a glance.

    Tier composition matters too — Tier 1 (equity + retained earnings)
    is higher quality than Tier 2 (subordinated debt). A bank with 15%
    CAR that's 80% Tier 1 is stronger than one with the same 15% CAR
    at 60% Tier 1 / 40% Tier 2.

    Research Q2 ("Market Capitalisation, Float & Supply Risk") and Q8
    ("Regulatory & Policy Risk Assessment") both reference capital
    adequacy; this model is the canonical source for both.
- #}
{{
    config(
        location=gold_external_location(),
        description='CAR / Tier 1 / Tier 2 trends with NRB-minimum headroom bucket.',
    )
}}

{%- set nrb_min_car = 0.11 -%}

with base as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        capital_fund_to_rwa as car,
        tier1_capital,
        tier2_capital,
        total_capital
    from {{ source('silver', 'additional_info') }}
    where capital_fund_to_rwa is not null
),

with_context as (
    select
        *,
        lag(car, 4) over w as car_yoy_prev
    from base
    window w as (partition by scrip order by fiscal_year_bs, quarter)
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    car,
    tier1_capital,
    tier2_capital,
    total_capital,
    -- Composition — what fraction is the higher-quality Tier 1?
    tier1_capital * 1.0 / nullif(total_capital, 0)                  as tier1_share,
    -- Headroom above the {{ nrb_min_car * 100 }}% NRB minimum.
    -- Positive = buffer; negative = below floor (regulatory breach).
    car - {{ nrb_min_car }}                                          as car_buffer,
    -- YoY change — is capital improving or eroding?
    car - car_yoy_prev                                               as car_yoy_change,
    -- Tiered bucket for dashboards. Thresholds reflect industry norms.
    case
        when car >= 0.15                      then 'STRONG'
        when car >= 0.12                      then 'ADEQUATE'
        when car >= {{ nrb_min_car }}         then 'TIGHT'
        when car is null                      then null
        else                                       'BELOW_MIN'
    end                                                              as capital_tier,
    current_timestamp                                                as computed_at
from with_context
order by scrip, fiscal_year_bs, quarter
