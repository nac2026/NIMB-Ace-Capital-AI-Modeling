{# -
    gold.operating_leverage — how much operating profit moves per unit
    of revenue change. Answers research Q3 "Cost structure and operating
    leverage" and Q10 "Earnings volatility risk".

    Formula:
      OL_raw = (%Δ operating_profit) / (%Δ total_operating_income)

    Banks with high fixed-cost bases (heavy branch networks, big IT
    spend) show high operating leverage — they amplify both upside and
    downside. Low-leverage banks (lean ops) have more stable earnings.

    A single-quarter OL is noisy because either numerator can be near
    zero. We publish:
      * op_leverage_raw        — single-quarter elasticity (can be huge)
      * op_leverage_4q_avg     — smoothed 4-quarter average (usable)
      * op_leverage_tier       — HIGH / MODERATE / LOW bucket based on
                                 4-quarter average of |OL|

    Scrips that are loss-making or just turning the corner will have
    unstable OL — flagged with low `n_valid_quarters` so downstream
    consumers can filter.
- #}
{{
    config(
        location=gold_external_location(),
        description='Operating leverage — revenue elasticity of operating profit. 4-quarter smoothed.',
    )
}}

with growth as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        operating_profit_yoy_pct,
        total_operating_income_yoy_pct
    from {{ ref('quarterly_growth') }}
),

-- Single-quarter raw OL. Cap at ±10 so a small-denominator blowup
-- doesn't pollute the smoothed average.
raw as (
    select
        *,
        case
            when abs(total_operating_income_yoy_pct) < 0.005 then null  -- denom too small
            else least(
                greatest(
                    operating_profit_yoy_pct / nullif(total_operating_income_yoy_pct, 0),
                    -10.0
                ),
                10.0
            )
        end as op_leverage_raw
    from growth
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    op_leverage_raw,
    -- Smoothed 4-quarter average — only emit when at least 2 of the 4
    -- quarters had valid OL values.
    avg(op_leverage_raw) over w4 as op_leverage_4q_avg,
    count(op_leverage_raw) over w4 as n_valid_quarters,
    case
        when count(op_leverage_raw) over w4 < 2                                 then null
        when abs(avg(op_leverage_raw) over w4) >= 2.5                           then 'HIGH'
        when abs(avg(op_leverage_raw) over w4) >= 1.5                           then 'MODERATE'
        else                                                                         'LOW'
    end                             as op_leverage_tier,
    current_timestamp               as computed_at
from raw
window w4 as (
    partition by scrip order by fiscal_year_bs, quarter rows between 3 preceding and current row
)
order by scrip, fiscal_year_bs, quarter
