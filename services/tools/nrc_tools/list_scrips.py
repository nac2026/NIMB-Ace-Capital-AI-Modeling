"""list_scrips(sector?, active_only?) → the scrip universe (so the LLM can disambiguate)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ScripMaster, ToolResponse
from nrc_storage import PostgresClient

from ._base import _timed, build_response

TOOL_NAME = "list_scrips"


class ListScripsInput(BaseModel):
    sector: str | None = Field(default=None, description="Filter to one sector (e.g. 'Commercial Bank')")
    active_only: bool = Field(default=True, description="Exclude merged/delisted scrips")


def list_scrips(
    *,
    sector: str | None = None,
    active_only: bool = True,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[ScripMaster]]:
    pg = pg or PostgresClient()
    filters = ["1=1"]
    params: list = []
    if sector is not None:
        filters.append("sector = %s")
        params.append(sector)
    if active_only:
        filters.append("is_active")

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT scrip, company_name, sector, sub_sector,
                   listed_shares, paid_up_value, paid_up_capital,
                   NULL::DOUBLE PRECISION AS promoter_shares,
                   NULL::DOUBLE PRECISION AS public_shares,
                   NULL::TEXT AS isin,
                   registered_date, NULL::TEXT AS phone, NULL::TEXT AS email,
                   NULL::TEXT AS address, NULL::TEXT AS website,
                   is_active, company_id
            FROM scrips
            WHERE {' AND '.join(filters)}
            ORDER BY scrip
            """,
            tuple(params),
        )

    scrips = [ScripMaster.model_validate(r) for r in rows]
    return build_response(
        tool=TOOL_NAME,
        data=scrips,
        sources=["postgres.scrips"],
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "List scrips in the universe with basic metadata (company name, sector, listed shares, "
        "paid-up capital). Use when the user refers to a company by name ('how is Nabil doing?') "
        "and you need to resolve the scrip symbol, or to answer 'what banks are active?', "
        "'how many scrips in X sector?'."
    ),
    "input_schema": ListScripsInput.model_json_schema(),
}
