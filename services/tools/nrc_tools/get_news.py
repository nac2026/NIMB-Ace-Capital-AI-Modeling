"""get_news(scrip?, limit?, search?) → scrip-tagged or keyword news headlines."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import EventType, Language, NewsArticle, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_news"


class GetNewsInput(BaseModel):
    scrip: str | None = Field(
        default=None,
        description="Filter to news tagged to this scrip. Omit for sector-wide news.",
    )
    search: str | None = Field(
        default=None,
        description="Case-insensitive keyword search in title (ILIKE + pg_trgm).",
    )
    limit: int = Field(default=10, ge=1, le=50)


def get_news(
    *,
    scrip: str | None = None,
    search: str | None = None,
    limit: int = 10,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[NewsArticle]]:
    pg = pg or PostgresClient()

    filters = ["1=1"]
    params: list = []
    if scrip is not None:
        filters.append("%s = ANY(scrip_tags)")
        params.append(scrip.strip().upper())
    if search is not None:
        filters.append("title ILIKE %s")
        params.append(f"%{search.strip()}%")
    params.append(limit)

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT article_id, url, source, published_at, title, body,
                   language, scrip_tags, sector_tags, event_type, ingested_at
            FROM news_articles
            WHERE {' AND '.join(filters)}
            ORDER BY published_at DESC
            LIMIT %s
            """,
            tuple(params),
        )

    if not rows:
        raise ToolError(
            f"No news matched filters (scrip={scrip!r}, search={search!r})",
            tool=TOOL_NAME,
            reason="not_found",
        )

    articles = []
    for r in rows:
        r["language"] = Language(r["language"])
        r["event_type"] = EventType(r["event_type"])
        articles.append(NewsArticle.model_validate(r))

    return build_response(
        tool=TOOL_NAME,
        data=articles,
        sources=["postgres.news_articles"],
        data_as_of=rows[0]["published_at"],
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get news headlines, optionally filtered by scrip-tag or keyword search. "
        "Use for 'what's the latest news about X?', 'any news on interest rates?', "
        "'recent earnings news for banks', etc. Bodies not included — use "
        "get_news_details(article_id) for the full text (not yet implemented)."
    ),
    "input_schema": GetNewsInput.model_json_schema(),
}
