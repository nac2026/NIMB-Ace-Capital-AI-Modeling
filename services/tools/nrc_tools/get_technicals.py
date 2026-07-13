"""get_technicals(scrip, date?) → latest (or specified-date) indicator set(s).

Accepts a single scrip or a list — always returns a list of IndicatorSet."""
from __future__ import annotations
from datetime import date as dt_date

from pydantic import BaseModel, Field

from nrc_contracts import IndicatorSet, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_technicals"


class GetTechnicalsInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list of symbols, e.g. 'NABIL' or ['NABIL','EBL','SCB']. "
                    "Pass a list to compare technical indicators across banks.",
    )
    as_of_date: dt_date | None = Field(
        default=None,
        description="Trading date (YYYY-MM-DD). Omit for latest.",
    )


def get_technicals(
    scrip: str | list[str],
    *,
    as_of_date: dt_date | None = None,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[IndicatorSet]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        if as_of_date is not None:
            rows = pg.fetch_all(
                f"SELECT * FROM indicators_daily WHERE scrip IN ({ph}) AND date=%s ORDER BY scrip",
                (*scrips, as_of_date),
            )
        else:
            rows = pg.fetch_all(
                f"""
                SELECT DISTINCT ON (scrip) *
                FROM indicators_daily
                WHERE scrip IN ({ph})
                ORDER BY scrip, date DESC
                """,
                tuple(scrips),
            )

    if not rows:
        raise ToolError(
            f"No indicator data for scrip(s)={scrips} date={as_of_date}",
            tool=TOOL_NAME, reason="not_found",
        )

    indicators = [IndicatorSet.model_validate(row) for row in rows]
    data_as_of = max(r["computed_at"] for r in rows) if rows else None
    return build_response(
        tool=TOOL_NAME, data=indicators,
        sources=["postgres.indicators_daily"], data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get technical indicators (SMA 20/50/200, RSI-14, MACD, Bollinger Bands, ATR-14) "
        "for one or more scrips. Pass a list for comparisons: e.g. scrip=['NABIL','EBL']. "
        "Use for overbought/oversold, moving averages, or trend-direction questions."
    ),
    "input_schema": GetTechnicalsInput.model_json_schema(),
}
