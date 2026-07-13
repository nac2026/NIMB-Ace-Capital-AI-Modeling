{# -
    gold.quarterly_growth — YoY and QoQ growth rates on every canonical
    flow + stock metric. One row per (scrip, fy, quarter). Needed for
    research Q3 ("Revenue and profit growth trend"), Q12 ("Quarterly
    financial deviation check"), and downstream Piotroski signal #3
    (profit growth YoY > 0).

    Conventions:
      * YoY = (current - value 4 quarters ago) / |value 4 quarters ago|
      * QoQ = (current - value 1 quarter ago) / |value 1 quarter ago|
      * We use abs(denominator) to keep signs interpretable when the
        prior value is negative (e.g. a loss reversing to a profit).
      * Rows where the denominator is 0 or NULL return NULL — downstream
        consumers should handle that explicitly rather than imputing 0.
      * 3Y growth is emitted too since it's the SOW's de-facto alpha
        horizon for fundamental factors.

    NOTE: this uses raw per-quarter values, NOT TTM. For smoothed TTM
    growth join onto gold.ttm_fundamentals and compute similarly —
    that's a follow-on model when analysts ask for it.
- #}
{{
    config(
        location=gold_external_location(),
        description='YoY / QoQ / 3-year growth rates on core flow and stock metrics.',
    )
}}

{%- set growth_metrics = [
    'net_profit',
    'operating_profit',
    'profit_before_tax',
    'net_interest_income',
    'total_operating_income',
    'net_fees_income',
    'staff_expenses',
    'total_assets',
    'total_loans',
    'total_deposits',
    'shareholders_equity',
] -%}

with

base as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        {% for m in growth_metrics -%}
        {{ m }}{{ ',' if not loop.last }}
        {% endfor %}
    from {{ source('silver', 'fundamentals_snapshots') }}
),

-- Lag each metric by 1 (QoQ), 4 (YoY), 12 (3-year) quarters. DuckDB
-- evaluates all these windows in a single pass.
lagged as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        {% for m in growth_metrics -%}
        {{ m }},
        lag({{ m }}, 1)  over w as {{ m }}_qoq_prev,
        lag({{ m }}, 4)  over w as {{ m }}_yoy_prev,
        lag({{ m }}, 12) over w as {{ m }}_3y_prev{{ ',' if not loop.last }}
        {% endfor %}
    from base
    window w as (partition by scrip order by fiscal_year_bs, quarter)
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    {% for m in growth_metrics %}
    {{ m }},
    ({{ m }} - {{ m }}_qoq_prev) / nullif(abs({{ m }}_qoq_prev), 0) as {{ m }}_qoq_pct,
    ({{ m }} - {{ m }}_yoy_prev) / nullif(abs({{ m }}_yoy_prev), 0) as {{ m }}_yoy_pct,
    ({{ m }} - {{ m }}_3y_prev)  / nullif(abs({{ m }}_3y_prev),  0) as {{ m }}_3y_pct{{ ',' if not loop.last }}
    {% endfor %},
    current_timestamp as computed_at
from lagged
order by scrip, fiscal_year_bs, quarter
