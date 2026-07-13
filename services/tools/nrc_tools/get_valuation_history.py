"""get_valuation_history(scrip, quarters=20) → P/E and P/B vs own history.

From gold.valuation_history. Self-percentile over trailing 20 quarters
answers 'is NABIL cheap vs its own past?' which gold.valuation doesn't
(that's peer-relative)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_valuation_history"


class GetValuationHistoryInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    quarters: int = Field(20, ge=1, le=60, description="Lookback in quarters (default 20 ≈ 5y).")


class ValuationHistoryRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    pe_self_pct_5y: float | None = None
    pb_self_pct_5y: float | None = None
    pe_self_pct_all: float | None = None
    self_valuation_tier: str | None = None


def get_valuation_history(
    scrip: str,
    *,
    quarters: int = 20,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[ValuationHistoryRow]]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT fiscal_year_bs, quarter, pe_ratio, pb_ratio,
                   pe_self_pct_5y, pb_self_pct_5y, pe_self_pct_all,
                   self_valuation_tier, computed_at
            FROM valuation_history
            WHERE scrip = %s
            ORDER BY fiscal_year_bs DESC, quarter DESC
            LIMIT %s
            """,
            (scrip, quarters),
        )
    if not rows:
        raise ToolError(f"No valuation_history for {scrip}", tool=TOOL_NAME, reason="not_found")
    rows.reverse()

    data_as_of = max(r["computed_at"] for r in rows)
    results = [ValuationHistoryRow.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.valuation_history"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return P/E and P/B history with self-percentile ranking vs scrip's "
        "own 5-year distribution. pe_self_pct_5y of 0.15 means the scrip is "
        "currently cheaper than 85% of its own last 5 years. self_valuation_tier "
        "buckets this (VERY_CHEAP / CHEAP / FAIR / EXPENSIVE / VERY_EXPENSIVE). "
        "Use for 'is NABIL cheap vs its own past?' — complements peer-relative "
        "valuation from get_valuation."
    ),
    "input_schema": GetValuationHistoryInput.model_json_schema(),
}
