"""News articles + hybrid search results."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from .common import EventType, Language


class NewsArticle(BaseModel):
    """One scraped article. article_id = stable hash of url.
    Maps 1:1 to silver.news (and mirrored into Postgres news_articles for search)."""
    model_config = ConfigDict(extra="forbid")

    article_id: str = Field(min_length=1)
    url: str
    source: str                                      # sharesansar | merolagani | bank_website
    published_at: datetime
    title: str
    body: str | None = None                          # fetched lazily by news_embedder
    language: Language = Language.EN
    scrip_tags: list[str] = Field(default_factory=list)
    sector_tags: list[str] = Field(default_factory=list)
    event_type: EventType = EventType.OTHER
    ingested_at: datetime


class NewsSearchHit(BaseModel):
    article: NewsArticle
    similarity: float = Field(ge=0, le=1)            # cosine similarity from pgvector
    match_tags: list[str] = Field(default_factory=list)


class NewsSearchResult(BaseModel):
    query: str
    hits: list[NewsSearchHit]
    total_results: int = Field(ge=0)
