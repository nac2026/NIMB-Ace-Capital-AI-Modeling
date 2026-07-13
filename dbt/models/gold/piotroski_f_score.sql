{# -
    gold.piotroski_f_score — bank-adapted 9-signal quality score.

    Piotroski's original F-Score was designed for non-financial firms.
    Banks have different economics (leverage is the product, not a
    warning), different reporting (no CFO line), and different risk
    drivers (NPL, CAR). This is a 9-signal bank-adaptation:

      PROFITABILITY (4)
        p1  Net profit positive this period                    (1 pt)
        p2  Return on assets positive this period              (1 pt)
        p3  Net profit grew YoY                                (1 pt)
        p4  Return on assets improved YoY                      (1 pt)
      BALANCE SHEET HEALTH (3)
        p5  NPL ratio did not worsen YoY                       (1 pt)
        p6  Capital adequacy (CAR) maintained or improved YoY  (1 pt)
        p7  No large share issuance (paid-up capital up ≤20%)  (1 pt)
      OPERATING EFFICIENCY (2)
        p8  Net Interest Margin improved YoY                   (1 pt)
        p9  Cost-to-income ratio improved (decreased) YoY      (1 pt)

    Total: 0–9. Interpretation:
      7–9 → STRONG (most quality factors positive)
      4–6 → MODERATE
      0–3 → WEAK (multiple red flags)

    All 9 require YoY comparison (for p3–p9), so rows where the YoY
    predecessor is missing emit NULL for that signal. The f_score
    column sums whatever signals are available — undercounts but doesn't
    lie. Downstream consumers should check `n_signals_available` before
    using the raw score.
- #}
{{
    config(
        location=gold_external_location(),
        description='Bank-adapted Piotroski F-Score — 9 binary signals, 0-9 sum.',
    )
}}

with base as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        net_profit,
        roa,
        npl_ratio,
        car,
        paid_up_capital,
        -- Compute NIM + CIR inline so we don't depend on other Gold
        -- models (keeps Piotroski dependency-free within dbt).
        net_interest_income * 1.0 / nullif(total_assets, 0) as nim_current,
        (coalesce(staff_expenses, 0)
          + coalesce(other_operating_expenses, 0)
          + coalesce(depreciation_amortization, 0))
          * 1.0 / nullif(total_operating_income, 0)         as cti_current
    from {{ source('silver', 'fundamentals_snapshots') }}
),

-- All YoY lags in one pass.
lagged as (
    select
        *,
        lag(net_profit, 4)      over w as net_profit_prev_y,
        lag(roa, 4)             over w as roa_prev_y,
        lag(npl_ratio, 4)       over w as npl_ratio_prev_y,
        lag(car, 4)             over w as car_prev_y,
        lag(paid_up_capital, 4) over w as paid_up_capital_prev_y,
        lag(nim_current, 4)     over w as nim_prev_y,
        lag(cti_current, 4)     over w as cti_prev_y
    from base
    window w as (partition by scrip order by fiscal_year_bs, quarter)
),

signals as (
    select
        scrip,
        fiscal_year_bs,
        quarter,
        -- Profitability
        case when net_profit > 0                     then 1 when net_profit is null then null else 0 end as p1_positive_profit,
        case when roa > 0                            then 1 when roa        is null then null else 0 end as p2_positive_roa,
        case when net_profit > net_profit_prev_y     then 1 when net_profit_prev_y is null then null else 0 end as p3_profit_grew,
        case when roa        > roa_prev_y            then 1 when roa_prev_y        is null then null else 0 end as p4_roa_improved,
        -- BS health
        case when npl_ratio <= npl_ratio_prev_y      then 1 when npl_ratio_prev_y  is null then null else 0 end as p5_npl_not_worse,
        case when car       >= car_prev_y            then 1 when car_prev_y        is null then null else 0 end as p6_car_not_worse,
        case when paid_up_capital <= paid_up_capital_prev_y * 1.20
                                                     then 1 when paid_up_capital_prev_y is null then null else 0 end as p7_no_large_issuance,
        -- Operating efficiency
        case when nim_current >= nim_prev_y          then 1 when nim_prev_y        is null then null else 0 end as p8_nim_improved,
        case when cti_current <= cti_prev_y          then 1 when cti_prev_y        is null then null else 0 end as p9_cti_improved
    from lagged
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    p1_positive_profit, p2_positive_roa, p3_profit_grew, p4_roa_improved,
    p5_npl_not_worse,   p6_car_not_worse, p7_no_large_issuance,
    p8_nim_improved,    p9_cti_improved,
    -- Sum available signals; signals with NULL inputs contribute 0 to
    -- the sum but increment the "missing" count so the denominator is
    -- visible downstream.
    coalesce(p1_positive_profit, 0)
      + coalesce(p2_positive_roa, 0)
      + coalesce(p3_profit_grew, 0)
      + coalesce(p4_roa_improved, 0)
      + coalesce(p5_npl_not_worse, 0)
      + coalesce(p6_car_not_worse, 0)
      + coalesce(p7_no_large_issuance, 0)
      + coalesce(p8_nim_improved, 0)
      + coalesce(p9_cti_improved, 0)
                                                                      as f_score,
    (case when p1_positive_profit is not null then 1 else 0 end
      + case when p2_positive_roa     is not null then 1 else 0 end
      + case when p3_profit_grew       is not null then 1 else 0 end
      + case when p4_roa_improved      is not null then 1 else 0 end
      + case when p5_npl_not_worse     is not null then 1 else 0 end
      + case when p6_car_not_worse     is not null then 1 else 0 end
      + case when p7_no_large_issuance is not null then 1 else 0 end
      + case when p8_nim_improved      is not null then 1 else 0 end
      + case when p9_cti_improved      is not null then 1 else 0 end) as n_signals_available,
    current_timestamp                                                  as computed_at
from signals
order by scrip, fiscal_year_bs, quarter
