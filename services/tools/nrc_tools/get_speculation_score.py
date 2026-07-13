"""get_speculation_score(scrip) → composite manipulation/speculation flag.

From postgres.speculation_score. A 0-100 composite (concentration, control,
circular/wash, single-broker accumulation, block trades) with a tier
(LOW/MODERATE/ELEVATED/HIGH) per scrip, plus the component breakdown so the
answer can explain *why* a scrip looks operator-driven. Accepts one scrip or a
list (for screening). This is a flag for review, not a verdict."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_speculation_score"


class GetSpeculationScoreInput(BaseModel):
    scrip: str | list[str] = Field(..., description="One scrip symbol or a list of symbols.")


class SpeculationRow(BaseModel):
    scrip: str
    speculation_score: float | None = None
    speculation_tier: str | None = None
    n_days: int | None = None
    c_concentration: float | None = None
    c_control: float | None = None
    c_circular: float | None = None
    c_accumulation: float | None = None
    c_block: float | None = None
    has_self_trade: int | None = None


def get_speculation_score(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[SpeculationRow]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips if s and s.strip()]
    if not scrips:
        raise ToolError("No scrip provided", tool=TOOL_NAME, reason="bad_input")

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT scrip, speculation_score, speculation_tier, n_days,
                   c_concentration, c_control, c_circular, c_accumulation, c_block,
                   has_self_trade, computed_at
            FROM speculation_score
            WHERE scrip = ANY(%s)
            ORDER BY speculation_score DESC
            """,
            (scrips,),
        )
    if not rows:
        raise ToolError(
            f"No speculation score for {', '.join(scrips)}", tool=TOOL_NAME, reason="not_found"
        )

    data_as_of = max(r["computed_at"] for r in rows)
    results = [
        SpeculationRow.model_validate({k: v for k, v in r.items() if k != "computed_at"})
        for r in rows
    ]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.speculation_score"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Composite 0-100 speculation/manipulation score + tier "
        "(LOW/MODERATE/ELEVATED/HIGH) for one scrip or a list, from floor-sheet "
        "microstructure. Component breakdown: concentration, control, circular/"
        "wash (c_circular), single-broker accumulation, block trades, plus a "
        "self-trade flag. Use for 'is this stock being manipulated / "
        "speculative?' or to rank a shortlist by manipulation risk. A flag for "
        "review, not an investment verdict."
    ),
    "input_schema": GetSpeculationScoreInput.model_json_schema(),
}
