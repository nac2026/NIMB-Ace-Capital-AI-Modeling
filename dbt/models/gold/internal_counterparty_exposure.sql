{# -
    gold.internal_counterparty_exposure — who keeps ending up on the other side
    of the fund's trades? One row per (fund, counterparty broker, scrip).

    The collusion-proxy signal. A fund's counterparties should look roughly like
    the scrip's overall broker mix; a counterparty whose share of the fund's flow
    is far above its market share in that scrip is statistically surprising:

      share_of_fund   = fund qty traded against this broker / fund qty in scrip
      cp_market_share = broker's share of all floor-sheet sides in the scrip
      surprise_z      = (share_of_fund − cp_market_share)
                        / sqrt(p(1−p)/n_trades)      (one-sample proportion z)

    surprise_z ≥ ~3 with n_trades ≥ 3 means "this pairing is very unlikely to be
    random routing". It gets worse when the same broker is independently flagged
    by the market-side models (accumulating/distributing the scrip, or sitting
    in a wash pair). A flag for review, not a verdict — thin-scrip routing can
    legitimately concentrate.
- #}
{{
    config(
        location=gold_external_location(),
        description='Per (fund, counterparty broker, scrip): repeat-trading stats + binomial surprise z + market-side flags.',
    )
}}

with fills as (
    select *
    from {{ ref('internal_trade_enriched') }}
    where counterparty_broker is not null
),

-- The fund's total matched quantity per scrip (denominator for share-of-fund).
fund_scrip as (
    select client_code, scrip, sum(our_qty) as fund_qty, count(*) as fund_trades
    from fills
    group by 1, 2
),

-- Each broker's share of ALL floor-sheet sides in the scrip (its market share).
sides as (
    select scrip, buyer_broker  as broker, quantity from {{ source('silver', 'floorsheet') }}
    union all
    select scrip, seller_broker as broker, quantity from {{ source('silver', 'floorsheet') }}
),
broker_share as (
    select
        scrip, broker,
        sum(quantity) as broker_sides,
        sum(sum(quantity)) over (partition by scrip) as scrip_sides
    from sides
    group by scrip, broker
),

-- Market-side flags on the counterparty in this scrip.
wash_pairs as (
    select scrip, broker_lo as broker from {{ ref('broker_pair_graph') }} where circular_score >= 0.20
    union
    select scrip, broker_hi as broker from {{ ref('broker_pair_graph') }} where circular_score >= 0.20
),

exposure as (
    select
        f.client_code,
        max(f.client_name) as client_name,
        f.counterparty_broker,
        f.scrip,
        count(*) as n_trades,
        sum(f.our_qty) as total_qty,
        sum(f.our_value) as total_amount,
        count(distinct f.trade_date) as n_days,
        min(f.trade_date) as first_date,
        max(f.trade_date) as last_date
    from fills f
    group by f.client_code, f.counterparty_broker, f.scrip
)

select
    e.client_code,
    e.client_name,
    e.counterparty_broker,
    e.scrip,
    e.n_trades,
    e.total_qty,
    e.total_amount,
    e.n_days,
    e.first_date,
    e.last_date,
    e.total_qty / nullif(fsq.fund_qty, 0) as share_of_fund_qty,
    bs.broker_sides / nullif(bs.scrip_sides, 0) as cp_market_share,
    -- One-sample proportion z: how improbable is this pairing under random routing?
    case
        when bs.scrip_sides > 0
         and bs.broker_sides / bs.scrip_sides between 0.000001 and 0.999999
        then ((e.total_qty / nullif(fsq.fund_qty, 0)) - (bs.broker_sides / bs.scrip_sides))
             / sqrt((bs.broker_sides / bs.scrip_sides) * (1 - bs.broker_sides / bs.scrip_sides) / e.n_trades)
    end as surprise_z,
    coalesce(ba.accumulation_flag, false) as cp_is_accumulator,
    coalesce(ba.distribution_flag, false) as cp_is_distributor,
    (wp.broker is not null) as cp_in_wash_pair,
    (coalesce(ba.accumulation_flag, false) or coalesce(ba.distribution_flag, false)
     or wp.broker is not null) as cp_flagged,
    current_timestamp as computed_at
from exposure e
join fund_scrip fsq on fsq.client_code = e.client_code and fsq.scrip = e.scrip
left join broker_share bs on bs.scrip = e.scrip and bs.broker = e.counterparty_broker
left join {{ ref('broker_accumulation') }} ba
       on ba.scrip = e.scrip and ba.broker = e.counterparty_broker
left join wash_pairs wp on wp.scrip = e.scrip and wp.broker = e.counterparty_broker
