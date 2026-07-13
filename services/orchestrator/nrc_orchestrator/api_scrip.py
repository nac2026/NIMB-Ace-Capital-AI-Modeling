"""Scrip-scoped dashboard endpoints.

One router, eleven GET endpoints under `/api/scrip/{symbol}/...`. Each
route is a direct Postgres SQL query against the serving tables
populated by `nrc_processing.sync_postgres`. No ToolResponse envelope —
dashboards want bulk data, not tool metadata.

Response shapes are Pydantic models so the frontend TypeScript wrappers
in services/web/src/lib/api.ts can be typed end-to-end. Every response
includes a `data_as_of` timestamp (when the serving table was last
synced) so the UI can render "last updated 2h ago" labels.

Serving-table dependencies per endpoint:
  summary              → scrips + daily_bars + market_cap_metrics +
                          quality_momentum_matrix + fundamental_quality_composite
  fundamentals-history → fundamental_snapshots + ttm_fundamentals +
                          quarterly_growth
  valuation-history    → valuation_history
  returns              → price_returns + total_shareholder_return + beta_and_volatility
  piotroski            → piotroski_f_score
  dupont               → dupont_decomposition
  asset-quality        → asset_quality_trends
  capital              → capital_strength
  dividends            → dividend_yield + corporate_actions
  technicals           → indicators_daily + technical_signal_summary
  quality              → fundamental_quality_composite"""
from __future__ import annotations
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from nrc_storage import PostgresClient

router = APIRouter(prefix="/api/scrip", tags=["scrip"])


# ============================================================= response models

class ScripSummary(BaseModel):
    """Header-strip data for the scrip detail page."""
    scrip: str
    company_name: str
    sector: str
    latest_close: float | None = None
    latest_date: date | None = None
    change_pct: float | None = None
    market_cap_npr: float | None = None
    market_cap_tier: str | None = None
    quadrant: str | None = None
    quality_score_0_100: float | None = None
    quality_tier: str | None = None
    week52_high: float | None = None
    week52_low: float | None = None


class ScripProfile(BaseModel):
    """Company-profile / Overview-tab data — identity, listing facts, the
    latest per-share snapshot and ownership where available.

    NOTE on coverage: the `scrips` master + market_cap + fundamentals give us
    sector, listing/capital facts and per-share metrics. We do NOT currently
    receive a shareholding breakdown (promoter/public/foreign) or qualitative
    profile fields (CEO, HQ, employees, description) from the SMTM feed — those
    are null and flagged `ownership_available=False` until the provider sends
    them (see the NEPSE data-request workbook)."""
    scrip: str
    company_name: str
    sector: str
    sub_sector: str | None = None
    # listing & capital facts
    listed_shares: float | None = None
    paid_up_value: float | None = None
    paid_up_capital: float | None = None
    registered_date: date | None = None
    shares_outstanding: float | None = None
    market_cap_npr: float | None = None
    market_cap_tier: str | None = None
    # latest per-share / valuation snapshot
    eps: float | None = None
    bvps: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    roe: float | None = None
    fiscal_year_bs: int | None = None
    quarter: int | None = None
    # income / dividend
    dividend_yield: float | None = None
    bonus_pct: float | None = None
    # ownership (best-effort; absent in current feed)
    promoter_pct: float | None = None
    public_pct: float | None = None
    ownership_available: bool = False
    data_as_of: Any | None = None


class FundamentalsHistoryRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    net_profit: float | None = None
    operating_profit: float | None = None
    net_interest_income: float | None = None
    roe: float | None = None
    roa: float | None = None
    npl_ratio: float | None = None
    car: float | None = None
    cd_ratio: float | None = None
    eps: float | None = None
    bvps: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    total_deposits: float | None = None
    total_loans: float | None = None
    # From ttm_fundamentals
    ttm_net_profit: float | None = None
    ttm_roe: float | None = None
    ttm_roa: float | None = None
    ttm_nim: float | None = None
    # From quarterly_growth
    net_profit_yoy_pct: float | None = None
    net_profit_qoq_pct: float | None = None
    total_operating_income_yoy_pct: float | None = None
    total_loans_yoy_pct: float | None = None
    total_deposits_yoy_pct: float | None = None


class ValuationHistoryRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    pe_self_pct_5y: float | None = None
    pb_self_pct_5y: float | None = None
    pe_self_pct_all: float | None = None
    self_valuation_tier: str | None = None


class ReturnsSnapshot(BaseModel):
    scrip: str
    as_of: date | None = None
    close: float | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None
    return_3y: float | None = None
    return_5y: float | None = None
    drawdown_from_peak: float | None = None
    realized_vol_20d: float | None = None
    position_in_20d_range: float | None = None
    # TSR adds dividends
    tsr_1y: float | None = None
    tsr_3y: float | None = None
    tsr_5y: float | None = None
    # Risk
    beta: float | None = None
    alpha_annual: float | None = None
    r_squared: float | None = None
    annualized_vol: float | None = None
    sharpe_ratio_2y: float | None = None


class PiotroskiRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    p1_positive_profit: int | None = None
    p2_positive_roa: int | None = None
    p3_profit_grew: int | None = None
    p4_roa_improved: int | None = None
    p5_npl_not_worse: int | None = None
    p6_car_not_worse: int | None = None
    p7_no_large_issuance: int | None = None
    p8_nim_improved: int | None = None
    p9_cti_improved: int | None = None
    f_score: int | None = None
    n_signals_available: int | None = None


class DupontRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    roe_computed: float | None = None
    roa: float | None = None
    equity_multiplier: float | None = None
    net_profit_margin: float | None = None
    asset_turnover: float | None = None
    tax_burden: float | None = None
    interest_burden: float | None = None
    operating_margin: float | None = None
    nim: float | None = None


class AssetQualityRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    npl_ratio: float | None = None
    llp_to_npl_ratio: float | None = None
    npl_qoq_change_abs: float | None = None
    npl_yoy_change_abs: float | None = None
    llp_coverage_yoy_change: float | None = None
    credit_loss_rate_ttm: float | None = None
    asset_quality_tier: str | None = None


class CapitalRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    car: float | None = None
    tier1_capital: float | None = None
    tier2_capital: float | None = None
    total_capital: float | None = None
    tier1_share: float | None = None
    car_buffer: float | None = None
    car_yoy_change: float | None = None
    capital_tier: str | None = None


class DividendRow(BaseModel):
    fiscal_year_bs: int
    annual_cash_div_pct: float | None = None
    annual_bonus_pct: float | None = None
    market_value_per_share: float | None = None
    cash_dividend_yield: float | None = None
    total_dividend_yield: float | None = None
    yield_tier: str | None = None


class CorporateActionRow(BaseModel):
    action_type: str
    ratio: float | None = None
    amount: float | None = None
    announcement_date: date | None = None
    fiscal_year_bs: int | None = None


class DividendsResponse(BaseModel):
    annual: list[DividendRow]
    actions: list[CorporateActionRow]


class TechnicalsSnapshot(BaseModel):
    scrip: str
    as_of: date | None = None
    close: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bollinger_upper: float | None = None
    bollinger_middle: float | None = None
    bollinger_lower: float | None = None
    atr_14: float | None = None
    # From technical_signal_summary — exposed individually, not as a verdict.
    r1_trend: int | None = None
    r2_ma_align: int | None = None
    r3_rsi: int | None = None
    r4_macd: int | None = None
    r5_bollinger: int | None = None
    signal_sum: int | None = None
    technical_signal: str | None = None  # available but UI shouldn't render as verdict


class QualityRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    profitability_pct: float | None = None
    asset_quality_pct: float | None = None
    growth_pct: float | None = None
    capital_pct: float | None = None
    efficiency_pct: float | None = None
    piotroski_pct: float | None = None
    quality_score_0_100: float | None = None
    quality_tier: str | None = None


# ============================================================== helpers

def _validate_scrip(scrip: str, pg: PostgresClient) -> str:
    """Uppercase the scrip + verify it's in the active universe."""
    scrip = scrip.strip().upper()
    row = pg.fetch_one("SELECT scrip FROM scrips WHERE scrip = %s", (scrip,))
    if row is None:
        raise HTTPException(404, f"Unknown scrip: {scrip}")
    return scrip


