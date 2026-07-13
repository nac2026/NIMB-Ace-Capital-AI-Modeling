"""get_dupont(scrip, quarters=8) → DuPont ROE decomposition trajectory.

Answers "why is NABIL's ROE 12.8%?" with the 2/3/5-step decomposition. From
gold.dupont_decomposition — ROE = ROA × Leverage = NPM × Turnover × Leverage,
and the 5-step: Tax Burden × Interest Burden × Operating Margin × Asset
Turnover × Leverage."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_dupont"


class GetDupontInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    quarters: int = Field(8, ge=1, le=40,
                          description="How many quarters of history (default 8 ≈ 2 fiscal years).")


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


def get_dupont(
    scrip: str,
    *,
    quarters: int = 8,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[DupontRow]]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT fiscal_year_bs, quarter,
                   roe_computed, roa, equity_multiplier,
                   net_profit_margin, asset_turnover,
                   tax_burden, interest_burden, operating_margin, nim,
                   computed_at
            FROM dupont_decomposition
            WHERE scrip = %s
            ORDER BY fiscal_year_bs DESC, quarter DESC
            LIMIT %s
            """,
            (scrip, quarters),
        )
    if not rows:
        raise ToolError(f"No DuPont data for {scrip}", tool=TOOL_NAME, reason="not_found")
    rows.reverse()  # chronological for trend reading

    data_as_of = max(r["computed_at"] for r in rows)
    results = [DupontRow.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.dupont_decomposition"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return DuPont decomposition of ROE over the last N quarters. Shows "
        "ROE = ROA × equity_multiplier, and the 5-step form (tax_burden × "
        "interest_burden × operating_margin × asset_turnover × leverage). "
        "Use to attribute ROE changes — 'is NABIL's ROE up because of higher "
        "margins or higher leverage?'"
    ),
    "input_schema": GetDupontInput.model_json_schema(),
}
