"""get_price_history(scrip, days) → daily close prices for charting.

Queries daily_bars for the last N trading days (chronological order).
Supports one or multiple scrips so the LLM can overlay lines for peer
comparison. Designed to feed the ```chart block renderer in the UI."""
from __future__ import annotations
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_price_history"


class PriceBar(BaseModel):
    scrip: str
    date: str          # ISO date string, e.g. "2026-03-15"
    close: float


class GetPriceHistoryInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description=(
            "NEPSE scrip symbol or list of symbols. "
            "Pass a list to overlay multiple scrips on one chart, e.g. ['NABIL','EBL']."
        ),
    )
    days: int = Field(
        default=30,
        ge=5,
        le=365,
        description="Number of trailing trading days to return (default 30, max 365).",
    )


def get_price_history(
    scrip: str | list[str],
    days: int = 30,
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[PriceBar]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT scrip, date, close
            FROM (
                SELECT scrip, date, close,
                       ROW_NUMBER() OVER (PARTITION BY scrip ORDER BY date DESC) AS rn
                FROM daily_bars
                WHERE scrip IN ({ph})
            ) sub
            WHERE rn <= %s
            ORDER BY scrip, date ASC
            """,
            (*scrips, days),
        )

    if not rows:
        raise ToolError(
            f"No price history for {scrips}",
            tool=TOOL_NAME,
            reason="not_found",
        )

    latest_date = max(row["date"] for row in rows)
    data_as_of = datetime.combine(latest_date, datetime.min.time(), tzinfo=timezone.utc)

    bars = [
        PriceBar(
            scrip=row["scrip"],
            date=row["date"].isoformat(),
            close=float(row["close"]),
        )
        for row in rows
    ]

    return build_response(
        tool=TOOL_NAME,
        data=bars,
        sources=["postgres.daily_bars"],
        data_as_of=data_as_of,
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get daily closing prices for one or more scrips over the last N trading days. "
        "Use for any price trend, chart, or time-series question — e.g. 'show NIMB price last month', "
        "'compare NABIL vs EBL price last quarter', 'how has HBL trended this year'. "
        "Returns chronological (date, close) pairs per scrip. "
        "Default is 30 days; pass days=90 for a quarter, days=365 for a year."
    ),
    "input_schema": GetPriceHistoryInput.model_json_schema(),
}
