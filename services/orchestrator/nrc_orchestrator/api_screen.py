"""Pre-built screen endpoints.

Five hard-coded filter presets backed by the serving-layer Gold tables.
Each returns the same `UniverseRow` shape as `/api/universe` so the
frontend can reuse the universe table component.

Rationale for presets vs. filter-builder: NIMB research analysts have
a handful of recurring "find me X" questions that deserve one-click
access. A full filter-builder UI (metric + operator + value) is the
right long-term answer but not required for the first milestone."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nrc_storage import PostgresClient

from .api_data import UniverseRow

router = APIRouter(prefix="/api/screen", tags=["screen"])


_BASE_SELECT = """
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
    ) x WHERE rn = 2
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
latest_fqc AS (
    SELECT DISTINCT ON (scrip) scrip, quality_score_0_100, quality_tier
    FROM fundamental_quality_composite
    ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
),
latest_pio AS (
    SELECT DISTINCT ON (scrip) scrip, f_score, fiscal_year_bs, quarter
    FROM piotroski_f_score
    ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
),
prev_pio AS (
    -- F-score 4 quarters (1 year) earlier — for YoY improvement detection.
    SELECT DISTINCT ON (scrip) scrip, f_score AS f_score_prev_y
    FROM piotroski_f_score p1
    WHERE (fiscal_year_bs, quarter) = (
        SELECT MAX(fiscal_year_bs) - 1, MAX(quarter)
        FROM piotroski_f_score p2 WHERE p2.scrip = p1.scrip
    )
    ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
),
prev_fqc AS (
    SELECT DISTINCT ON (scrip) scrip, quality_score_0_100 AS quality_prev
    FROM fundamental_quality_composite fc1
    WHERE (fiscal_year_bs, quarter) = (
        SELECT MAX(fiscal_year_bs) - 1, MAX(quarter)
        FROM fundamental_quality_composite fc2 WHERE fc2.scrip = fc1.scrip
    )
    ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
)
SELECT
    s.scrip, s.company_name, s.sector,
    lb.close AS latest_close, lb.date AS latest_date,
    CASE WHEN pb.prev_close > 0
         THEN 100.0 * (lb.close - pb.prev_close) / pb.prev_close
         ELSE NULL END                  AS change_pct,
    ls.roe, ls.npl_ratio, ls.car, ls.cd_ratio, ls.pe_ratio,
    s2.composite_score, s2.flags,
    fqc.quality_score_0_100, fqc.quality_tier,
    qmm.quadrant,
    vh.self_valuation_tier,
    dy.total_dividend_yield,
    lp.f_score, pp.f_score_prev_y,
    pf.quality_prev
FROM scrips s
LEFT JOIN latest_bar    lb  ON lb.scrip  = s.scrip
LEFT JOIN prev_bar      pb  ON pb.scrip  = s.scrip
LEFT JOIN latest_snap   ls  ON ls.scrip  = s.scrip
LEFT JOIN latest_s2     s2  ON s2.scrip  = s.scrip
LEFT JOIN latest_fqc    fqc ON fqc.scrip = s.scrip
LEFT JOIN quality_momentum_matrix qmm ON qmm.scrip = s.scrip
LEFT JOIN LATERAL (
    SELECT self_valuation_tier FROM valuation_history
    WHERE scrip = s.scrip
    ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1
) vh ON TRUE
LEFT JOIN LATERAL (
    SELECT total_dividend_yield FROM dividend_yield
    WHERE scrip = s.scrip
    ORDER BY fiscal_year_bs DESC LIMIT 1
) dy ON TRUE
LEFT JOIN latest_pio    lp  ON lp.scrip  = s.scrip
LEFT JOIN prev_pio      pp  ON pp.scrip  = s.scrip
LEFT JOIN prev_fqc      pf  ON pf.scrip  = s.scrip
WHERE s.is_active
"""


class ScreenResponse(BaseModel):
    preset: str
    description: str
    rows: list[UniverseRow]


def _hydrate_rows(rows: list[dict]) -> list[UniverseRow]:
    return [
        UniverseRow(**{
            k: v for k, v in r.items()
            if k in UniverseRow.model_fields
        } | {"flags": list(r.get("flags") or [])})
        for r in rows
    ]


@router.get("/top-quality", response_model=ScreenResponse)
def top_quality(request: Request) -> ScreenResponse:
    """Scrips with composite quality score >= 70 (TOP_DECILE or strong STRONG)."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        _BASE_SELECT + " AND fqc.quality_score_0_100 >= 70 ORDER BY fqc.quality_score_0_100 DESC"
    )
    return ScreenResponse(
        preset="top-quality",
        description="Scrips with composite fundamental quality score ≥ 70.",
        rows=_hydrate_rows(rows),
    )


@router.get("/cheap-vs-self", response_model=ScreenResponse)
def cheap_vs_self(request: Request) -> ScreenResponse:
    """Scrips trading cheap vs their own 5-year P/E history."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        _BASE_SELECT + " AND vh.self_valuation_tier IN ('VERY_CHEAP', 'CHEAP') ORDER BY fqc.quality_score_0_100 DESC NULLS LAST"
    )
    return ScreenResponse(
        preset="cheap-vs-self",
        description="Scrips in the bottom 30% of their own 5-year P/E distribution.",
        rows=_hydrate_rows(rows),
    )


@router.get("/high-yield", response_model=ScreenResponse)
def high_yield(request: Request) -> ScreenResponse:
    """Scrips with total dividend yield >= 8% — above typical NPR FD rate."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        _BASE_SELECT + " AND dy.total_dividend_yield >= 0.08 ORDER BY dy.total_dividend_yield DESC"
    )
    return ScreenResponse(
        preset="high-yield",
        description="Scrips paying total dividend yield ≥ 8% (above typical NPR fixed-deposit rate).",
        rows=_hydrate_rows(rows),
    )


@router.get("/contrarian", response_model=ScreenResponse)
def contrarian(request: Request) -> ScreenResponse:
    """Quality scrips with negative 6-month momentum — possible rerating setup."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        _BASE_SELECT + " AND qmm.quadrant = 'CONTRARIAN_BET' ORDER BY fqc.quality_score_0_100 DESC NULLS LAST"
    )
    return ScreenResponse(
        preset="contrarian",
        description="High-quality scrips with below-median 6-month momentum (CONTRARIAN_BET quadrant).",
        rows=_hydrate_rows(rows),
    )


@router.get("/turnaround", response_model=ScreenResponse)
def turnaround(request: Request) -> ScreenResponse:
    """Scrips where Piotroski F-Score improved ≥ 3 points YoY AND prior
    quality was AVERAGE/WEAK — a classic turnaround screen."""
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        _BASE_SELECT
        + " AND (lp.f_score - pp.f_score_prev_y) >= 3"
          " AND pf.quality_prev <= 40"
          " ORDER BY (lp.f_score - pp.f_score_prev_y) DESC"
    )
    return ScreenResponse(
        preset="turnaround",
        description="Piotroski F-Score improved ≥ 3 points YoY from a weak prior-year base (quality prev ≤ 40).",
        rows=_hydrate_rows(rows),
    )
