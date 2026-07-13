"""stage2_bank_screen(scrip?) → bank-specific deep screen with health flags."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import Quarter, Stage2BankResult, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "stage2_bank_screen"


class Stage2BankScreenInput(BaseModel):
    scrip: str | None = Field(
        default=None,
        description="Filter to one scrip. Omit for the full ranked list.",
    )
    sector: str | None = Field(
        default=None,
        description=(
            "Filter to one sector, e.g. 'Commercial Bank', 'Hydro Power', "
            "'Life Insurance'. Omit for all sectors."
        ),
    )
    min_composite_score: float | None = Field(
        default=None,
        ge=0, le=1,
        description="Only return scrips with composite_score >= this threshold.",
    )


def stage2_bank_screen(
    *,
    scrip: str | None = None,
    sector: str | None = None,
    min_composite_score: float | None = None,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[Stage2BankResult]]:
    pg = pg or PostgresClient()

    filters = ["1=1"]
    params: list = []
    if scrip is not None:
        filters.append("scrip = %s")
        params.append(scrip.strip().upper())
    if sector is not None:
        filters.append("sector = %s")
        params.append(sector.strip())
    if min_composite_score is not None:
        filters.append("composite_score >= %s")
        params.append(min_composite_score)

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT * FROM stage2_bank_screen
            WHERE {' AND '.join(filters)}
            ORDER BY fiscal_year_bs DESC, quarter DESC, composite_score DESC
            """,
            tuple(params),
        )

    if not rows:
        raise ToolError(
            "No Stage 2 bank screen results match the filters",
            tool=TOOL_NAME,
            reason="not_found",
        )

    results = []
    for r in rows:
        r["quarter"] = Quarter(r["quarter"])
        results.append(Stage2BankResult.model_validate(r))

    return build_response(
        tool=TOOL_NAME,
        data=results,
        sources=["postgres.stage2_bank_screen"],
        data_as_of=rows[0]["computed_at"],
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Run the sector-aware deep fundamental screen. Covers ALL sectors (not just "
        "banks); every scrip is scored on percentiles computed WITHIN its own sector, "
        "plus a composite score and boolean flags. Optionally filter by `sector` or "
        "`scrip`.\n\n"
        "IMPORTANT semantic: ALL percentiles are normalized so 1.0 = best-in-sector and "
        "0.0 = worst-in-sector, regardless of the metric's natural direction:\n"
        "  * roe_percentile / roa_percentile / net_margin_percentile: higher = better\n"
        "  * npl_percentile: 1.0 = LOWEST NPL in sector (best); 0.0 = highest (worst)\n"
        "  * car_percentile: higher = better\n"
        "  * cd_percentile: 1.0 = LOWEST CD ratio; 0.0 = highest (liquidity risk)\n"
        "composite_score (mean of the relevant percentiles) closer to 1.0 = healthier.\n\n"
        "Two scoring families by what the sector reports:\n"
        "  * Deposit-taking BFIs (Commercial Bank, Development Bank, Finance, Microfinance): "
        "composite = mean of ROE, NPL, CAR, CD percentiles. The npl/car/cd columns are "
        "populated. Flags: NPL_HIGH > 5%, CAR_LOW < 11%, CD_HIGH > 85%, ROE_LOW < 10%.\n"
        "  * All other sectors (hydro, manufacturing, hotels, investment, life & non-life "
        "insurance, …): composite = mean of ROE, ROA, net-margin percentiles. npl/car/cd "
        "are NULL. Flags: LOSS (net profit < 0), ROE_LOW (< 10%), THIN_MARGIN (margin < 5%).\n\n"
        "Use for 'which hydropower companies are healthiest?', 'most stressed banks', "
        "'show flagged scrips in <sector>', 'how healthy is X?', or any sector-relative "
        "fundamental-health question."
    ),
    "input_schema": Stage2BankScreenInput.model_json_schema(),
}
