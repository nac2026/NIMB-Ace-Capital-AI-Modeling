{# -
    gold.internal_cross_trade — intra-firm cross / wash pairs: one fund account
    buying a scrip while another (or the same) fund account sells it within a
    short window on the same day.

    Legitimate inter-scheme rebalancing exists, but near-simultaneous opposite
    fills across the firm's own books are exactly how internal wash/parking
    trades look, so every pair within 5 minutes is surfaced for review. One row
    per (buy fill, sell fill) pair on the same scrip + day within the window.
- #}
{{
    config(
        location=gold_external_location(),
        description='Near-simultaneous intra-firm buy/sell pairs in the same scrip (cross/wash candidates).',
    )
}}

with fills as (
    select contract_number, scrip, trade_date, client_code, client_name,
           side, our_qty, our_price, traded_at
    from {{ ref('internal_trade_enriched') }}
)

select
    b.scrip,
    b.trade_date,
    b.client_code  as buy_client,
    s.client_code  as sell_client,
    b.contract_number as buy_contract,
    s.contract_number as sell_contract,
    b.our_qty   as buy_qty,
    s.our_qty   as sell_qty,
    b.our_price as buy_price,
    s.our_price as sell_price,
    abs(date_diff('second', b.traded_at, s.traded_at)) as time_gap_s,
    (b.client_code = s.client_code) as same_client,
    current_timestamp as computed_at
from fills b
join fills s
  on s.scrip = b.scrip
 and s.trade_date = b.trade_date
 and s.side = 'S'
 and b.side = 'B'
 and s.contract_number != b.contract_number
 and abs(date_diff('second', b.traded_at, s.traded_at)) <= 300
