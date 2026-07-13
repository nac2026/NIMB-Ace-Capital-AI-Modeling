{# -
    gold.internal_trade_surveillance — one scored row per internal fill: how
    suspicious does this trade look? The headline table for the CEO board and
    the agent tool.

    v2 composite — five components, each normalized 0..1, each date-aligned to
    the fill (not snapshots):

      exec (0.25)         — slippage vs the ±15-min interval VWAP (whole-day VWAP
                            as fallback), measured in SIGMAS of the scrip's own
                            20-day volatility so illiquid names aren't over-flagged;
                            3σ saturates. Filling outside the day's range = 1.0.
      manip (0.20)        — worst market-manipulation signal on the scrip:
                            speculation tier, that-day concentration flag,
                            wash/circular score, pump pattern.
      counterparty (0.25) — the collusion proxy: binomial surprise of how often
                            this fund faces this broker vs the broker's market
                            share (z/4, ≥3 fills), a market-flagged counterparty
                            (accum/dist/wash, ≥2 fills) = 0.6, and the fund
                            providing EXIT LIQUIDITY (buying while the
                            counterparty unwinds an accumulated position) = 0.7.
      cross (0.15)        — intra-firm wash: opposite fills across the firm's own
                            books within 5 min = 1.0; same-fund same-day
                            buy-and-sell churn = 0.5.
      outcome (0.15)      — post-trade markout: adverse T+5 drift in sigmas
                            (we bought and it fell / sold and it rose), 3σ
                            saturates; buying in the top decile of the trailing
                            20-day range = 0.5.

    score = 100 × Σ(weight × component); tiers HIGH ≥70 / ELEVATED ≥45 /
    MODERATE ≥25 / LOW. flag_reasons lists which checks fired. A flag for
    review, not a verdict.
- #}
{{
    config(
        location=gold_external_location(),
        description='Per internal fill: 0-100 five-component surveillance score (exec, manip, counterparty, cross, outcome) + tier + reasons.',
    )
}}

with circ as (
    select scrip, max(circular_score) as max_circular
    from {{ ref('broker_pair_graph') }}
    group by scrip
),

-- Counterparty's running position in the scrip BEFORE each day, from broker
-- flows: positive cum_before + selling that day = distributing into our buys.
flow as (
    select
        scrip, broker, trade_date, net_qty,
        sum(net_qty) over (
            partition by scrip, broker order by trade_date
            rows between unbounded preceding and 1 preceding
        ) as cum_before
    from {{ ref('broker_flow_daily') }}
),

-- Fills that participate in a near-simultaneous intra-firm cross.
cross_fills as (
    select buy_contract as contract_number from {{ ref('internal_cross_trade') }}
    union
    select sell_contract from {{ ref('internal_cross_trade') }}
),

-- Same fund, same scrip, same day, material volume on BOTH sides = churn.
churn as (
    select client_code, scrip, trade_date
    from {{ ref('internal_trade_enriched') }}
    group by client_code, scrip, trade_date
    having sum(case when side = 'B' then our_qty else 0 end) > 0
       and sum(case when side = 'S' then our_qty else 0 end) > 0
       and least(sum(case when side = 'B' then our_qty else 0 end),
                 sum(case when side = 'S' then our_qty else 0 end))
         / greatest(sum(case when side = 'B' then our_qty else 0 end),
                    sum(case when side = 'S' then our_qty else 0 end)) >= 0.5
),

scored as (
    select
        e.contract_number,
        e.scrip,
        e.trade_date,
        e.client_code,
        e.client_name,
        e.side,
        e.our_qty,
        e.our_value,
        e.our_broker,
        e.counterparty_broker,
        e.our_price,
        e.day_vwap,
        e.interval_vwap,
        e.n_interval_trades,
        e.vol_20d,
        e.markout_1d_pct,
        e.markout_5d_pct,
        e.markout_20d_pct,
        e.matched_floorsheet,

        -- ---- signal 1: execution quality ----
        -- Benchmark = interval VWAP when the window has enough prints, else day VWAP.
        case
            when e.interval_vwap is not null and e.n_interval_trades >= 5 then e.interval_vwap
            else e.day_vwap
        end as benchmark_vwap,
        case
            when coalesce(case when e.interval_vwap is not null and e.n_interval_trades >= 5
                               then e.interval_vwap else e.day_vwap end, 0) = 0 then null
            when e.side = 'B' then
                (e.our_price - (case when e.interval_vwap is not null and e.n_interval_trades >= 5
                                     then e.interval_vwap else e.day_vwap end))
                / (case when e.interval_vwap is not null and e.n_interval_trades >= 5
                        then e.interval_vwap else e.day_vwap end)
            else
                ((case when e.interval_vwap is not null and e.n_interval_trades >= 5
                       then e.interval_vwap else e.day_vwap end) - e.our_price)
                / (case when e.interval_vwap is not null and e.n_interval_trades >= 5
                        then e.interval_vwap else e.day_vwap end)
        end as slippage_vs_vwap_pct,
        case
            when e.day_vwap is null then null
            else e.our_qty * (e.our_price - e.day_vwap) * (case when e.side = 'B' then 1 else -1 end)
        end as slippage_npr,
        coalesce(
            (e.side = 'B' and e.day_high_fs is not null and e.our_price > e.day_high_fs)
         or (e.side = 'S' and e.day_low_fs  is not null and e.our_price < e.day_low_fs),
            false
        ) as worse_than_range_flag,

        -- ---- signal 2: trading-into-manipulation context ----
        ss.speculation_score as scrip_speculation_score,
        ss.speculation_tier  as scrip_speculation_tier,
        coalesce(bc.concentration_flag, false) as scrip_concentration_flag,
        coalesce(ci.max_circular, 0)           as scrip_circular_score,
        coalesce(
            pr.return_1m >= 0.25
         or (pr.return_3m >= 0.40 and pr.drawdown_from_peak <= -0.20),
            false
        ) as scrip_pump_flag,

        -- ---- signal 3: counterparty pattern (collusion proxy) ----
        cp.n_trades   as cp_n_trades,
        cp.share_of_fund_qty as cp_share_of_fund,
        cp.cp_market_share,
        cp.surprise_z as cp_surprise_z,
        coalesce(cp.cp_flagged, false) as cp_flagged,
        coalesce(cp.n_trades >= 3 and cp.n_days >= 2, false) as repeat_counterparty_flag,
        coalesce(
            e.side = 'B' and fl.cum_before > 0 and fl.net_qty < 0,
            false
        ) as exit_liquidity_flag,

        -- ---- signal 4: intra-firm cross / churn ----
        (cf.contract_number is not null) as cross_flag,
        (ch.client_code is not null)     as churn_flag,

        -- ---- signal 5: outcome / timing ----
        coalesce(
            e.side = 'B'
            and e.prior_high_20d is not null and e.prior_high_20d > e.prior_low_20d
            and (e.our_price - e.prior_low_20d) / (e.prior_high_20d - e.prior_low_20d) >= 0.9,
            false
        ) as bought_near_peak_flag
    from {{ ref('internal_trade_enriched') }} e
    left join {{ ref('speculation_score') }} ss on ss.scrip = e.scrip
    left join {{ ref('broker_concentration_daily') }} bc
           on bc.scrip = e.scrip and bc.trade_date = e.trade_date
    left join circ ci on ci.scrip = e.scrip
    left join {{ ref('price_returns') }} pr on pr.scrip = e.scrip
    left join {{ ref('internal_counterparty_exposure') }} cp
           on cp.client_code = e.client_code
          and cp.counterparty_broker = e.counterparty_broker
          and cp.scrip = e.scrip
    left join flow fl
           on fl.scrip = e.scrip and fl.broker = e.counterparty_broker
          and fl.trade_date = e.trade_date
    left join cross_fills cf on cf.contract_number = e.contract_number
    left join churn ch
           on ch.client_code = e.client_code and ch.scrip = e.scrip
          and ch.trade_date = e.trade_date
),

components as (
    select
        *,
        -- exec (0..1): slippage in sigmas of the scrip's own daily vol; 3σ saturates.
        -- Outside the day's traded range = hard 1.0.
        greatest(
            case when worse_than_range_flag then 1.0 else 0.0 end,
            least(1.0, greatest(0.0,
                coalesce(slippage_vs_vwap_pct, 0) / nullif(3 * coalesce(vol_20d, 0), 0)))
        ) as exec_component,
        -- manip (0..1): worst market-side signal on the scrip.
        greatest(
            case scrip_speculation_tier
                when 'HIGH' then 1.0 when 'ELEVATED' then 0.6 when 'MODERATE' then 0.3 else 0.0 end,
            case when scrip_concentration_flag then 0.6 else 0.0 end,
            least(1.0, scrip_circular_score),
            case when scrip_pump_flag then 0.7 else 0.0 end
        ) as manip_component,
        -- counterparty (0..1): statistical surprise + flagged broker + exit liquidity.
        greatest(
            case when cp_n_trades >= 3 and cp_surprise_z is not null
                 then least(1.0, greatest(0.0, cp_surprise_z / 4.0)) else 0.0 end,
            case when cp_flagged and cp_n_trades >= 2 then 0.6 else 0.0 end,
            case when exit_liquidity_flag then 0.7 else 0.0 end
        ) as counterparty_component,
        -- cross (0..1): near-simultaneous intra-firm cross = 1.0, same-day churn = 0.5.
        greatest(
            case when cross_flag then 1.0 else 0.0 end,
            case when churn_flag then 0.5 else 0.0 end
        ) as cross_component,
        -- outcome (0..1): adverse T+5 markout in sigmas (3σ saturates) + bought-near-peak.
        greatest(
            least(1.0, greatest(0.0,
                -coalesce(markout_5d_pct, 0) / nullif(3 * coalesce(vol_20d, 0) * sqrt(5), 0))),
            case when bought_near_peak_flag then 0.5 else 0.0 end
        ) as outcome_component
    from scored
)

select
    contract_number,
    scrip,
    trade_date,
    client_code,
    client_name,
    side,
    our_qty,
    our_value,
    our_broker,
    counterparty_broker,
    our_price,
    day_vwap,
    interval_vwap,
    n_interval_trades,
    matched_floorsheet,
    round(slippage_vs_vwap_pct, 4) as slippage_vs_vwap_pct,
    round(slippage_npr, 2)         as slippage_npr,
    worse_than_range_flag,
    round(markout_1d_pct, 4)  as markout_1d_pct,
    round(markout_5d_pct, 4)  as markout_5d_pct,
    round(markout_20d_pct, 4) as markout_20d_pct,
    scrip_speculation_score,
    scrip_speculation_tier,
    scrip_concentration_flag,
    round(scrip_circular_score, 4) as scrip_circular_score,
    scrip_pump_flag,
    cp_n_trades,
    round(cp_share_of_fund, 4) as cp_share_of_fund,
    round(cp_market_share, 4)  as cp_market_share,
    round(cp_surprise_z, 2)    as cp_surprise_z,
    cp_flagged,
    repeat_counterparty_flag,
    exit_liquidity_flag,
    cross_flag,
    churn_flag,
    bought_near_peak_flag,
    round(exec_component, 4)         as exec_component,
    round(manip_component, 4)        as manip_component,
    round(counterparty_component, 4) as counterparty_component,
    round(cross_component, 4)        as cross_component,
    round(outcome_component, 4)      as outcome_component,
    round(100 * (0.25 * exec_component + 0.20 * manip_component
               + 0.25 * counterparty_component + 0.15 * cross_component
               + 0.15 * outcome_component), 1) as surveillance_score,
    case
        when 100 * (0.25*exec_component + 0.20*manip_component + 0.25*counterparty_component
                  + 0.15*cross_component + 0.15*outcome_component) >= 70 then 'HIGH'
        when 100 * (0.25*exec_component + 0.20*manip_component + 0.25*counterparty_component
                  + 0.15*cross_component + 0.15*outcome_component) >= 45 then 'ELEVATED'
        when 100 * (0.25*exec_component + 0.20*manip_component + 0.25*counterparty_component
                  + 0.15*cross_component + 0.15*outcome_component) >= 25 then 'MODERATE'
        else 'LOW'
    end as surveillance_tier,
    list_filter([
        case when worse_than_range_flag then 'Filled outside the day''s traded range' end,
        case when exec_component >= 0.5 and not worse_than_range_flag
             then 'Fill materially worse than prevailing market (vol-adjusted)' end,
        case when scrip_speculation_tier in ('HIGH', 'ELEVATED')
             then 'Scrip flagged speculative (' || scrip_speculation_tier || ')' end,
        case when scrip_concentration_flag then 'Broker concentration on the scrip that day' end,
        case when scrip_circular_score >= 0.20 then 'Scrip shows wash / circular trading' end,
        case when scrip_pump_flag then 'Scrip in a pump / run-up pattern' end,
        case when cp_n_trades >= 3 and cp_surprise_z >= 3
             then 'Statistically improbable repeat counterparty (z=' || round(cp_surprise_z, 1) || ')' end,
        case when cp_flagged and cp_n_trades >= 2
             then 'Counterparty broker is market-flagged in this scrip' end,
        case when exit_liquidity_flag then 'Fund bought while counterparty was unwinding its position' end,
        case when cross_flag then 'Near-simultaneous opposite fill within the firm' end,
        case when churn_flag then 'Same fund bought AND sold this scrip the same day' end,
        case when bought_near_peak_flag then 'Bought in the top decile of the 20-day range' end,
        case when coalesce(markout_5d_pct, 0) <= -0.05
             then 'Price moved sharply against the fund within 5 days' end
    ], x -> x is not null) as flag_reasons,
    current_timestamp as computed_at
from components
