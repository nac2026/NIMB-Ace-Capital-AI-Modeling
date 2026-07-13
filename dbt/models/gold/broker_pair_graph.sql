{# -
    gold.broker_pair_graph — directed broker→broker trade edges per scrip,
    with reciprocal (circular / wash) trading detection.

    Each unordered broker pair {lo, hi} for a scrip gets the volume flowing
    in each direction (lo→hi = lo buys from hi, and hi→lo). Wash / circular
    trading shows up as a pair that trades heavily in BOTH directions with
    little net positional change — brokers passing shares back and forth to
    manufacture volume and move price.

      reciprocal_balance = min(dir volumes) / max(dir volumes)  (1 = perfectly
                           balanced ping-pong; 0 = one-directional, normal)
      circular_score     = reciprocal_balance × (reciprocal_volume share of
                           the scrip's volume) → 0..1, high = suspicious.

    self_trade rows (lo = hi: same broker on both sides) are direct wash
    trades and always score 1.0 on balance. Research Q (circular trading
    detection / speculative identification).
- #}
{{
    config(
        location=gold_external_location(),
        description='Per (scrip, broker pair): directional volumes + reciprocal-balance circular/wash score.',
    )
}}

with edges as (
    select
        scrip,
        buyer_broker,
        seller_broker,
        sum(quantity) as qty,
        sum(amount)   as amount,
        count(*)      as n_trades
    from {{ source('silver', 'floorsheet') }}
    group by scrip, buyer_broker, seller_broker
),

scrip_vol as (
    select scrip, sum(qty) as scrip_qty from edges group by scrip
),

-- Collapse directed edges into unordered pairs (lo, hi) with per-direction qty.
pairs as (
    select
        scrip,
        least(buyer_broker, seller_broker)    as broker_lo,
        greatest(buyer_broker, seller_broker) as broker_hi,
        -- volume where lo is the buyer (hi → lo)
        sum(case when buyer_broker <= seller_broker then qty else 0 end) as qty_lo_buys,
        -- volume where hi is the buyer (lo → hi)
        sum(case when buyer_broker >  seller_broker then qty else 0 end) as qty_hi_buys,
        sum(qty)              as pair_qty,
        sum(amount)           as pair_amount,
        cast(sum(n_trades) as bigint) as pair_trades
    from edges
    group by scrip, least(buyer_broker, seller_broker), greatest(buyer_broker, seller_broker)
)

select
    p.scrip,
    p.broker_lo,
    p.broker_hi,
    (p.broker_lo = p.broker_hi)                            as self_trade,
    p.qty_lo_buys,
    p.qty_hi_buys,
    p.pair_qty,
    p.pair_amount,
    p.pair_trades,
    case
        when p.broker_lo = p.broker_hi then 1.0
        when greatest(p.qty_lo_buys, p.qty_hi_buys) > 0
            then least(p.qty_lo_buys, p.qty_hi_buys) / greatest(p.qty_lo_buys, p.qty_hi_buys)
        else 0.0
    end as reciprocal_balance,
    case when v.scrip_qty > 0 then p.pair_qty / v.scrip_qty else 0 end as pair_volume_share,
    (
        case
            when p.broker_lo = p.broker_hi then 1.0
            when greatest(p.qty_lo_buys, p.qty_hi_buys) > 0
                then least(p.qty_lo_buys, p.qty_hi_buys) / greatest(p.qty_lo_buys, p.qty_hi_buys)
            else 0.0
        end
        * case when v.scrip_qty > 0 then p.pair_qty / v.scrip_qty else 0 end
    ) as circular_score,
    current_timestamp as computed_at
from pairs p
join scrip_vol v using (scrip)