# ============================================================== endpoints

@router.get("/{scrip}/summary", response_model=ScripSummary)
def summary(scrip: str, request: Request) -> ScripSummary:
    """Header-strip data — single row stitched from ~5 Postgres tables."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    row = pg.fetch_one(
        """
        WITH latest_bar AS (
            SELECT scrip, date, close
            FROM daily_bars WHERE scrip = %s
            ORDER BY date DESC LIMIT 1
        ),
        prev_bar AS (
            SELECT close AS prev_close
            FROM daily_bars WHERE scrip = %s
            ORDER BY date DESC OFFSET 1 LIMIT 1
        ),
        week52 AS (
            SELECT MIN(close) AS lo, MAX(close) AS hi
            FROM daily_bars
            WHERE scrip = %s AND date >= (CURRENT_DATE - INTERVAL '365 days')
        )
        SELECT
            s.scrip, s.company_name, s.sector,
            lb.close AS latest_close, lb.date AS latest_date,
            CASE WHEN pb.prev_close > 0
                 THEN 100.0 * (lb.close - pb.prev_close) / pb.prev_close
                 ELSE NULL END AS change_pct,
            mc.market_cap_npr, mc.market_cap_tier,
            qmm.quadrant,
            fqc.quality_score_0_100, fqc.quality_tier,
            w.hi AS week52_high, w.lo AS week52_low
        FROM scrips s
        LEFT JOIN latest_bar lb ON TRUE
        LEFT JOIN prev_bar   pb ON TRUE
        LEFT JOIN week52     w  ON TRUE
        LEFT JOIN market_cap_metrics mc ON mc.scrip = s.scrip
        LEFT JOIN quality_momentum_matrix qmm ON qmm.scrip = s.scrip
        LEFT JOIN LATERAL (
            SELECT quality_score_0_100, quality_tier
            FROM fundamental_quality_composite
            WHERE scrip = s.scrip
            ORDER BY fiscal_year_bs DESC, quarter DESC
            LIMIT 1
        ) fqc ON TRUE
        WHERE s.scrip = %s
        """,
        (scrip, scrip, scrip, scrip),
    )
    if row is None:
        raise HTTPException(404, f"Scrip not found: {scrip}")
    return ScripSummary(**row)


@router.get("/{scrip}/profile", response_model=ScripProfile)
def profile(scrip: str, request: Request) -> ScripProfile:
    """Company-profile / Overview-tab data — identity + listing/capital facts
    (scrips master), market cap (market_cap_metrics), the latest per-share
    snapshot (fundamental_snapshots) and latest dividend yield. Stitched in one
    query so the Overview tab needs a single request."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    row = pg.fetch_one(
        """
        SELECT
            s.scrip, s.company_name, s.sector, s.sub_sector,
            s.listed_shares, s.paid_up_value, s.paid_up_capital, s.registered_date,
            mc.shares_outstanding, mc.market_cap_npr, mc.market_cap_tier,
            f.eps, f.bvps, f.pe_ratio, f.pb_ratio, f.roe,
            f.fiscal_year_bs, f.quarter,
            d.total_dividend_yield AS dividend_yield, d.annual_bonus_pct AS bonus_pct
        FROM scrips s
        LEFT JOIN market_cap_metrics mc ON mc.scrip = s.scrip
        LEFT JOIN LATERAL (
            SELECT eps, bvps, pe_ratio, pb_ratio, roe, fiscal_year_bs, quarter
            FROM fundamental_snapshots
            WHERE scrip = s.scrip
            ORDER BY fiscal_year_bs DESC, quarter DESC
            LIMIT 1
        ) f ON TRUE
        LEFT JOIN LATERAL (
            SELECT total_dividend_yield, annual_bonus_pct
            FROM dividend_yield
            WHERE scrip = s.scrip
            ORDER BY fiscal_year_bs DESC
            LIMIT 1
        ) d ON TRUE
        WHERE s.scrip = %s
        """,
        (scrip,),
    )
    if row is None:
        raise HTTPException(404, f"Scrip not found: {scrip}")
    return ScripProfile(ownership_available=False, data_as_of=datetime.now(), **row)


