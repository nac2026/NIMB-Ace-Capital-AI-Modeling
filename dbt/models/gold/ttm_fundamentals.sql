{# -
    gold.ttm_fundamentals — trailing-12-month aggregates per (scrip, fy, quarter).

    For FLOW metrics (income, expense, profit — things measured over a
    period) we SUM the current quarter plus the 3 prior quarters — the
    classic TTM window. For STOCK metrics (balance-sheet balances) we
    keep the current-quarter value since they're point-in-time.

    Rows are gated on n_quarters = 4 so we only emit complete TTM
    periods — a scrip's first 3 quarters of history get no TTM row,
    which is preferable to returning a partial sum that looks fine but
    under-counts.

    Research Q3 ("Revenue and profit growth trend YoY, TTM") is fed from
    here; quarterly_growth uses TTM values to compute rolling growth
    rates that smooth out seasonality.
- #}
{{
    config(
        location=gold_external_location(),
        description='Trailing-12-month sums for flow metrics + point-in-time balance-sheet stocks.',
    )
}}

with

-- Canonical per-quarter flows + stocks. Sequence number drives the
-- 4-row trailing window below — using fiscal_year_bs + quarter directly
-- as the order key would be correct but an integer seq is faster and
-- immune to gaps in data.
ordered as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        -- flow metrics (TTM these)
        net_profit,
        operating_profit,
        profit_before_tax,
        interest_income,
        interest_expense,
        net_interest_income,
        fees_income,
        fees_expense,
        net_fees_income,
        net_trading_income,
        other_operating_income,
        total_operating_income,
        net_operating_income,
        impairment_charge,
        staff_expenses,
        other_operating_expenses,
        depreciation_amortization,
        income_tax,
        -- stock metrics (pass through — point-in-time)
        total_assets,
        total_loans,
        loans_to_customers,
        total_deposits,
        shareholders_equity,
        paid_up_capital,
        retained_earnings,
        row_number() over (partition by scrip order by fiscal_year_bs, quarter) as seq
    from {{ source('silver', 'fundamentals_snapshots') }}
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    -- FLOWS: sum over (current + 3 prior) quarters
    sum(net_profit)                  over w4 as ttm_net_profit,
    sum(operating_profit)            over w4 as ttm_operating_profit,
    sum(profit_before_tax)           over w4 as ttm_profit_before_tax,
    sum(interest_income)             over w4 as ttm_interest_income,
    sum(interest_expense)            over w4 as ttm_interest_expense,
    sum(net_interest_income)         over w4 as ttm_net_interest_income,
    sum(fees_income)                 over w4 as ttm_fees_income,
    sum(net_fees_income)             over w4 as ttm_net_fees_income,
    sum(net_trading_income)          over w4 as ttm_net_trading_income,
    sum(other_operating_income)      over w4 as ttm_other_operating_income,
    sum(total_operating_income)      over w4 as ttm_total_operating_income,
    sum(net_operating_income)        over w4 as ttm_net_operating_income,
    sum(impairment_charge)           over w4 as ttm_impairment_charge,
    sum(staff_expenses)              over w4 as ttm_staff_expenses,
    sum(other_operating_expenses)    over w4 as ttm_other_opex,
    sum(depreciation_amortization)   over w4 as ttm_depreciation,
    sum(income_tax)                  over w4 as ttm_income_tax,
    -- STOCKS: current value (no aggregation)
    total_assets,
    total_loans,
    loans_to_customers,
    total_deposits,
    shareholders_equity,
    paid_up_capital,
    retained_earnings,
    -- Derived TTM ratios (after stocks so they reference current balance):
    sum(net_profit) over w4       / nullif(total_assets, 0)         as ttm_roa,
    sum(net_profit) over w4       / nullif(shareholders_equity, 0)  as ttm_roe,
    sum(net_interest_income) over w4 / nullif(total_assets, 0)      as ttm_nim,
    -- Window bookkeeping — gate TTM output to complete 4-quarter windows.
    count(*) over w4 as n_quarters_in_window,
    current_timestamp as computed_at
from ordered
window w4 as (
    partition by scrip order by seq rows between 3 preceding and current row
)
-- Drop partial-window rows — first 3 quarters of a scrip's history have
-- TTM sums that under-count.
qualify count(*) over w4 = 4
order by scrip, fiscal_year_bs, quarter
