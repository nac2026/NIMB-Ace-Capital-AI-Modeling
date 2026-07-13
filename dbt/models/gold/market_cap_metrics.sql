{# -
    gold.market_cap_metrics — size + liquidity snapshot per scrip.

    Research Q2 ("Market Capitalisation, Float & Supply Risk") + Q1
    ("Free-float liquidity and exit feasibility"). Uses the latest
    close × the latest reported ordinary-share count.

    Columns:
      market_cap_npr            — close × shares (NPR, full units)
      market_cap_tier           — LARGE / MID / SMALL bucket
      paid_up_capital_npr       — total paid-up capital (NPR full units)
      price_to_face_value       — close / 100 (NEPSE face = NPR 100).
                                  Useful for the research question
                                  "Price-to-face-value perception risk".
      book_value_per_share      — latest BVPS
      price_to_book_vs_face     — another size-vs-value view

    Notes on units:
      * silver.fundamentals_snapshots.ordinary_shares is in THOUSANDS of
        shares (matches paid_up_capital / face_value).
      * silver.closes.close is NPR per share.
      * market_cap = close × (ordinary_shares × 1000) gives NPR.
- #}
{{
    config(
        location=gold_external_location(),
        description='Market cap + paid-up + price-to-face snapshot per scrip.',
    )
}}

{%- set nepse_face_value = 100 -%}

with latest_fundamentals as (
    select *
    from {{ source('silver', 'fundamentals_snapshots') }}
    qualify row_number() over (partition by scrip order by fiscal_year_bs desc, quarter desc) = 1
),

latest_close as (
    select scrip, date, close
    from {{ source('silver', 'closes') }}
    qualify row_number() over (partition by scrip order by date desc) = 1
)

select
    lf.scrip,
    lc.date                                                 as as_of,
    lc.close                                                as latest_close,
    -- ordinary_shares is in '000s → multiply by 1000 for raw share count.
    lf.ordinary_shares * 1000                               as shares_outstanding,
    -- market_cap in NPR full units. Cast to double because bigints may
    -- overflow the 32-bit range for the largest banks.
    cast(lc.close * lf.ordinary_shares * 1000 as double)    as market_cap_npr,
    -- Bucketed size. NEPSE commercial banks span roughly NPR 20bn (SCB)
    -- to NPR 200bn+ (NABIL, NICA); thresholds tuned accordingly.
    case
        when lc.close * lf.ordinary_shares * 1000 >= 100e9  then 'LARGE'
        when lc.close * lf.ordinary_shares * 1000 >=  40e9  then 'MID'
        when lc.close * lf.ordinary_shares * 1000 >=  15e9  then 'SMALL'
        else                                                      'MICRO'
    end                                                     as market_cap_tier,
    -- paid_up_capital is in NPR '000s already; multiply by 1000 for raw.
    cast(lf.paid_up_capital * 1000 as double)               as paid_up_capital_npr,
    lf.bvps,
    -- Price-to-face-value is a NEPSE-specific sentiment gauge. NEPSE
    -- face = NPR 100. Close of 500 = 5× face. Research Q2 flags this
    -- as a 'perception risk' signal.
    lc.close / {{ nepse_face_value }}                       as price_to_face_value,
    -- Price-to-book — same as pb_ratio but against the absolute BVPS
    -- rather than whatever's in silver (cross-check).
    lc.close / nullif(lf.bvps, 0)                           as price_to_book_computed,
    current_timestamp                                       as computed_at
from latest_fundamentals lf
join latest_close lc using (scrip)
order by market_cap_npr desc nulls last