@router.get("/{scrip}/fundamentals-history", response_model=list[FundamentalsHistoryRow])
def fundamentals_history(scrip: str, request: Request, quarters: int = 20) -> list[FundamentalsHistoryRow]:
    """Aligned fundamentals + TTM + growth over the last N quarters."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    rows = pg.fetch_all(
        """
        SELECT
            fs.fiscal_year_bs, fs.quarter,
            fs.net_profit, fs.operating_profit, fs.net_interest_income,
            fs.roe, fs.roa, fs.npl_ratio, fs.car, fs.cd_ratio,
            fs.eps, fs.bvps, fs.pe_ratio, fs.pb_ratio,
            fs.total_deposits, fs.total_loans,
            ttm.ttm_net_profit, ttm.ttm_roe, ttm.ttm_roa, ttm.ttm_nim,
            qg.net_profit_yoy_pct, qg.net_profit_qoq_pct,
            qg.total_operating_income_yoy_pct,
            qg.total_loans_yoy_pct, qg.total_deposits_yoy_pct
        FROM fundamental_snapshots fs
        LEFT JOIN ttm_fundamentals ttm
               USING (scrip, fiscal_year_bs, quarter)
        LEFT JOIN quarterly_growth qg
               USING (scrip, fiscal_year_bs, quarter)
        WHERE fs.scrip = %s
        ORDER BY fs.fiscal_year_bs DESC, fs.quarter DESC
        LIMIT %s
        """,
        (scrip, quarters),
    )
    rows.reverse()  # chronological for charting
    return [FundamentalsHistoryRow(**r) for r in rows]


@router.get("/{scrip}/valuation-history", response_model=list[ValuationHistoryRow])
def valuation_history(scrip: str, request: Request, quarters: int = 20) -> list[ValuationHistoryRow]:
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    rows = pg.fetch_all(
        """
        SELECT fiscal_year_bs, quarter, pe_ratio, pb_ratio,
               pe_self_pct_5y, pb_self_pct_5y, pe_self_pct_all,
               self_valuation_tier
        FROM valuation_history
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC, quarter DESC
        LIMIT %s
        """,
        (scrip, quarters),
    )
    rows.reverse()
    return [ValuationHistoryRow(**r) for r in rows]


@router.get("/{scrip}/returns", response_model=ReturnsSnapshot)
def returns(scrip: str, request: Request) -> ReturnsSnapshot:
    """Latest-snapshot returns, TSR, and market-risk metrics in one stitch."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    row = pg.fetch_one(
        """
        SELECT
            pr.scrip, pr.as_of, pr.close,
            pr.return_1m, pr.return_3m, pr.return_6m,
            pr.return_1y, pr.return_3y, pr.return_5y,
            pr.drawdown_from_peak, pr.realized_vol_20d, pr.position_in_20d_range,
            tsr.tsr_1y, tsr.tsr_3y, tsr.tsr_5y,
            bv.beta, bv.alpha_annual, bv.r_squared,
            bv.annualized_vol, bv.sharpe_ratio_2y
        FROM scrips s
        LEFT JOIN price_returns pr                 ON pr.scrip  = s.scrip
        LEFT JOIN total_shareholder_return tsr     ON tsr.scrip = s.scrip
        LEFT JOIN beta_and_volatility bv           ON bv.scrip  = s.scrip
        WHERE s.scrip = %s
        """,
        (scrip,),
    )
    if row is None:
        raise HTTPException(404, f"Scrip not found: {scrip}")
    # price_returns has no data for SCB; fall back to name-only row.
    row["scrip"] = scrip
    return ReturnsSnapshot(**row)


