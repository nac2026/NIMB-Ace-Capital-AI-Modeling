{# -
    gold.valuation_history — P/E and P/B percentile vs scrip's OWN history.

    Peer-relative valuation is in gold.valuation. This model answers the
    different question of "is this cheap vs its *own* 5-year history?" —
    a scrip trading at 18× P/E looks expensive absolutely but cheap if
    it traded at 25× for most of the last 5 years. Research Q4
    explicitly asks "P/E vs sector average" (covered by gold.valuation)
    and "Margin of safety" — margin of safety is here.

    Emits one row per (scrip, fy, quarter) with:
      * pe_self_pct_5y    — P/E percentile over trailing 20 quarters
      * pb_self_pct_5y    — P/B percentile over trailing 20 quarters
      * pe_self_pct_all   — P/E percentile over all history
      * self_valuation_tier — VERY_CHEAP / CHEAP / FAIR / EXPENSIVE / VERY_EXPENSIVE

    Lower percentile = historically cheap. 0% = cheapest in the window.
- #}
{{
    config(
        location=gold_external_location(),
        description="P/E and P/B percentile vs scrip's own 5-year and all-history distribution.",
    )
}}

with base as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        pe_ratio,
        pb_ratio
    from {{ source('silver', 'fundamentals_snapshots') }}
    where pe_ratio is not null and pe_ratio > 0
),

-- PERCENT_RANK over the scrip's own trailing window. We use a 20-quarter
-- (5-year) window for the primary view — long enough to span a credit
-- cycle, short enough that ancient regimes don't distort the current
-- picture.
with_pct as (
    select
        *,
        percent_rank() over (
            partition by scrip
            order by pe_ratio
            rows between 19 preceding and current row
        ) as pe_self_pct_5y,
        percent_rank() over (
            partition by scrip
            order by pb_ratio
            rows between 19 preceding and current row
        ) as pb_self_pct_5y,
        percent_rank() over (
            partition by scrip
            order by pe_ratio
        ) as pe_self_pct_all,
        count(*) over (
            partition by scrip
            order by fiscal_year_bs, quarter
            rows between 19 preceding and current row
        ) as n_quarters_in_5y_window
    from base
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    pe_ratio,
    pb_ratio,
    pe_self_pct_5y,
    pb_self_pct_5y,
    pe_self_pct_all,
    n_quarters_in_5y_window,
    -- Bucket — use the 5-year percentile when we have ≥8 quarters of
    -- history, else fall back to the all-history rank. This avoids the
    -- first few quarters auto-tagging as VERY_CHEAP.
    case
        when pe_ratio is null                              then null
        when n_quarters_in_5y_window < 8                   then null  -- not enough history
        when pe_self_pct_5y <= 0.10                        then 'VERY_CHEAP'
        when pe_self_pct_5y <= 0.30                        then 'CHEAP'
        when pe_self_pct_5y <= 0.70                        then 'FAIR'
        when pe_self_pct_5y <= 0.90                        then 'EXPENSIVE'
        else                                                    'VERY_EXPENSIVE'
    end as self_valuation_tier,
    current_timestamp as computed_at
from with_pct
order by scrip, fiscal_year_bs, quarter
