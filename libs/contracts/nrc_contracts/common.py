"""Shared enums, aliases, and constants used across contracts."""
from __future__ import annotations
from datetime import date
from enum import Enum
from typing import Annotated, Literal
from pydantic import BeforeValidator, Field


class Quarter(int, Enum):
    """Nepali fiscal-year quarters (Bikram Sambat).

    Q1 = Shrawan–Ashwin   (~Jul 17 – Oct 16)
    Q2 = Kartik–Poush     (~Oct 17 – Jan 14)
    Q3 = Magh–Chaitra     (~Jan 15 – Apr 13)
    Q4 = Baisakh–Ashad    (~Apr 14 – Jul 16)
    """
    Q1 = 1
    Q2 = 2
    Q3 = 3
    Q4 = 4


class ActionType(str, Enum):
    BONUS = "bonus"
    RIGHTS = "rights"
    CASH_DIVIDEND = "cash_dividend"
    SPLIT = "split"
    MERGER = "merger"


class Language(str, Enum):
    EN = "en"
    NE = "ne"
    MIXED = "mixed"


class EventType(str, Enum):
    EARNINGS = "earnings"
    DIVIDEND = "dividend"
    MANAGEMENT = "management"
    REGULATORY = "regulatory"
    MERGER = "merger"
    OTHER = "other"


class SourceTier(str, Enum):
    """Relative authority of a data source. Lower rank wins in Silver dedup.

    Primary, hand-curated client dumps take precedence over historical exports,
    which in turn take precedence over any live API feed, which beats scraped
    data. Scraping is now a fallback-only path kept for emergency backfill."""
    CLIENT_AUTHORITATIVE = "client_authoritative"
    CLIENT_HISTORICAL = "client_historical"
    LIVE_API = "live_api"
    SCRAPED = "scraped"


SOURCE_TIER_RANK: dict[SourceTier, int] = {
    SourceTier.CLIENT_AUTHORITATIVE: 0,
    SourceTier.CLIENT_HISTORICAL: 1,
    SourceTier.LIVE_API: 2,
    SourceTier.SCRAPED: 3,
}


# Known NEPSE sector labels (canonical form). Free-form str in schemas;
# we canonicalize here so downstream code has a stable list.
SECTORS: tuple[str, ...] = (
    "Commercial Bank",
    "Development Bank",
    "Finance",
    "Microfinance",
    "Life Insurance",
    "Non Life Insurance",
    "Hydro Power",
    "Manufacturing and Processing",
    "Hotels",
    "Trading",
    "Investment",
    "Mutual Fund",
    "Corporate Debenture",
    "Preferred Stock",
    "Others",
    "Merged",  # Sharesansar marks merged/delisted entities this way
)

# Type aliases for clarity at call sites
FiscalYearBS = int          # e.g. 2082 → BS FY 2082/2083
TradingDate = date          # Gregorian (AD) date of a trading day


def _canon_scrip(v: object) -> object:
    """Trim + uppercase incoming scrip symbols; reject empty."""
    if isinstance(v, str):
        s = v.strip().upper()
        if not s:
            raise ValueError("scrip must not be blank")
        return s
    return v


# Use this in every model that has a `scrip` field to get consistent canonicalization.
Scrip = Annotated[str, BeforeValidator(_canon_scrip), Field(min_length=1, max_length=20)]
