{# -
    gold.valuation — per-scrip valuation snapshot vs sector peer medians.

    Columns:
      * pe_trailing / pb        from latest silver.fundamentals_snapshots row
      * peer_pe_median          median P/E across active scrips in the sector
      * peer_pb_median          median P/B across active scrips in the sector
      * pe_vs_peer_pct          (pe_trailing - peer_pe_median) / peer_pe_median;
                                positive = premium, negative = discount
      * fair_value_forward_eps  placeholder (requires forward EPS estimate
                                we don't have yet; NULL until that lands)
      * upside_pct              (peer_pe_median * eps) / latest_close - 1 —
                                how far the peer-multiple-implied price is
                                from today's close

    One row per active scrip with a fundamental snapshot and at least one
    price observation.
- #}
{{
    config(
        location=gold_external_location(),
        description='Per-scrip valuation snapshot vs sector peer medians (P/E, P/B, upside).',
    )
}}

with

-- Latest close per scrip — drives the upside calc.
latest_price as (
    select scrip, date, close
    from {{ source('silver', 'prices') }}
    qualify row_number() over (partition by scrip order by date desc) = 1
),

-- Most recent fundamental snapshot per scrip, joined to sector.
latest_snap as (
    select
        fs.scrip, fs.fiscal_year_bs, fs.quarter,
        fs.pe_ratio, fs.pb_ratio, fs.eps, fs.bvps,
        sm.sector
    from {{ source('silver', 'fundamentals_snapshots') }} fs
    join {{ source('silver', 'scrip_master') }}           sm using (scrip)
    where sm.is_active
    qualify row_number() over (
        partition by fs.scrip
        order by fs.fiscal_year_bs desc, fs.quarter desc
    ) = 1
),

-- Sector-wide peer medians (one row per sector).
peer_medians as (
    select
        sector,
        median(pe_ratio) as peer_pe_median,
        median(pb_ratio) as peer_pb_median
    from latest_snap
    group by sector
)

select
    ls.scrip,
    lp.date,
    ls.pe_ratio                                                    as pe_trailing,
    cast(null as double)                                           as pe_forward,
    ls.pb_ratio                                                    as pb,
    pm.peer_pe_median,
    pm.peer_pb_median,
    (ls.pe_ratio - pm.peer_pe_median) / nullif(pm.peer_pe_median, 0)  as pe_vs_peer_pct,
    cast(null as double)                                           as fair_value_forward_eps,
    case
        when ls.eps is not null
         and lp.close > 0
         and pm.peer_pe_median is not null
        then (pm.peer_pe_median * ls.eps) / lp.close - 1
    end                                                            as upside_pct,
    current_timestamp                                              as computed_at
from latest_snap ls
join peer_medians pm using (sector)
join latest_price lp using (scrip)
order by ls.scrip
