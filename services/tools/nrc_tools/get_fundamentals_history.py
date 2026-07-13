"""get_fundamentals_history(scrip, last_n_quarters?) → ordered quarterly snapshots.

Accepts a single scrip or a list — returns the last N quarters for all requested
scrips in chronological order (oldest first), grouped by scrip."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import FundamentalSnapshot, Quarter, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_fundamentals_history"


class GetFundamentalsHistoryInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list of symbols, e.g. 'NABIL' or ['NABIL','EBL']. "
                    "Pass a list to compare historical trends across banks in one call.",
    )
    last_n_quarters: int = Field(
        default=8, ge=1, le=20,
        description="Number of most recent quarters per scrip (default 8 ≈ 2 fiscal years).",
    )


def get_fundamentals_history(
    scrip: str | list[str],
    *,
    last_n_quarters: int = 8,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[FundamentalSnapshot]]:
    """Last N quarterly snapshots for one or more scrips, oldest first."""
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY scrip
                        ORDER BY fiscal_year_bs DESC, quarter DESC
                    ) AS rn
                FROM fundamental_snapshots
                WHERE scrip IN ({ph})
            ) t
            WHERE rn <= %s
            ORDER BY scrip, fiscal_year_bs ASC, quarter ASC
            """,
            (*scrips, last_n_quarters),
        )

    if not rows:
        raise ToolError(
            f"No fundamental history for scrip(s)={scrips}",
            tool=TOOL_NAME, reason="not_found",
        )

    snapshots = []
    for row in rows:
        row.pop("rn", None)
        row["quarter"] = Quarter(row["quarter"])
        snapshots.append(FundamentalSnapshot.model_validate(row))

    return build_response(
        tool=TOOL_NAME, data=snapshots,
        sources=["postgres.fundamental_snapshots"], latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get multiple quarters of financial history for one or more scrips in a single call. "
        "Returns last N quarterly snapshots per scrip (default 8 ≈ 2 fiscal years), chronological order — "
        "EPS, ROE, ROA, NPL ratio, CAR, CD ratio, BVPS, net profit, total deposits, total loans, P/E, P/B. "
        "Pass a list to compare trends across banks: e.g. scrip=['NABIL','EBL']. "
        "Use for trend analysis, time-series charts, or 'how has X changed over time?' questions."
    ),
    "input_schema": GetFundamentalsHistoryInput.model_json_schema(),
}
