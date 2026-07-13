{# -
    gold.investment_scorecard — the CROWN-JEWEL analytics output. One
    row per active scrip with a final 0-100 score + recommendation.

    Five weighted components:
      Fundamental Quality   30%   — gold.fundamental_quality_composite
      Valuation (self)      25%   — gold.valuation_history (P/E self pct)
      Momentum              20%   — gold.price_returns (6m return percentile)
      Risk (inverse vol)    15%   — gold.beta_and_volatility (sharpe pct)
      Income                10%   — gold.dividend_yield (yield percentile)

    Each component is normalized to [0,1]. The valuation component is
    FLIPPED (cheaper = better = higher contribution). The scorecard is
    designed for the LLM tool layer to return a single actionable
    answer to "should I buy NABIL?" without hand-waving.

    Recommendation tiers (threshold chosen to spread the universe
    meaningfully — adjust in the var below if analysts want finer
    granularity):

         >=70  STRONG_BUY
       55-70   BUY
       40-55   HOLD
       25-40   REDUCE
         <25   SELL

    This is a COMPOSITE recommendation — it does not replace analyst
    judgment. It flags candidates for deep-dive; analysts override on
    qualitative factors (governance, macro thesis, insider flows).
- #}
{{
    config(
        location=gold_external_location(),
        description='0-100 investment scorecard per scrip with BUY/HOLD/SELL recommendation.',
    )
}}

with

latest_quality as (
    select scrip, quality_score_0_100
    from {{ ref('fundamental_quality_composite') }}
    qualify row_number() over (partition by scrip order by fiscal_year_bs desc, quarter desc) = 1
),

latest_valuation as (
    select scrip, pe_self_pct_5y
    from {{ ref('valuation_history') }}
    qualify row_number() over (partition by scrip order by fiscal_year_bs desc, quarter desc) = 1
),

latest_returns as (
    select scrip, return_6m, realized_vol_20d
    from {{ ref('price_returns') }}
),

latest_risk as (
    select scrip, sharpe_ratio_2y, annualized_vol, beta
    from {{ ref('beta_and_volatility') }}
),

latest_income as (
    select scrip, total_dividend_yield
    from {{ ref('dividend_yield') }}
    qualify row_number() over (partition by scrip order by fiscal_year_bs desc) = 1
),

-- Cross-join to get all active scrips. Missing components fall to 0.5
-- (neutral) so a data gap isn't punished as a 0-score.
assembled as (
    select
        sm.scrip,
        sm.sector,
        q.quality_score_0_100,
        v.pe_self_pct_5y,
        r.return_6m,
        r.realized_vol_20d,
        rk.sharpe_ratio_2y,
        rk.annualized_vol,
        rk.beta,
        i.total_dividend_yield
    from {{ source('silver', 'scrip_master') }} sm
    left join latest_quality   q  using (scrip)
    left join latest_valuation v  using (scrip)
    left join latest_returns   r  using (scrip)
    left join latest_risk      rk using (scrip)
    left join latest_income    i  using (scrip)
    where sm.is_active
),

-- Cross-sectional percentile ranks so each component is comparable.
ranked as (
    select
        *,
        -- Quality — higher is better. Already 0-100 but rescale to 0-1.
        quality_score_0_100 / 100.0                                                                  as n_quality,
        -- Valuation — FLIPPED: cheaper (lower pe_self_pct_5y) = higher score.
        1.0 - coalesce(pe_self_pct_5y, 0.5)                                                           as n_valuation,
        -- Momentum — percentile rank of 6m return across the active universe.
        percent_rank() over (order by return_6m nulls first)                                          as n_momentum,
        -- Risk — percentile rank of Sharpe ratio (higher is better).
        percent_rank() over (order by sharpe_ratio_2y nulls first)                                    as n_risk,
        -- Income — percentile rank of dividend yield (higher is better).
        percent_rank() over (order by total_dividend_yield nulls first)                               as n_income
    from assembled
)

select
    scrip,
    sector,
    -- Expose each normalized component so the LLM can explain WHY a
    -- scrip got the score it did.
    round(100 * coalesce(n_quality,   0.5), 1) as quality_pct,
    round(100 * coalesce(n_valuation, 0.5), 1) as valuation_pct,
    round(100 * coalesce(n_momentum,  0.5), 1) as momentum_pct,
    round(100 * coalesce(n_risk,      0.5), 1) as risk_pct,
    round(100 * coalesce(n_income,    0.5), 1) as income_pct,
    -- Raw underlying values for traceability.
    quality_score_0_100, pe_self_pct_5y, return_6m, sharpe_ratio_2y, total_dividend_yield,
    -- Weighted composite.
    round(100 * (
          0.30 * coalesce(n_quality,   0.5)
        + 0.25 * coalesce(n_valuation, 0.5)
        + 0.20 * coalesce(n_momentum,  0.5)
        + 0.15 * coalesce(n_risk,      0.5)
        + 0.10 * coalesce(n_income,    0.5)
    ), 2) as scorecard_0_100,
    -- Recommendation.
    case
        when 100 * (
              0.30 * coalesce(n_quality,   0.5)
            + 0.25 * coalesce(n_valuation, 0.5)
            + 0.20 * coalesce(n_momentum,  0.5)
            + 0.15 * coalesce(n_risk,      0.5)
            + 0.10 * coalesce(n_income,    0.5)
        ) >= 70                                                             then 'STRONG_BUY'
        when 100 * (
              0.30 * coalesce(n_quality,   0.5)
            + 0.25 * coalesce(n_valuation, 0.5)
            + 0.20 * coalesce(n_momentum,  0.5)
            + 0.15 * coalesce(n_risk,      0.5)
            + 0.10 * coalesce(n_income,    0.5)
        ) >= 55                                                             then 'BUY'
        when 100 * (
              0.30 * coalesce(n_quality,   0.5)
            + 0.25 * coalesce(n_valuation, 0.5)
            + 0.20 * coalesce(n_momentum,  0.5)
            + 0.15 * coalesce(n_risk,      0.5)
            + 0.10 * coalesce(n_income,    0.5)
        ) >= 40                                                             then 'HOLD'
        when 100 * (
              0.30 * coalesce(n_quality,   0.5)
            + 0.25 * coalesce(n_valuation, 0.5)
            + 0.20 * coalesce(n_momentum,  0.5)
            + 0.15 * coalesce(n_risk,      0.5)
            + 0.10 * coalesce(n_income,    0.5)
        ) >= 25                                                             then 'REDUCE'
        else                                                                     'SELL'
    end as recommendation,
    current_timestamp as computed_at
from ranked
order by scorecard_0_100 desc
