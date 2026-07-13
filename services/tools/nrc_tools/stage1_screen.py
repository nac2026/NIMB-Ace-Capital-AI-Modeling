"""stage1_screen(sector?, passed_only?) → Stage 1 composite screen results."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import Quarter, Stage1Result, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "stage1_screen"


class Stage1ScreenInput(BaseModel):
    sector: str | None = Field(default=None, description="Filter to one sector, e.g. 'Commercial Bank'")
    passed_only: bool = Field(default=True, description="Only return scrips that passed the screen")


def stage1_screen(
    *,
    sector: str | None = None,
    passed_only: bool = True,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[Stage1Result]]:
    pg = pg or PostgresClient()

    filters = ["1=1"]
    params: list = []
    if sector is not None:
        filters.append("sector = %s")
        params.append(sector)
    if passed_only:
        filters.append("passed")

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT * FROM stage1_screen_results
            WHERE {' AND '.join(filters)}
            ORDER BY fiscal_year_bs DESC, quarter DESC, rank ASC
            """,
            tuple(params),
        )

    if not rows:
        raise ToolError(
            "No Stage 1 screen results match the filters",
            tool=TOOL_NAME,
            reason="not_found",
        )

    results = []
    for r in rows:
        r["quarter"] = Quarter(r["quarter"])
        results.append(Stage1Result.model_validate(r))

    return build_response(
        tool=TOOL_NAME,
        data=results,
        sources=["postgres.stage1_screen_results"],
        data_as_of=rows[0]["computed_at"],
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Run the Stage-1 sector-relative screen (composite z-score of profitability + "
        "revenue growth + return ratio). Returns the ranked scrips that passed. "
        "Use for 'which banks are in the top half of the sector?', 'screen for winners', "
        "or 'show me the Stage-1 pass list'."
    ),
    "input_schema": Stage1ScreenInput.model_json_schema(),
}
