{# -
    gold.dividend_yield — annual dividend return vs market price.

    Research Q4 explicitly asks "Dividend yield vs fixed deposit rates".
    NEPSE face value is NPR 100, so:
        cash dividend per share = cash_dividend_pct × 100
        cash yield              = cash div per share / market price
        total yield             = (cash + bonus) × 100 / market price

    Treat bonus shares as part of total yield because they're a form of
    stock-based return — a 10% bonus issues 10 new shares per 100 held,
    increasing the shareholder's holding at market price.

    One row per (scrip, fiscal_year_bs) — yields are annual by
    construction. The cash_dividend_pct and bonus_pct columns in
    silver.additional_info are declared at quarter granularity but
    typically only reported in one quarter (usually Q4 at year-end);
    summing across the year handles both forms.
- #}
{{
    config(
        location=gold_external_location(),
        description='Annual cash + bonus dividend yield vs year-end market price.',
    )
}}

{%- set face_value = 100 -%}

with annual_div as (
    -- Annual totals — sum all four quarters so we catch dividends
    -- declared at any point in the year, not just Q4.
    select
        scrip,
        fiscal_year_bs,
        sum(cash_dividend_pct) as annual_cash_div_pct,
        sum(bonus_pct)         as annual_bonus_pct
    from {{ source('silver', 'additional_info') }}
    group by scrip, fiscal_year_bs
),

-- End-of-year market price: the latest quarter's MVPS within that fy.
-- If MVPS is missing in Q4 (incomplete recent data), falls back to the
-- most recent non-null quarter.
fy_end_price as (
    select scrip, fiscal_year_bs, market_value_per_share
    from {{ source('silver', 'additional_info') }}
    where market_value_per_share is not null
    qualify row_number() over (partition by scrip, fiscal_year_bs order by quarter desc) = 1
)

select
    ad.scrip,
    ad.fiscal_year_bs,
    ad.annual_cash_div_pct,
    ad.annual_bonus_pct,
    fy.market_value_per_share,
    -- cash yield = (cash_div_pct × face) / market_price
    (ad.annual_cash_div_pct * {{ face_value }}) * 1.0 / nullif(fy.market_value_per_share, 0)
                                                                   as cash_dividend_yield,
    -- Total yield — includes stock-form return.
    ((ad.annual_cash_div_pct + ad.annual_bonus_pct) * {{ face_value }}) * 1.0
        / nullif(fy.market_value_per_share, 0)                      as total_dividend_yield,
    -- Payout tier for dashboards. Reference anchors:
    --   NEPSE 1-year fixed deposit typical rate: ~8%
    --   Dividend yield > FD rate = "income" name.
    case
        when fy.market_value_per_share is null           then null
        when ad.annual_cash_div_pct * {{ face_value }}
             * 1.0 / nullif(fy.market_value_per_share, 0) >= 0.08   then 'ABOVE_FD_RATE'
        when ad.annual_cash_div_pct * {{ face_value }}
             * 1.0 / nullif(fy.market_value_per_share, 0) >= 0.04   then 'MODERATE'
        else                                                             'LOW'
    end                                                             as yield_tier,
    current_timestamp                                               as computed_at
from annual_div ad
left join fy_end_price fy using (scrip, fiscal_year_bs)
where ad.annual_cash_div_pct is not null or ad.annual_bonus_pct is not null
order by ad.scrip, ad.fiscal_year_bs
