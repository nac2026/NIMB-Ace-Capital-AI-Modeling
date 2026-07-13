{# -
    gold.beta_and_volatility — market risk snapshot per scrip.

    Regresses daily log-returns of the scrip against daily log-returns
    of the NEPSE index over a 2-year (≈504 trading day) lookback to
    extract:
      * beta                  — slope. >1 = amplifies market moves;
                                <1 = dampens; negative = counter-cyclical
      * alpha_annual          — intercept × 252 (annualized excess return)
      * r_squared             — how much of the scrip's variance the
                                index explains (stock-specific vs market)
      * annualized_vol        — scrip's own volatility, annualized
      * sharpe_ratio_2y       — (annual scrip return - rf) / annual vol.
                                Using 8% as the NPR risk-free proxy
                                (1-year NEPSE fixed deposit rate).

    Depends on silver.index_snapshots, which is populated by the
    scraper. If the scraper hasn't run, this model emits no rows —
    degrades gracefully rather than failing.
- #}
{{
    config(
        location=gold_external_location(),
        description='NEPSE beta, alpha, Sharpe, realized vol per scrip (2-year window).',
    )
}}

{%- set rf_annual = 0.08 -%}
{%- set trading_days_per_year = 252 -%}
{%- set lookback_days = 504 -%}

with scrip_returns as (
    select
        scrip,
        date,
        ln(close * 1.0 / nullif(lag(close) over (partition by scrip order by date), 0)) as log_return
    from {{ source('silver', 'closes') }}
),

nepse_returns as (
    select
        date,
        ln(close * 1.0 / nullif(lag(close) over (order by date), 0)) as nepse_log_return
    from {{ source('silver', 'index_snapshots') }}
    where index_name = 'NEPSE'
),

joined as (
    select
        sr.scrip,
        sr.date,
        sr.log_return,
        nr.nepse_log_return
    from scrip_returns sr
    join nepse_returns nr using (date)
    where sr.log_return is not null and nr.nepse_log_return is not null
),

-- Keep only the last ~2 years of aligned returns. rn is a countdown
-- from latest observation per scrip.
windowed as (
    select
        *,
        row_number() over (partition by scrip order by date desc) as rn
    from joined
),

trimmed as (
    select * from windowed where rn <= {{ lookback_days }}
),

-- Regression inputs — aggregate per scrip.
regression as (
    select
        scrip,
        count(*)                                                                                     as n_obs,
        max(date)                                                                                    as as_of,
        avg(log_return)                                                                              as mean_r,
        avg(nepse_log_return)                                                                        as mean_m,
        covar_samp(log_return, nepse_log_return)                                                     as cov_rm,
        var_samp(nepse_log_return)                                                                   as var_m,
        var_samp(log_return)                                                                         as var_r,
        corr(log_return, nepse_log_return)                                                           as corr_rm
    from trimmed
    group by scrip
)

select
    scrip,
    as_of,
    n_obs,
    -- beta = cov(r, m) / var(m).
    cov_rm / nullif(var_m, 0)                                                                        as beta,
    -- alpha (daily) = mean_r - beta * mean_m; annualized ×252.
    (mean_r - (cov_rm / nullif(var_m, 0)) * mean_m) * {{ trading_days_per_year }}                    as alpha_annual,
    -- R² = corr².
    corr_rm * corr_rm                                                                                as r_squared,
    -- Annualized vol of the scrip (not of residuals — true own-vol).
    sqrt(var_r * {{ trading_days_per_year }})                                                        as annualized_vol,
    -- Annualized scrip return (from log-returns).
    exp(mean_r * {{ trading_days_per_year }}) - 1                                                    as annualized_return,
    -- Sharpe ratio — (annual return - rf) / annual vol. rf = {{ rf_annual * 100 }}%.
    (exp(mean_r * {{ trading_days_per_year }}) - 1 - {{ rf_annual }})
        / nullif(sqrt(var_r * {{ trading_days_per_year }}), 0)                                       as sharpe_ratio_2y,
    current_timestamp                                                                                 as computed_at
from regression
where n_obs >= 60                                                         -- ≥ ~3 months of aligned returns
order by scrip
