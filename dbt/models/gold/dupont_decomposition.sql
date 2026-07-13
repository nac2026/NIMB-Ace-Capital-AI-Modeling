{# -
    gold.dupont_decomposition — decomposes ROE into its drivers so
    analysts can answer "why did ROE change?" rather than just "did it?"

    Three nested decompositions for banks:

      1. Two-step (Return on Equity breakdown):
            ROE = ROA × Financial Leverage
                = (Net Profit / Total Assets) × (Total Assets / Equity)

      2. Three-step (Profitability × Efficiency × Leverage):
            ROE = Net Profit Margin × Asset Turnover × Financial Leverage
                = (NP / Revenue) × (Revenue / Assets) × (Assets / Equity)
          where "Revenue" for a bank = Total Operating Income.

      3. Five-step (Tax × Burden × Margin × Turnover × Leverage):
            ROE = Tax Burden × Interest Burden × Operating Margin
                  × Asset Turnover × Financial Leverage
          This is the bank-specific form that separates operating
          performance from tax and financing effects.

    Research Q3 asks "Cost structure and operating leverage"; this model
    provides the operating-profit ladder that answer is built on.
- #}
{{
    config(
        location=gold_external_location(),
        description='ROE decomposition — 2/3/5-step DuPont for banks.',
    )
}}

with base as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        net_profit,
        profit_before_tax,
        operating_profit,
        total_operating_income,
        net_interest_income,
        total_assets,
        shareholders_equity
    from {{ source('silver', 'fundamentals_snapshots') }}
)

select
    scrip,
    fiscal_year_bs,
    quarter,

    -- ROE computed from the BS + IS so we can verify the decomposition
    -- reconciles (ROE ≈ product of the three factors, ignoring lag
    -- between flow and stock).
    net_profit * 1.0 / nullif(shareholders_equity, 0)              as roe_computed,

    -- ============ TWO-STEP ============
    net_profit * 1.0 / nullif(total_assets, 0)                     as roa,
    total_assets * 1.0 / nullif(shareholders_equity, 0)            as equity_multiplier,   -- financial leverage

    -- ============ THREE-STEP ============
    -- Banks use Total Operating Income as "revenue" — it's the top line
    -- after interest expense + fees netting. Using gross interest income
    -- would double-count the cost of funds.
    net_profit * 1.0 / nullif(total_operating_income, 0)           as net_profit_margin,
    total_operating_income * 1.0 / nullif(total_assets, 0)         as asset_turnover,      -- asset utilization

    -- ============ FIVE-STEP (bank-specific) ============
    -- Tax Burden = how much of pretax profit survives taxes (0..1).
    net_profit * 1.0 / nullif(profit_before_tax, 0)                as tax_burden,
    -- Interest Burden = how much of operating profit survives interest
    -- + non-operating items. PBT / Operating Profit < 1 means
    -- non-operating expenses are dragging pretax down.
    profit_before_tax * 1.0 / nullif(operating_profit, 0)          as interest_burden,
    -- Operating Margin = operating profit as % of revenue.
    operating_profit * 1.0 / nullif(total_operating_income, 0)     as operating_margin,
    -- Asset Turnover, Leverage — reused from above.

    -- Net Interest Margin — the bank-defining ratio.
    net_interest_income * 1.0 / nullif(total_assets, 0)            as nim,

    current_timestamp                                               as computed_at
from base
order by scrip, fiscal_year_bs, quarter