@router.get("/{scrip}/piotroski", response_model=list[PiotroskiRow])
def piotroski(scrip: str, request: Request, quarters: int = 20) -> list[PiotroskiRow]:
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    rows = pg.fetch_all(
        """
        SELECT fiscal_year_bs, quarter,
               p1_positive_profit, p2_positive_roa, p3_profit_grew,
               p4_roa_improved,    p5_npl_not_worse, p6_car_not_worse,
               p7_no_large_issuance, p8_nim_improved, p9_cti_improved,
               f_score, n_signals_available
        FROM piotroski_f_score
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC, quarter DESC
        LIMIT %s
        """,
        (scrip, quarters),
    )
    rows.reverse()
    return [PiotroskiRow(**r) for r in rows]


@router.get("/{scrip}/dupont", response_model=list[DupontRow])
def dupont(scrip: str, request: Request, quarters: int = 20) -> list[DupontRow]:
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    rows = pg.fetch_all(
        """
        SELECT fiscal_year_bs, quarter,
               roe_computed, roa, equity_multiplier,
               net_profit_margin, asset_turnover,
               tax_burden, interest_burden, operating_margin, nim
        FROM dupont_decomposition
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC, quarter DESC
        LIMIT %s
        """,
        (scrip, quarters),
    )
    rows.reverse()
    return [DupontRow(**r) for r in rows]


@router.get("/{scrip}/asset-quality", response_model=list[AssetQualityRow])
def asset_quality(scrip: str, request: Request, quarters: int = 20) -> list[AssetQualityRow]:
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    rows = pg.fetch_all(
        """
        SELECT fiscal_year_bs, quarter,
               npl_ratio, llp_to_npl_ratio,
               npl_qoq_change_abs, npl_yoy_change_abs, llp_coverage_yoy_change,
               credit_loss_rate_ttm, asset_quality_tier
        FROM asset_quality_trends
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC, quarter DESC
        LIMIT %s
        """,
        (scrip, quarters),
    )
    rows.reverse()
    return [AssetQualityRow(**r) for r in rows]


@router.get("/{scrip}/capital", response_model=list[CapitalRow])
def capital(scrip: str, request: Request, quarters: int = 20) -> list[CapitalRow]:
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    rows = pg.fetch_all(
        """
        SELECT fiscal_year_bs, quarter,
               car, tier1_capital, tier2_capital, total_capital,
               tier1_share, car_buffer, car_yoy_change, capital_tier
        FROM capital_strength
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC, quarter DESC
        LIMIT %s
        """,
        (scrip, quarters),
    )
    rows.reverse()
    return [CapitalRow(**r) for r in rows]


@router.get("/{scrip}/dividends", response_model=DividendsResponse)
def dividends(scrip: str, request: Request) -> DividendsResponse:
    """Annual yield table + raw cash-dividend / bonus event log."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    annual = pg.fetch_all(
        """
        SELECT fiscal_year_bs,
               annual_cash_div_pct, annual_bonus_pct,
               market_value_per_share,
               cash_dividend_yield, total_dividend_yield, yield_tier
        FROM dividend_yield
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC
        """,
        (scrip,),
    )
    actions = pg.fetch_all(
        """
        SELECT action_type, ratio, amount, announcement_date, fiscal_year_bs
        FROM corporate_actions
        WHERE scrip = %s
        ORDER BY announcement_date DESC NULLS LAST
        """,
        (scrip,),
    )
    return DividendsResponse(
        annual=[DividendRow(**r) for r in annual],
        actions=[CorporateActionRow(**r) for r in actions],
    )


@router.get("/{scrip}/technicals", response_model=TechnicalsSnapshot)
def technicals(scrip: str, request: Request) -> TechnicalsSnapshot:
    """Latest indicator values + the 5-rule technical-posture breakdown."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    row = pg.fetch_one(
        """
        WITH latest_ind AS (
            SELECT * FROM indicators_daily
            WHERE scrip = %s
            ORDER BY date DESC LIMIT 1
        )
        SELECT
            li.scrip, li.date AS as_of, li.close,
            li.sma_20, li.sma_50, li.sma_200,
            li.ema_12, li.ema_26, li.rsi_14,
            li.macd, li.macd_signal, li.macd_histogram,
            li.bollinger_upper, li.bollinger_middle, li.bollinger_lower,
            li.atr_14,
            tss.r1_trend, tss.r2_ma_align, tss.r3_rsi, tss.r4_macd, tss.r5_bollinger,
            tss.signal_sum, tss.technical_signal
        FROM latest_ind li
        LEFT JOIN technical_signal_summary tss ON tss.scrip = li.scrip
        """,
        (scrip,),
    )
    if row is None:
        # Return a skeleton so the UI can render an empty state cleanly.
        return TechnicalsSnapshot(scrip=scrip)
    return TechnicalsSnapshot(**row)


