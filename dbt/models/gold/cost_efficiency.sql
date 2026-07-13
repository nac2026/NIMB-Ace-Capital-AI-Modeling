{# -
    gold.cost_efficiency — operating cost ratios per (scrip, fy, quarter).

    Cost-to-income ratio (CIR) is the single most-cited bank efficiency
    metric in Nepal and globally. Good banks are in the 40–50% range;
    banks above 65% are generally considered expensive to run.

    Breaks CIR into its parts so analysts can see WHERE costs are —
    staff, general opex, or depreciation — rather than just that they're
    elevated.

    Research Q3 "Cost structure and operating leverage" maps directly
    here. Feeds into fundamental_quality_composite as the efficiency
    component, and into piotroski_f_score's signal #9 (CIR improved YoY).
- #}
{{
    config(
        location=gold_external_location(),
        description='Cost-to-income ratio + its component breakdown.',
    )
}}

with base as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        total_operating_income,
        total_assets,
        staff_expenses,
        other_operating_expenses,
        depreciation_amortization,
        operating_profit,
        -- Composite opex — depreciation included because it's a real
        -- ongoing cost despite being non-cash.
        coalesce(staff_expenses, 0)
          + coalesce(other_operating_expenses, 0)
          + coalesce(depreciation_amortization, 0)  as total_opex
    from {{ source('silver', 'fundamentals_snapshots') }}
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    -- Primary ratio.
    total_opex * 1.0 / nullif(total_operating_income, 0)             as cost_to_income_ratio,
    -- Component contributions (sum to ~1.0 if you add them).
    staff_expenses * 1.0 / nullif(total_operating_income, 0)         as staff_cost_ratio,
    other_operating_expenses * 1.0 / nullif(total_operating_income, 0) as other_opex_ratio,
    depreciation_amortization * 1.0 / nullif(total_operating_income, 0) as depreciation_ratio,
    -- Revenue productivity — operating income per unit of asset.
    -- Higher = more efficient use of the balance sheet to generate revenue.
    total_operating_income * 1.0 / nullif(total_assets, 0)           as revenue_per_asset,
    -- Pre-provision operating margin — operating profit as % of revenue,
    -- a cleaner margin view than post-impairment net margin.
    operating_profit * 1.0 / nullif(total_operating_income, 0)       as operating_margin,
    -- Opex per rupee of operating income — duplicates CIR but stated
    -- the opposite way so it's easy to sort descending for "who spends
    -- the most per rupee earned".
    total_opex,
    total_operating_income,
    current_timestamp                                                 as computed_at
from base
order by scrip, fiscal_year_bs, quarter
