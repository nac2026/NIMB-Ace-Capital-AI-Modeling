"""get_live_quote(scrip) → real-time intraday tick from live_quotes table.

Unlike get_quote, this tool returns ONLY live data — it does NOT fall back to
daily_bars. Use this when the user asks for 'current price', 'live price', or
'right now' and a real-time answer matters more than a guaranteed response."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import Quote, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_live_quote"


class GetLiveQuoteInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list of symbols, e.g. 'NABIL' or ['NABIL','EBL']. "
                    "Use this tool when the user explicitly asks for a live, current, or real-time price.",
    )


def get_live_quote(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[Quote]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT scrip, price, change_abs, change_pct, volume, turnover, tick_at
            FROM live_quotes
            WHERE scrip IN ({ph})
            ORDER BY scrip
            """,
            tuple(scrips),
        )

    if not rows:
        raise ToolError(
            f"No live tick data for {scrips}. The real-time feed may not be active yet — "
            "try get_quote for end-of-day data instead.",
            tool=TOOL_NAME,
            reason="not_found",
        )

    quotes = [
        Quote(
            scrip=row["scrip"],
            close=float(row["price"]),
            change=float(row["change_abs"] or 0.0),
            percent_change=float(row["change_pct"] or 0.0),
            volume=int(row["volume"]),
            turnover=float(row["turnover"]),
            as_of=row["tick_at"],
        )
        for row in rows
    ]
    data_as_of = max(r["tick_at"] for r in rows)

    return build_response(
        tool=TOOL_NAME, data=quotes,
        sources=["postgres.live_quotes"], data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get the real-time intraday price for one or more scrips from the live feed. "
        "Returns the most recent tick (price, change, volume) regardless of age — "
        "if the feed is paused, this still returns the last known tick. "
        "Use when the user asks for 'live price', 'current price right now', or 'intraday price'. "
        "Unlike get_quote, this does NOT fall back to end-of-day batch data."
    ),
    "input_schema": GetLiveQuoteInput.model_json_schema(),
}