@router.get("/{scrip}/quality", response_model=list[QualityRow])
def quality(scrip: str, request: Request, quarters: int = 20) -> list[QualityRow]:
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)
    rows = pg.fetch_all(
        """
        SELECT fiscal_year_bs, quarter,
               profitability_pct, asset_quality_pct, growth_pct,
               capital_pct, efficiency_pct, piotroski_pct,
               quality_score_0_100, quality_tier
        FROM fundamental_quality_composite
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC, quarter DESC
        LIMIT %s
        """,
        (scrip, quarters),
    )
    rows.reverse()
    return [QualityRow(**r) for r in rows]


# ===================================================== floor-sheet / broker flow

class BrokerConcentrationDay(BaseModel):
    trade_date: date
    n_brokers: int | None = None
    hhi_buy: float | None = None
    hhi_sell: float | None = None
    top1_buy_share: float | None = None
    top3_buy_share: float | None = None
    top1_sell_share: float | None = None
    top3_sell_share: float | None = None
    concentration_flag: bool | None = None


class BrokerPositionRow(BaseModel):
    broker: int
    cum_net_qty: float | None = None
    volume_share: float | None = None
    days_net_buy: int | None = None
    days_active: int | None = None
    accumulation_flag: bool | None = None
    distribution_flag: bool | None = None
    # Position-phase trajectory (from broker_position).
    phase: str | None = None                 # accumulating | distributing | flat
    accum_start_date: date | None = None
    peak_date: date | None = None
    dist_start_date: date | None = None
    days_since_peak: int | None = None


class TimelinePoint(BaseModel):
    date: date
    cum_net_qty: float | None = None


class BrokerTimeline(BaseModel):
    broker: int
    points: list[TimelinePoint] = []


class SpeculationRow(BaseModel):
    speculation_score: float | None = None
    speculation_tier: str | None = None
    c_concentration: float | None = None
    c_control: float | None = None
    c_circular: float | None = None
    c_accumulation: float | None = None
    c_block: float | None = None
    has_self_trade: int | None = None


class FloorsheetResponse(BaseModel):
    scrip: str
    speculation: SpeculationRow | None = None
    concentration_recent: list[BrokerConcentrationDay] = []
    top_accumulators: list[BrokerPositionRow] = []
    top_distributors: list[BrokerPositionRow] = []
    position_timeline: list[BrokerTimeline] = []
    data_as_of: datetime | None = None


