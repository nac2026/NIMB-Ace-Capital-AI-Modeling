"""Read-only data endpoints for the web UI dashboard.

These are intentionally plain SQL (not the tool layer) — the tool layer
exists for LLM use and returns ToolResponse[T] envelopes. Dashboards need
bulk rows, not tool envelopes, so it's cleaner to keep them separate."""
from __future__ import annotations
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nrc_storage import PostgresClient

router = APIRouter(prefix="/api", tags=["data"])


# ----------------------------------------------------------------- models
class UniverseRow(BaseModel):
    """One row of the 19-active-bank dashboard grid.

    Original stage-2 columns stay for chat/screen-preset reuse; the Phase I+J
    fields (suffix below) feed the redesigned dashboard's extra columns and
    filter chips without needing a second request per scrip."""
    scrip: str
    company_name: str
    sector: str
    latest_close: float | None = None
    latest_date: date | None = None
    change_pct: float | None = None
    roe: float | None = None
    npl_ratio: float | None = None
    car: float | None = None
    cd_ratio: float | None = None
    pe_ratio: float | None = None
    composite_score: float | None = None
    flags: list[str] = []
    # Phase I+J enrichments
    scorecard_0_100: float | None = None
    quality_score_0_100: float | None = None
    quality_tier: str | None = None
    quadrant: str | None = None
    return_6m: float | None = None
    self_valuation_tier: str | None = None
    total_dividend_yield: float | None = None
    yield_tier: str | None = None
    market_cap_npr: float | None = None
    market_cap_tier: str | None = None


class IndexRow(BaseModel):
    index_name: str
    date: date
    close: float
    change: float | None = None
    percent_change: float | None = None
    turnover: float | None = None


# -------------------------------------------------------------- endpoints
@router.get("/universe", response_model=list[UniverseRow])
def universe(request: Request) -> list[UniverseRow]:
    """Everything the dashboard grid needs about active banks in one shot."""
    pg: PostgresClient = request.app.state.pg
    # Joins: scrips (names) + latest daily_bars + latest fundamentals + stage2 score/flags.
    rows = pg.fetch_all("""
        WITH latest_bar AS (
            SELECT DISTINCT ON (scrip) scrip, date, close
            FROM daily_bars
            ORDER BY scrip, date DESC
        ),
        prev_bar AS (
            SELECT scrip, close AS prev_close
            FROM (
                SELECT scrip, close,
                       ROW_NUMBER() OVER (PARTITION BY scrip ORDER BY date DESC) AS rn
                FROM daily_bars
            ) x
            WHERE rn = 2
        ),
        latest_snap AS (
            SELECT DISTINCT ON (scrip) scrip, roe, npl_ratio, car, cd_ratio, pe_ratio
            FROM fundamental_snapshots
            ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
        ),
        latest_s2 AS (
            SELECT DISTINCT ON (scrip) scrip, composite_score, flags
            FROM stage2_bank_screen
            ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
        ),
        latest_val AS (
            SELECT DISTINCT ON (scrip) scrip, self_valuation_tier
            FROM valuation_history
            ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
        ),
        latest_div AS (
            SELECT DISTINCT ON (scrip) scrip, total_dividend_yield, yield_tier
            FROM dividend_yield
            ORDER BY scrip, fiscal_year_bs DESC
        )
        SELECT
            s.scrip, s.company_name, s.sector,
            lb.close        AS latest_close,
            lb.date         AS latest_date,
            CASE WHEN pb.prev_close > 0
                 THEN 100.0 * (lb.close - pb.prev_close) / pb.prev_close
                 ELSE NULL END                   AS change_pct,
            ls.roe, ls.npl_ratio, ls.car, ls.cd_ratio, ls.pe_ratio,
            s2.composite_score, s2.flags,
            sc.scorecard_0_100,
            qm.quality_score_0_100, qm.quality_tier, qm.quadrant, qm.return_6m,
            lv.self_valuation_tier,
            ld.total_dividend_yield, ld.yield_tier,
            mc.market_cap_npr, mc.market_cap_tier
        FROM scrips s
        LEFT JOIN latest_bar           lb ON lb.scrip = s.scrip
        LEFT JOIN prev_bar             pb ON pb.scrip = s.scrip
        LEFT JOIN latest_snap          ls ON ls.scrip = s.scrip
        LEFT JOIN latest_s2            s2 ON s2.scrip = s.scrip
        LEFT JOIN investment_scorecard sc ON sc.scrip = s.scrip
        LEFT JOIN quality_momentum_matrix qm ON qm.scrip = s.scrip
        LEFT JOIN latest_val           lv ON lv.scrip = s.scrip
        LEFT JOIN latest_div           ld ON ld.scrip = s.scrip
        LEFT JOIN market_cap_metrics   mc ON mc.scrip = s.scrip
        WHERE s.is_active
        ORDER BY s.scrip
    """)
    return [UniverseRow(**{**r, "flags": list(r["flags"] or [])}) for r in rows]


