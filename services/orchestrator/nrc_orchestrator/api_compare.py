"""Compare endpoint — bulk per-scrip summary for 2-5 scrips.

Used by the /compare page in the frontend. Returns the same shape as
/api/scrip/{symbol}/summary but as a list, so the frontend can render a
transposed metric grid (metrics as rows, scrips as columns)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from nrc_storage import PostgresClient

from .api_scrip import ScripSummary

router = APIRouter(prefix="/api", tags=["compare"])


@router.get("/compare", response_model=list[ScripSummary])
def compare(
    request: Request,
    scrips: str = Query(..., description="Comma-separated list of 2-5 NEPSE tickers, e.g. NABIL,NICA,HBL"),
) -> list[ScripSummary]:
    """Return a ScripSummary per requested scrip, in the order provided.

    Bounded at 5 scrips — any more and the transposed grid becomes
    unreadable. Unknown scrips produce a 404 so the frontend can warn
    the user to remove them."""
    symbols = [s.strip().upper() for s in scrips.split(",") if s.strip()]
    if not 2 <= len(symbols) <= 5:
        raise HTTPException(
            422, "Provide 2 to 5 comma-separated scrips (e.g. scrips=NABIL,NICA,HBL)."
        )

    pg: PostgresClient = request.app.state.pg

    # Validate all scrips exist first so one typo fails the whole request
    # cleanly rather than returning a partial result.
    placeholders = ",".join(["%s"] * len(symbols))
    known_rows = pg.fetch_all(
        f"SELECT scrip FROM scrips WHERE scrip IN ({placeholders})",
        tuple(symbols),
    )
    known = {r["scrip"] for r in known_rows}
    missing = [s for s in symbols if s not in known]
    if missing:
        raise HTTPException(404, f"Unknown scrip(s): {', '.join(missing)}")

    # Bulk fetch per-scrip summaries. One SQL round-trip via IN clause.
    rows = pg.fetch_all(
        f"""
        WITH latest_bar AS (
            SELECT DISTINCT ON (scrip) scrip, date, close
            FROM daily_bars WHERE scrip IN ({placeholders})
            ORDER BY scrip, date DESC
        ),
        prev_bar AS (
            SELECT scrip, close AS prev_close
            FROM (
                SELECT scrip, close,
                       ROW_NUMBER() OVER (PARTITION BY scrip ORDER BY date DESC) AS rn
                FROM daily_bars WHERE scrip IN ({placeholders})
            ) x WHERE rn = 2
        ),
        week52 AS (
            SELECT scrip,
                   MIN(close) AS lo, MAX(close) AS hi
            FROM daily_bars
            WHERE scrip IN ({placeholders})
              AND date >= (CURRENT_DATE - INTERVAL '365 days')
            GROUP BY scrip
        ),
        latest_fqc AS (
            SELECT DISTINCT ON (scrip) scrip, quality_score_0_100, quality_tier
            FROM fundamental_quality_composite
            WHERE scrip IN ({placeholders})
            ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
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
        LEFT JOIN latest_bar  lb  ON lb.scrip  = s.scrip
        LEFT JOIN prev_bar    pb  ON pb.scrip  = s.scrip
        LEFT JOIN week52      w   ON w.scrip   = s.scrip
        LEFT JOIN market_cap_metrics mc         ON mc.scrip  = s.scrip
        LEFT JOIN quality_momentum_matrix qmm   ON qmm.scrip = s.scrip
        LEFT JOIN latest_fqc  fqc ON fqc.scrip = s.scrip
        WHERE s.scrip IN ({placeholders})
        """,
        tuple(symbols) * 5,
    )

    # Return in the requested order, not Postgres-natural order.
    by_scrip = {r["scrip"]: r for r in rows}
    return [ScripSummary(**by_scrip[s]) for s in symbols if s in by_scrip]
