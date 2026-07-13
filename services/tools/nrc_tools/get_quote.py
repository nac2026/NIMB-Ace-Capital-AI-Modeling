"""get_quote(scrip) → latest daily bar + change. Accepts single scrip or list."""
from __future__ import annotations
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from nrc_contracts import Quote, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_quote"


class GetQuoteInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list of symbols, e.g. 'NABIL' or ['NABIL','EBL','SCB']. "
                    "Pass a list when querying 2+ scrips in one call.",
    )


def get_quote(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[Quote]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    # Check live_quotes first — accept ticks fresher than 5 minutes
    with _timed() as t:
        live_rows = pg.fetch_all(
            f"""
            SELECT scrip, price, change_abs, change_pct, volume, turnover, tick_at
            FROM live_quotes
            WHERE scrip IN ({ph})
              AND tick_at > NOW() - INTERVAL '5 minutes'
            ORDER BY scrip
            """,
            tuple(scrips),
        )

    if live_rows and len(live_rows) == len(scrips):
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
            for row in live_rows
        ]
        data_as_of = max(r["tick_at"] for r in live_rows)
        return build_response(
            tool=TOOL_NAME, data=quotes,
            sources=["postgres.live_quotes"], data_as_of=data_as_of, latency_ms=t["latency_ms"],
        )

    # Fall back to daily_bars (batch EOD data)
    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            WITH ranked AS (
                SELECT
                    scrip, date, close, volume, turnover,
                    LAG(close) OVER (PARTITION BY scrip ORDER BY date) AS prev_close,
                    ROW_NUMBER() OVER (PARTITION BY scrip ORDER BY date DESC) AS rn
                FROM daily_bars
                WHERE scrip IN ({ph})
            )
            SELECT scrip, date, close, volume, turnover, prev_close
            FROM ranked
            WHERE rn = 1
            ORDER BY scrip
            """,
            tuple(scrips),
        )

    if not rows:
        raise ToolError(f"No price data for {scrips}", tool=TOOL_NAME, reason="not_found")

    quotes = []
    latest_date = None
    for row in rows:
        close, prev = row["close"], row["prev_close"]
        change = (close - prev) if prev is not None else 0.0
        pct = (change / prev * 100.0) if prev else 0.0
        as_of = datetime.combine(row["date"], datetime.min.time(), tzinfo=timezone.utc)
        if latest_date is None or row["date"] > latest_date:
            latest_date = row["date"]
        quotes.append(Quote(
            scrip=row["scrip"], close=float(close), change=float(change),
            percent_change=float(pct), volume=int(row["volume"]),
            turnover=float(row["turnover"]), as_of=as_of,
        ))

    data_as_of = datetime.combine(latest_date, datetime.min.time(), tzinfo=timezone.utc) if latest_date else None
    return build_response(
        tool=TOOL_NAME, data=quotes,
        sources=["postgres.daily_bars"], data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get the latest price quote (close price, change, volume, turnover) for one or more scrips. "
        "Automatically returns intraday real-time data when the live feed is active (< 5 min fresh); "
        "falls back to end-of-day batch data otherwise. "
        "Pass a list for any comparison: e.g. scrip=['NABIL','EBL','SCB']. "
        "Use for current price, today's change, or latest trade questions."
    ),
    "input_schema": GetQuoteInput.model_json_schema(),
}
