"""get_capital(scrip, quarters=8) → CAR / Tier 1/2 trajectory + NRB headroom.

From gold.capital_strength. NRB minimum CAR is 11% — car_buffer shows how
much headroom the scrip has. Capital tier buckets as STRONG/ADEQUATE/TIGHT/
BELOW_MIN for at-a-glance classification."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_capital"


class GetCapitalInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    quarters: int = Field(8, ge=1, le=40, description="Lookback in quarters (default 8).")


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


def get_capital(
    scrip: str,
    *,
    quarters: int = 8,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[CapitalRow]]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT fiscal_year_bs, quarter,
                   car, tier1_capital, tier2_capital, total_capital,
                   tier1_share, car_buffer, car_yoy_change,
                   capital_tier, computed_at
            FROM capital_strength
            WHERE scrip = %s
            ORDER BY fiscal_year_bs DESC, quarter DESC
            LIMIT %s
            """,
            (scrip, quarters),
        )
    if not rows:
        raise ToolError(f"No capital data for {scrip}", tool=TOOL_NAME, reason="not_found")
    rows.reverse()

    data_as_of = max(r["computed_at"] for r in rows)
    results = [CapitalRow.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.capital_strength"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return CAR / Tier 1 / Tier 2 trajectory + NRB-minimum headroom "
        "(car_buffer) over last N quarters. tier1_share shows capital-quality "
        "mix; capital_tier buckets as STRONG/ADEQUATE/TIGHT/BELOW_MIN. Use "
        "for 'does NABIL have enough capital?' or capital-raise likelihood "
        "questions."
    ),
    "input_schema": GetCapitalInput.model_json_schema(),
}
