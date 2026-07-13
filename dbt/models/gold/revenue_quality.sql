{# -
    gold.revenue_quality — income-mix analysis + earnings stability.

    A bank earning 85% of its revenue from core net interest income is a
    very different business from one with 40% trading income. The mix
    directly affects quality of earnings:
      * NII is sticky — recurring, tied to the loan book.
      * Fee income is moderately sticky — depends on transaction volumes.
      * Trading income is volatile — one bad quarter can wipe a year.
      * Other operating income usually contains one-offs.

    Also computes earnings-stability via the coefficient of variation of
    net profit over the trailing 8 quarters. CV < 0.2 is very stable,
    0.2–0.4 is moderate, > 0.4 is volatile.

    Feeds research Q3 "Segment-wise income sustainability" and provides
    the "revenue_quality" contribution to fundamental_quality_composite.
- #}
{{
    config(
        location=gold_external_location(),
        description='Income composition + earnings stability (CV of net profit).',
    )
}}

with base as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        net_interest_income,
        net_fees_income,
        net_trading_income,
        other_operating_income,
        total_operating_income,
        net_profit
    from {{ source('silver', 'fundamentals_snapshots') }}
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    -- Income composition (should sum to ~1.0; small gap if impairment
    -- recoveries or sign-flipped segment-level items).
    net_interest_income    * 1.0 / nullif(total_operating_income, 0) as nii_share,
    net_fees_income        * 1.0 / nullif(total_operating_income, 0) as fees_share,
    net_trading_income     * 1.0 / nullif(total_operating_income, 0) as trading_share,
    other_operating_income * 1.0 / nullif(total_operating_income, 0) as other_income_share,
    -- Diversification score (Herfindahl-complement): higher = more
    -- diversified. 1.0 = perfectly equal split; 0.0 = one segment.
    1.0 - (
        pow(coalesce(net_interest_income,    0) * 1.0 / nullif(total_operating_income, 0), 2)
      + pow(coalesce(net_fees_income,        0) * 1.0 / nullif(total_operating_income, 0), 2)
      + pow(coalesce(net_trading_income,     0) * 1.0 / nullif(total_operating_income, 0), 2)
      + pow(coalesce(other_operating_income, 0) * 1.0 / nullif(total_operating_income, 0), 2)
    )                                                                as revenue_diversification_score,
    -- Earnings stability — coefficient of variation of quarterly net
    -- profit over trailing 8 quarters. NULL until 8 quarters accrued.
    stddev_samp(net_profit) over w8 * 1.0 / nullif(abs(avg(net_profit) over w8), 0)
                                                                      as earnings_cv_8q,
    count(*) over w8                                                  as n_quarters_in_cv_window,
    current_timestamp                                                 as computed_at
from base
window w8 as (
    partition by scrip
    order by fiscal_year_bs, quarter
    rows between 7 preceding and current row
)
order by scrip, fiscal_year_bs, quarter
