{# -
    gold.asset_quality_trends — NPL trajectory + provision coverage +
    credit-loss rate, all with YoY deltas.

    Asset quality is the #1 driver of bank solvency risk. Analysts care
    about DIRECTION more than level — a bank with 4% NPL that's rising
    is worse than one at 5% that's falling.

    Columns computed:
      * npl_ratio, llp_to_npl_ratio — current values
      * npl_yoy_change_abs — absolute YoY change in NPL (pct points)
      * npl_qoq_change_abs — absolute QoQ change (noisier but faster)
      * credit_loss_rate_ttm — impairment charge TTM / total loans
      * asset_quality_tier — bucketed classification

    Feeds research Q3 "Revenue and profit growth trend" (via the
    impairment drag), Q12 "Quarterly financial deviation check" (for
    NPL spikes), and the fundamental_quality_composite's asset-quality
    component.
- #}
{{
    config(
        location=gold_external_location(),
        description='NPL trajectory, LLP coverage, credit-loss rate trends.',
    )
}}

with base as (
    select
        fs.scrip,
        fs.fiscal_year_bs,
        fs.quarter,
        fs.npl_ratio,
        fs.total_loans,
        fs.impairment_charge,
        -- additional_info's llp_to_npl_ratio is authoritative; falls
        -- back to NULL if the row isn't in Shreyas' additional-info set.
        ai.llp_to_npl_ratio
    from {{ source('silver', 'fundamentals_snapshots') }} fs
    left join {{ source('silver', 'additional_info') }}  ai using (scrip, fiscal_year_bs, quarter)
),

with_context as (
    select
        *,
        lag(npl_ratio, 1)         over w as npl_qoq_prev,
        lag(npl_ratio, 4)         over w as npl_yoy_prev,
        lag(llp_to_npl_ratio, 4)  over w as llp_yoy_prev,
        -- Impairment charge is a flow; TTM sum gives an annualized
        -- credit-loss view that's less noisy than a single quarter.
        sum(impairment_charge) over w4 as impairment_ttm,
        count(*) over w4               as n_q_in_ttm
    from base
    window
        w  as (partition by scrip order by fiscal_year_bs, quarter),
        w4 as (partition by scrip order by fiscal_year_bs, quarter rows between 3 preceding and current row)
)

select
    scrip,
    fiscal_year_bs,
    quarter,
    npl_ratio,
    llp_to_npl_ratio,
    -- Trajectory signals.
    npl_ratio - npl_qoq_prev        as npl_qoq_change_abs,
    npl_ratio - npl_yoy_prev        as npl_yoy_change_abs,
    llp_to_npl_ratio - llp_yoy_prev as llp_coverage_yoy_change,
    -- Annualized credit-loss rate — only emit when TTM window is full.
    case
        when n_q_in_ttm = 4
        then impairment_ttm * 1.0 / nullif(total_loans, 0)
    end as credit_loss_rate_ttm,
    -- Bucketed quality tier for dashboard chips / filters. Thresholds
    -- decimal-form: 3% / 5% NPL; coverage expressed as 1.0 = 100%.
    case
        when npl_ratio is null or llp_to_npl_ratio is null  then null
        when npl_ratio < 0.03 and llp_to_npl_ratio >= 1.00  then 'STRONG'
        when npl_ratio < 0.05 and llp_to_npl_ratio >= 0.80  then 'MODERATE'
        when npl_ratio >= 0.05 or  llp_to_npl_ratio < 0.80  then 'WEAK'
    end                               as asset_quality_tier,
    current_timestamp                 as computed_at
from with_context
order by scrip, fiscal_year_bs, quarter
