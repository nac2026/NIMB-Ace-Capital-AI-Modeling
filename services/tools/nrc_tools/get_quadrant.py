"""get_quadrant(scrip) → 2x2 quality × momentum positioning.

From gold.quality_momentum_matrix — descriptive positioning (QUALITY_LEADER,
CONTRARIAN_BET, MOMENTUM_TRAP, AVOID) based on the scrip's quality score vs
sector-median and 6-month return vs sector-median. Descriptive, not
prescriptive — fine to render in UI."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_quadrant"


class GetQuadrantInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="Scrip or list. Returns quadrant + the sector thresholds that placed each scrip.",
    )


class QuadrantResult(BaseModel):
    scrip: str
    sector: str | None = None
    quality_score_0_100: float | None = None
    quality_tier: str | None = None
    return_6m: float | None = None
    quadrant: str | None = None
    sector_quality_median: float | None = None
    sector_return_6m_median: float | None = None
    is_high_quality: bool | None = None
    is_high_momentum: bool | None = None


def get_quadrant(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[QuadrantResult]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT scrip, sector,
                   quality_score_0_100, quality_tier,
                   return_6m, quadrant,
                   sector_quality_median, sector_return_6m_median,
                   is_high_quality, is_high_momentum, computed_at
            FROM quality_momentum_matrix
            WHERE scrip IN ({ph})
            """,
            tuple(scrips),
        )
    if not rows:
        raise ToolError(f"No quadrant for scrip(s)={scrips}", tool=TOOL_NAME, reason="not_found")

    data_as_of = max(r["computed_at"] for r in rows)
    results = [QuadrantResult.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.quality_momentum_matrix"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return quality × 6-month momentum quadrant positioning for one or "
        "more scrips. Values: QUALITY_LEADER (high quality + positive 6m), "
        "CONTRARIAN_BET (high quality + negative 6m), MOMENTUM_TRAP (low "
        "quality + positive 6m), AVOID (low quality + negative 6m). Thresholds "
        "are sector-relative. Use to explain WHY a scrip is positioned where "
        "it is, not as a BUY/SELL recommendation."
    ),
    "input_schema": GetQuadrantInput.model_json_schema(),
}
