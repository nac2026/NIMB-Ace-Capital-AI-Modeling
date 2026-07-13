"""get_fundamentals(scrip, fy?, quarter?) → latest (or specified) quarterly snapshot(s).

Accepts a single scrip or a list — always returns a list of FundamentalSnapshot."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import FundamentalSnapshot, Quarter, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_fundamentals"


class GetFundamentalsInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list of symbols, e.g. 'NABIL' or ['NABIL','EBL','SCB']. "
                    "Pass a list when comparing fundamentals across banks.",
    )
    fiscal_year_bs: int | None = Field(
        default=None,
        description="Bikram Sambat fiscal year start (e.g. 2082 for FY 2082/83). Omit for latest.",
    )
    quarter: int | None = Field(
        default=None, ge=1, le=4,
        description="Quarter 1-4 of the BS fiscal year. Omit for latest.",
    )


def get_fundamentals(
    scrip: str | list[str],
    *,
    fiscal_year_bs: int | None = None,
    quarter: int | None = None,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[FundamentalSnapshot]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        if fiscal_year_bs is not None and quarter is not None:
            rows = pg.fetch_all(
                f"SELECT * FROM fundamental_snapshots WHERE scrip IN ({ph}) "
                f"AND fiscal_year_bs=%s AND quarter=%s ORDER BY scrip",
                (*scrips, fiscal_year_bs, quarter),
            )
        else:
            rows = pg.fetch_all(
                f"""
                SELECT DISTINCT ON (scrip) *
                FROM fundamental_snapshots
                WHERE scrip IN ({ph})
                ORDER BY scrip, fiscal_year_bs DESC, quarter DESC
                """,
                tuple(scrips),
            )

    if not rows:
        raise ToolError(
            f"No fundamentals for scrip(s)={scrips} fy={fiscal_year_bs} q={quarter}",
            tool=TOOL_NAME, reason="not_found",
        )

    snapshots = []
    for row in rows:
        row["quarter"] = Quarter(row["quarter"])
        snapshots.append(FundamentalSnapshot.model_validate(row))

    return build_response(
        tool=TOOL_NAME, data=snapshots,
        sources=["postgres.fundamental_snapshots"], latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get quarterly financial metrics (ROE, ROA, NPL, CAR, CD ratio, EPS, BVPS, "
        "net profit, deposits, loans, P/E, P/B) for one or more scrips. "
        "Pass a list for any comparison: e.g. scrip=['NABIL','EBL','SCB']. "
        "Omit fiscal_year_bs/quarter for the most recent snapshot."
    ),
    "input_schema": GetFundamentalsInput.model_json_schema(),
}