@router.get("/indices", response_model=list[IndexRow])
def indices(request: Request) -> list[IndexRow]:
    """Latest NEPSE + BANKING index snapshot."""
    pg: PostgresClient = request.app.state.pg
    # Only the most recent snapshot day — SMTM `indices-live` now refreshes the
    # whole set daily, so restricting to max(date) drops stale rows left over
    # from the retired scraper feed (which also used different name casing).
    rows = pg.fetch_all("""
        SELECT DISTINCT ON (index_name)
               index_name, date, close, change, percent_change, turnover
        FROM index_snapshots
        WHERE date = (SELECT max(date) FROM index_snapshots)
        ORDER BY index_name, date DESC
    """)
    # NEPSE first, then the rest alphabetically — the UI keys off it.
    rows.sort(key=lambda r: (0 if r["index_name"].strip().upper() == "NEPSE" else 1, r["index_name"]))
    return [IndexRow(**r) for r in rows]


class Stage2Row(BaseModel):
    scrip: str
    sector: str | None
    composite_score: float
    roe: float | None
    roa: float | None
    net_margin: float | None
    npl_ratio: float | None
    car: float | None
    cd_ratio: float | None
    flags: list[str]


@router.get("/stage2", response_model=list[Stage2Row])
def stage2(request: Request) -> list[Stage2Row]:
    """Stage-2 sector-aware deep screen — latest quarter, sorted best-first."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all("""
        SELECT DISTINCT ON (scrip) scrip, sector, composite_score, roe, roa, net_margin,
               npl_ratio, car, cd_ratio, flags
        FROM stage2_bank_screen
        ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
    """)
    # Sort in Python to avoid a second DISTINCT ON pass.
    rows.sort(key=lambda r: r["composite_score"] or 0, reverse=True)
    return [Stage2Row(**{**r, "flags": list(r["flags"] or [])}) for r in rows]


class PricePoint(BaseModel):
    date: date
    close: float


@router.get("/prices/{scrip}", response_model=list[PricePoint])
def prices(scrip: str, request: Request, days: int = 90) -> list[PricePoint]:
    """Last `days` of closes for one scrip — for the mini chart on hover/select."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        """
        SELECT date, close FROM daily_bars
        WHERE scrip = %s
        ORDER BY date DESC
        LIMIT %s
        """,
        (scrip.upper(), days),
    )
    rows.reverse()  # chronological for the chart
    return [PricePoint(**r) for r in rows]


@router.get("/universe/sparklines")
def universe_sparklines(request: Request, days: int = 30) -> dict[str, list[float]]:
    """Bulk last-N closes for every active scrip — lets the universe table
    render 19 sparklines with one round-trip instead of 19 serial /prices
    calls. Returned shape: {scrip: [close, close, ...]} chronological."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        """
        WITH ranked AS (
            SELECT scrip, date, close,
                   ROW_NUMBER() OVER (PARTITION BY scrip ORDER BY date DESC) AS rn
            FROM daily_bars
            WHERE scrip IN (SELECT scrip FROM scrips WHERE is_active)
        )
        SELECT scrip, date, close
        FROM ranked
        WHERE rn <= %s
        ORDER BY scrip, date ASC
        """,
        (days,),
    )
    out: dict[str, list[float]] = {}
    for r in rows:
        out.setdefault(r["scrip"], []).append(float(r["close"]))
    return out


# ============================================================ Phase I+J tables

class ScorecardRow(BaseModel):
    scrip: str
    sector: str | None = None
    quality_pct: float | None = None
    valuation_pct: float | None = None
    momentum_pct: float | None = None
    risk_pct: float | None = None
    income_pct: float | None = None
    quality_score_0_100: float | None = None
    scorecard_0_100: float | None = None
    # `recommendation` is in the Postgres table but deliberately absent from
    # this response model. Analysts don't want BUY/SELL chips in the UI;
    # chat tools can still read it from Postgres when needed.


@router.get("/scorecard", response_model=list[ScorecardRow])
def scorecard(request: Request) -> list[ScorecardRow]:
    """Full universe investment scorecard — 5 component percentiles +
    0-100 composite. No recommendation label in the response."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        """
        SELECT scrip, sector,
               quality_pct, valuation_pct, momentum_pct, risk_pct, income_pct,
               quality_score_0_100, scorecard_0_100
        FROM investment_scorecard
        ORDER BY scorecard_0_100 DESC NULLS LAST
        """
    )
    return [ScorecardRow(**r) for r in rows]


class QuadrantRow(BaseModel):
    scrip: str
    sector: str | None = None
    quality_score_0_100: float | None = None
    quality_tier: str | None = None
    return_6m: float | None = None
    quadrant: str | None = None
    sector_quality_median: float | None = None
    sector_return_6m_median: float | None = None


@router.get("/quadrant", response_model=list[QuadrantRow])
def quadrant(request: Request) -> list[QuadrantRow]:
    """Quality × 6-month momentum matrix — one row per active scrip."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        """
        SELECT scrip, sector,
               quality_score_0_100, quality_tier,
               return_6m, quadrant,
               sector_quality_median, sector_return_6m_median
        FROM quality_momentum_matrix
        ORDER BY quality_score_0_100 DESC NULLS LAST
        """
    )
    return [QuadrantRow(**r) for r in rows]


class SectorMomentumRow(BaseModel):
    sector: str
    n_scrips: int | None = None
    avg_return_3m: float | None = None
    avg_return_6m: float | None = None
    avg_return_1y: float | None = None
    median_return_6m: float | None = None
    return_6m_dispersion: float | None = None
    rank_by_6m: int | None = None
    momentum_tier: str | None = None


@router.get("/sector-momentum", response_model=list[SectorMomentumRow])
def sector_momentum(request: Request) -> list[SectorMomentumRow]:
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        """
        SELECT sector, n_scrips,
               avg_return_3m, avg_return_6m, avg_return_1y,
               median_return_6m, return_6m_dispersion,
               rank_by_6m, momentum_tier
        FROM sector_momentum
        ORDER BY rank_by_6m NULLS LAST
        """
    )
    return [SectorMomentumRow(**r) for r in rows]


# ----------------------------------------------------- market pulse (live intel)
class PulseScore(BaseModel):
    scrip: str
    company_name: str | None = None
    sector: str | None = None
    value: float | None = None
    tier: str | None = None
    extra: str | None = None


class MarketPulse(BaseModel):
    """Distinctive live-intel widgets for the dashboard: news sentiment breadth,
    speculation/manipulation alerts, broker accumulation, sentiment movers.
    All scrip-level lists JOIN `scrips`, so the equity universe only (no funds)."""
    sentiment_bullish: int = 0
    sentiment_neutral: int = 0
    sentiment_bearish: int = 0
    sentiment_avg: float | None = None
    speculation_alerts: list[PulseScore] = []
    broker_accumulation: list[PulseScore] = []
    bullish_movers: list[PulseScore] = []
    bearish_movers: list[PulseScore] = []


@router.get("/market-pulse", response_model=MarketPulse)
def market_pulse(request: Request, limit: int = 6) -> MarketPulse:
    pg: PostgresClient = request.app.state.pg

    sent = pg.fetch_one(
        """
        SELECT count(*) FILTER (WHERE ss.sentiment_label='BULLISH') AS bull,
               count(*) FILTER (WHERE ss.sentiment_label='NEUTRAL') AS neu,
               count(*) FILTER (WHERE ss.sentiment_label='BEARISH') AS bear,
               avg(ss.sentiment_score) AS avg_score
        FROM scrip_sentiment ss JOIN scrips s USING (scrip) WHERE s.is_active
        """
    ) or {}

    spec = pg.fetch_all(
        """
        SELECT sp.scrip, s.company_name, s.sector,
               sp.speculation_score AS value, sp.speculation_tier AS tier
        FROM speculation_score sp JOIN scrips s USING (scrip)
        WHERE s.is_active AND sp.speculation_tier IN ('HIGH','ELEVATED')
        ORDER BY sp.speculation_score DESC LIMIT %s
        """,
        (limit,),
    )
    accum = pg.fetch_all(
        """
        SELECT ba.scrip, s.company_name, s.sector,
               ba.volume_share AS value, ('broker #' || ba.broker) AS extra
        FROM broker_accumulation ba JOIN scrips s USING (scrip)
        WHERE s.is_active AND ba.accumulation_flag
        ORDER BY ba.volume_share DESC LIMIT %s
        """,
        (limit,),
    )
    bull = pg.fetch_all(
        """SELECT ss.scrip, s.company_name, s.sector, ss.sentiment_score AS value,
                  ss.sentiment_label AS tier
           FROM scrip_sentiment ss JOIN scrips s USING (scrip)
           WHERE s.is_active AND ss.n_articles >= 2
           ORDER BY ss.sentiment_score DESC LIMIT %s""",
        (limit,),
    )
    bear = pg.fetch_all(
        """SELECT ss.scrip, s.company_name, s.sector, ss.sentiment_score AS value,
                  ss.sentiment_label AS tier
           FROM scrip_sentiment ss JOIN scrips s USING (scrip)
           WHERE s.is_active AND ss.n_articles >= 2
           ORDER BY ss.sentiment_score ASC LIMIT %s""",
        (limit,),
    )
    return MarketPulse(
        sentiment_bullish=sent.get("bull", 0) or 0,
        sentiment_neutral=sent.get("neu", 0) or 0,
        sentiment_bearish=sent.get("bear", 0) or 0,
        sentiment_avg=sent.get("avg_score"),
        speculation_alerts=[PulseScore(**r) for r in spec],
        broker_accumulation=[PulseScore(**r) for r in accum],
        bullish_movers=[PulseScore(**r) for r in bull],
        bearish_movers=[PulseScore(**r) for r in bear],
    )


class MarketNewsItem(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_at: Any | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    summary: str | None = None
    event_type: str | None = None
    scrip_tags: list[str] = []
    sector_tags: list[str] = []


@router.get("/market-news", response_model=list[MarketNewsItem])
def market_news(request: Request, limit: int = 18) -> list[MarketNewsItem]:
    """Latest market-wide enriched headlines for the dashboard News Impact
    Timeline — across all scrips/sectors, newest first."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        """SELECT title, url, source, published_at, sentiment, sentiment_score,
                  summary, event_type, scrip_tags, sector_tags
           FROM news_articles
           WHERE enriched_at IS NOT NULL
           ORDER BY published_at DESC LIMIT %s""",
        (limit,),
    )
    return [MarketNewsItem(**r) for r in rows]
