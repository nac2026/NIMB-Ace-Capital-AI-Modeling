"""Shared Pydantic contracts used across all NRC libs and services."""
from __future__ import annotations

__version__ = "0.1.0"

from .common import (
    SECTORS,
    SOURCE_TIER_RANK,
    ActionType,
    EventType,
    FiscalYearBS,
    Language,
    Quarter,
    Scrip,
    SourceTier,
    TradingDate,
)
from .envelope import ToolMetadata, ToolResponse
from .floorsheet import FloorsheetTrade
from .fundamentals import (
    AdditionalInfoSnapshot,
    FundamentalMetric,
    FundamentalSnapshot,
    PeerRanking,
)
from .index import IndexSnapshot
from .internal_trade import InternalTrade
from .macro import MacroIndicator
from .market import CorporateAction, DailyBar, DailyClose, LiveTick, Quote
from .news import NewsArticle, NewsSearchHit, NewsSearchResult
from .scrip import ScripMaster
from .screens import Stage1Result, Stage2BankResult, Valuation
from .technicals import IndicatorSet
from .trace import QueryTrace, ToolCall

__all__ = [
    "SECTORS",
    "SOURCE_TIER_RANK",
    "ActionType",
    "AdditionalInfoSnapshot",
    "EventType",
    "FiscalYearBS",
    "Language",
    "Quarter",
    "Scrip",
    "SourceTier",
    "TradingDate",
    "CorporateAction",
    "FloorsheetTrade",
    "InternalTrade",
    "DailyBar",
    "DailyClose",
    "LiveTick",
    "Quote",
    "FundamentalMetric",
    "FundamentalSnapshot",
    "PeerRanking",
    "IndicatorSet",
    "NewsArticle",
    "NewsSearchHit",
    "NewsSearchResult",
    "ScripMaster",
    "MacroIndicator",
    "IndexSnapshot",
    "Stage1Result",
    "Stage2BankResult",
    "Valuation",
    "QueryTrace",
    "ToolCall",
    "ToolMetadata",
    "ToolResponse",
]