@router.get("/{scrip}/floorsheet", response_model=FloorsheetResponse)
def floorsheet(scrip: str, request: Request, days: int = 15, top_n: int = 5) -> FloorsheetResponse:
    """Broker-flow microstructure: speculation score, daily concentration, and
    the top accumulating/distributing brokers. Empty (not 404) for scrips with
    no floor-sheet yet."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)

    spec = pg.fetch_one(
        """SELECT speculation_score, speculation_tier, c_concentration, c_control,
                  c_circular, c_accumulation, c_block, has_self_trade, computed_at
           FROM speculation_score WHERE scrip = %s""",
        (scrip,),
    )
    conc = pg.fetch_all(
        """SELECT trade_date, n_brokers, hhi_buy, hhi_sell,
                  top1_buy_share, top3_buy_share, top1_sell_share, top3_sell_share,
                  concentration_flag
           FROM broker_concentration_daily WHERE scrip = %s
           ORDER BY trade_date DESC LIMIT %s""",
        (scrip, days),
    )
    cols = (
        "ba.broker, ba.cum_net_qty, ba.volume_share, ba.days_net_buy, ba.days_active, "
        "ba.accumulation_flag, ba.distribution_flag, "
        "bp.phase, bp.accum_start_date, bp.peak_date, bp.dist_start_date, bp.days_since_peak"
    )
    base = (
        f"SELECT {cols} FROM broker_accumulation ba "
        "LEFT JOIN broker_position bp ON bp.scrip = ba.scrip AND bp.broker = ba.broker "
        "WHERE ba.scrip = %s ORDER BY ba.cum_net_qty {dir} LIMIT %s"
    )
    accs = pg.fetch_all(base.format(dir="DESC"), (scrip, top_n))
    dists = pg.fetch_all(base.format(dir="ASC"), (scrip, top_n))

    # Position-over-time series for the top 3 accumulators + 3 distributors.
    chart_brokers = [r["broker"] for r in accs[:3]] + [r["broker"] for r in dists[:3]]
    timeline: list[BrokerTimeline] = []
    if chart_brokers:
        tl_rows = pg.fetch_all(
            """SELECT broker, trade_date AS date, cum_net_qty
               FROM broker_position_timeline
               WHERE scrip = %s AND broker = ANY(%s)
               ORDER BY broker, trade_date""",
            (scrip, chart_brokers),
        )
        by_broker: dict[int, list] = {}
        for r in tl_rows:
            by_broker.setdefault(r["broker"], []).append(TimelinePoint(date=r["date"], cum_net_qty=r["cum_net_qty"]))
        # preserve the accumulator-then-distributor order
        seen: set[int] = set()
        for b in chart_brokers:
            if b in by_broker and b not in seen:
                seen.add(b)
                timeline.append(BrokerTimeline(broker=b, points=by_broker[b]))

    return FloorsheetResponse(
        scrip=scrip,
        speculation=SpeculationRow(**spec) if spec else None,
        concentration_recent=[BrokerConcentrationDay(**c) for c in conc],
        top_accumulators=[BrokerPositionRow(**a) for a in accs],
        top_distributors=[BrokerPositionRow(**d) for d in dists],
        position_timeline=timeline,
        data_as_of=(spec["computed_at"] if spec else None),
    )


# ===================================================== news & sentiment

class NewsItem(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_at: datetime | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    summary: str | None = None
    event_type: str | None = None


class NewsSentimentResponse(BaseModel):
    scrip: str
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    n_articles: int = 0
    bullish_count: int = 0
    neutral_count: int = 0
    bearish_count: int = 0
    latest_published_at: datetime | None = None
    articles: list[NewsItem] = []


@router.get("/{scrip}/news-sentiment", response_model=NewsSentimentResponse)
def news_sentiment(scrip: str, request: Request, limit: int = 20) -> NewsSentimentResponse:
    """Ambient news sentiment for the company-360 News panel: the scrip's
    sentiment rollup + recent enriched, scrip-tagged articles."""
    pg: PostgresClient = request.app.state.pg
    scrip = _validate_scrip(scrip, pg)

    roll = pg.fetch_one(
        """SELECT sentiment_label, sentiment_score, n_articles,
                  bullish_count, neutral_count, bearish_count, latest_published_at
           FROM scrip_sentiment WHERE scrip = %s""",
        (scrip,),
    )
    arts = pg.fetch_all(
        """SELECT title, url, source, published_at, sentiment, sentiment_score,
                  summary, event_type
           FROM news_articles
           WHERE %s = ANY(scrip_tags) AND enriched_at IS NOT NULL
           ORDER BY published_at DESC LIMIT %s""",
        (scrip, limit),
    )
    return NewsSentimentResponse(
        scrip=scrip,
        sentiment_label=(roll["sentiment_label"] if roll else None),
        sentiment_score=(roll["sentiment_score"] if roll else None),
        n_articles=(roll["n_articles"] if roll else 0),
        bullish_count=(roll["bullish_count"] if roll else 0),
        neutral_count=(roll["neutral_count"] if roll else 0),
        bearish_count=(roll["bearish_count"] if roll else 0),
        latest_published_at=(roll["latest_published_at"] if roll else None),
        articles=[NewsItem(**a) for a in arts],
    )
