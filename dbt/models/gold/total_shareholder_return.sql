{# -
    gold.total_shareholder_return — capital appreciation + dividends
    over 1-year / 3-year / 5-year horizons. Answers "what did a
    shareholder ACTUALLY earn?" which diverges from price-only return
    for dividend-paying banks.

    Formula (simple approximation, not geometric compounding):
      TSR_Nyears = (close_today + sum(cash_dividends_over_N_years))
                   / close_N_years_ago - 1

    We approximate dividend per share from silver.corporate_actions:
      cash_div_per_share = cash_dividend_pct × 100  (NEPSE face value)

    Bonus shares INCREASE holding but don't add cash — we ignore them
    for the TSR cash-return definition. A "total return" including bonus
    share reinvestment is a nice-to-have future model.

    Depends on silver.corporate_actions (scraper-populated). If empty,
    TSR degrades to pure capital return (price_returns values).
- #}
{{
    config(
        location=gold_external_location(),
        description='Capital + dividend return over 1/3/5 year horizons per scrip.',
    )
}}

{%- set face_value = 100 -%}

with latest_close as (
    select scrip, date as as_of, close as close_today
    from {{ source('silver', 'closes') }}
    qualify row_number() over (partition by scrip order by date desc) = 1
),

-- Close N trading days ago (~22/mo, 252/yr).
historical_close as (
    select scrip, date, close, row_number() over (partition by scrip order by date desc) as rn
    from {{ source('silver', 'closes') }}
),

dividends_cum as (
    -- Cumulative cash dividend paid out per scrip over the last N years.
    -- In silver.corporate_actions, `ratio` is the decimal percentage
    -- (e.g. 0.055 = 5.5%) and `action_type` is lowercase. cash per share
    -- = ratio × face_value.
    select
        scrip,
        action_type,
        announcement_date,
        ratio,
        ratio * {{ face_value }} as cash_per_share
    from {{ source('silver', 'corporate_actions') }}
    where action_type = 'cash_dividend'
      and ratio is not null
      and announcement_date is not null
),

-- Aggregate dividends per scrip per lookback window from TODAY.
-- DuckDB can compare date math across rows via a CROSS JOIN on the
-- latest close date.
per_scrip_dividends as (
    select
        lc.scrip,
        lc.as_of,
        lc.close_today,
        coalesce(sum(case when d.announcement_date >= lc.as_of - interval 1  year then d.cash_per_share end), 0) as div_1y,
        coalesce(sum(case when d.announcement_date >= lc.as_of - interval 3  year then d.cash_per_share end), 0) as div_3y,
        coalesce(sum(case when d.announcement_date >= lc.as_of - interval 5  year then d.cash_per_share end), 0) as div_5y
    from latest_close lc
    left join dividends_cum d on d.scrip = lc.scrip
    group by lc.scrip, lc.as_of, lc.close_today
)

select
    psd.scrip,
    psd.as_of,
    psd.close_today,
    max(case when h.rn = 252  then h.close end)  as close_1y_ago,
    max(case when h.rn = 756  then h.close end)  as close_3y_ago,
    max(case when h.rn = 1260 then h.close end)  as close_5y_ago,
    psd.div_1y,
    psd.div_3y,
    psd.div_5y,
    -- TSR formulas. Compares simple (not geometric) return vs absolute
    -- price N years ago plus cumulative cash payouts.
    (psd.close_today + psd.div_1y)
        / nullif(max(case when h.rn = 252  then h.close end), 0) - 1    as tsr_1y,
    (psd.close_today + psd.div_3y)
        / nullif(max(case when h.rn = 756  then h.close end), 0) - 1    as tsr_3y,
    (psd.close_today + psd.div_5y)
        / nullif(max(case when h.rn = 1260 then h.close end), 0) - 1    as tsr_5y,
    current_timestamp                                                   as computed_at
from per_scrip_dividends psd
left join historical_close h on h.scrip = psd.scrip and h.rn in (252, 756, 1260)
group by psd.scrip, psd.as_of, psd.close_today, psd.div_1y, psd.div_3y, psd.div_5y
order by psd.scrip
