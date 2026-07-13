"""Newsfeed settings — sources, cadence, enrichment batch size."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Broad Google News queries run every cycle for market/sector breadth. Per-scrip
# queries are derived from the active universe (see sources.google_news_for_scrips).
DEFAULT_BROAD_QUERIES: tuple[str, ...] = (
    "NEPSE Nepal stock market",
    "Nepal commercial bank NEPSE",
    "Nepal hydropower share NEPSE",
    "Nepal microfinance share",
    "Nepal life insurance share NEPSE",
    "Nepal Rastra Bank monetary policy interest rate",
    "SEBON Nepal securities",
    "Nepal IPO right share bonus dividend NEPSE",
)

# Sharesansar category pages crawled each cycle (slug only). These carry
# company-specific events (dividends/rights/bonus, listings, IPO/FPO) that the
# generic /rss feed under-covers. Override via NEWSFEED_SHARESANSAR_CATEGORIES
# (comma-separated) as more categories are added.
DEFAULT_SHARESANSAR_CATEGORIES: tuple[str, ...] = (
    "ipo-fpo-news",
    "dividend-right-bonus",
    "exclusive",
    "financial-analysis",
    "share-listed",
)


class NewsfeedSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    newsfeed_interval_s: float = Field(default=1800.0, gt=0)     # 30 min default
    newsfeed_lookback_days: int = Field(default=30, ge=1)        # rollup window
    newsfeed_enrich_batch: int = Field(default=20, ge=1, le=50)  # headlines per LLM call
    newsfeed_max_per_query: int = Field(default=25, ge=1)        # cap items per RSS query
    newsfeed_sharesansar_rss: str = Field(default="https://www.sharesansar.com/rss")
    newsfeed_google_news_enabled: bool = Field(default=True)
    # Sharesansar category-page crawl (richer than /rss; bodies fetched for new URLs).
    newsfeed_sharesansar_categories_enabled: bool = Field(default=True)
    newsfeed_sharesansar_categories: tuple[str, ...] = Field(default=DEFAULT_SHARESANSAR_CATEGORIES)
    newsfeed_category_cap_per_page: int = Field(default=25, ge=1)   # detail URLs per category
    # Merolagani JSON news-list crawl (bodies fetched per new article from NewsDetail.aspx).
    newsfeed_merolagani_enabled: bool = Field(default=True)
    newsfeed_merolagani_pages: int = Field(default=3, ge=1)         # general-feed list pages per cycle
    newsfeed_merolagani_page_size: int = Field(default=8, ge=1)     # items per page
    # Per-symbol sweep: query Merolagani's symbol= filter for the N stalest scrips each
    # cycle (rotates through the universe). The symbol seeds an LLM candidate that the
    # LLM still confirms — authoritative-ish recall without blind tagging. 0 disables.
    newsfeed_merolagani_symbol_sweep_per_cycle: int = Field(default=20, ge=0)
    newsfeed_merolagani_symbol_pages: int = Field(default=1, ge=1)  # list pages per swept symbol
    # Per-scrip Google News queries are expensive (one HTTP call each); cap how
    # many scrips we sweep per cycle (rotates through the universe).
    newsfeed_scrip_sweep_per_cycle: int = Field(default=30, ge=0)


@lru_cache(maxsize=1)
def get_newsfeed_settings() -> NewsfeedSettings:
    return NewsfeedSettings()
