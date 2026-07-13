"""get_valuation(scrip) → P/E vs peer median, upside estimate.

Accepts a single scrip or a list — always returns a list of Valuation."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse, Valuation
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_valuation"


class GetValuationInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list of symbols, e.g. 'NABIL' or ['NABIL','EBL','SCB']. "
                    "Pass a list to compare valuations across banks.",
    )


def get_valuation(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[Valuation]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT DISTINCT ON (scrip) *
            FROM valuation
            WHERE scrip IN ({ph})
            ORDER BY scrip, date DESC
            """,
            tuple(scrips),
        )

    if not rows:
        raise ToolError(
            f"No valuation snapshot for scrip(s)={scrips}",
            tool=TOOL_NAME, reason="not_found",
        )

    valuations = [Valuation.model_validate(row) for row in rows]
    data_as_of = max(r["computed_at"] for r in rows) if rows else None
    return build_response(
        tool=TOOL_NAME, data=valuations,
        sources=["postgres.valuation"], data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get valuation metrics (P/E trailing, P/B, peer sector medians, premium-vs-peer, implied upside) "
        "for one or more scrips. Pass a list for comparisons: e.g. scrip=['NABIL','EBL','SCB']. "
        "Use for cheap/expensive questions, P/E peer comparisons, or fair value estimates."
    ),
    "input_schema": GetValuationInput.model_json_schema(),
}
