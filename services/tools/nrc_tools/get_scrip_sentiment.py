"""get_scrip_sentiment(scrip) → ambient news sentiment for a stock.

From postgres.scrip_sentiment (rebuilt each newsfeed cycle from live, enriched
news). Returns the recency-weighted sentiment score + label, bullish/bearish
counts, and the most-recent headlines. Use this to ground any answer about a
stock in current market sentiment — it's the 'what's the news saying' signal."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_scrip_sentiment"


class GetScripSentimentInput(BaseModel):
    scrip: str | list[str] = Field(..., description="One scrip symbol or a list of symbols.")


class ScripSentiment(BaseModel):
    scrip: str
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    n_articles: int = 0
    bullish_count: int = 0
    neutral_count: int = 0
    bearish_count: int = 0
    window_days: int | None = None
    latest_published_at: str | None = None
    top_headlines: list[dict] = Field(default_factory=list)


def get_scrip_sentiment(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[ScripSentiment]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips if s and s.strip()]
    if not scrips:
        raise ToolError("No scrip provided", tool=TOOL_NAME, reason="bad_input")

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT scrip, sentiment_label, sentiment_score, n_articles,
                   bullish_count, neutral_count, bearish_count, window_days,
                   latest_published_at, top_headlines, computed_at
            FROM scrip_sentiment
            WHERE scrip = ANY(%s)
            ORDER BY n_articles DESC
            """,
            (scrips,),
        )
    if not rows:
        raise ToolError(
            f"No recent news sentiment for {', '.join(scrips)}", tool=TOOL_NAME, reason="not_found"
        )

    data_as_of = max(r["computed_at"] for r in rows)
    out = []
    for r in rows:
        out.append(ScripSentiment(
            scrip=r["scrip"],
            sentiment_label=r["sentiment_label"],
            sentiment_score=r["sentiment_score"],
            n_articles=r["n_articles"],
            bullish_count=r["bullish_count"],
            neutral_count=r["neutral_count"],
            bearish_count=r["bearish_count"],
            window_days=r["window_days"],
            latest_published_at=r["latest_published_at"].isoformat() if r["latest_published_at"] else None,
            top_headlines=r["top_headlines"] or [],
        ))
    return build_response(
        tool=TOOL_NAME, data=out, sources=["postgres.scrip_sentiment"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Current news/market sentiment for a scrip (or list) from live-ingested, "
        "Gemini-enriched news: a recency-weighted score (-1..+1) + label "
        "(BULLISH/NEUTRAL/BEARISH), bullish/bearish article counts, and recent "
        "headlines. Use to ground answers in 'what's the news saying' / market "
        "sentiment for a stock."
    ),
    "input_schema": GetScripSentimentInput.model_json_schema(),
}
