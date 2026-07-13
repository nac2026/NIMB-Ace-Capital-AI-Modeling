"""SMTM Data API client — the live NEPSE feed (floorsheet, quotes, indices, company list)."""
from __future__ import annotations

__version__ = "0.1.0"

from .client import SMTMClient, SMTMError
from .config import SMTMSettings, get_smtm_settings
from .models import (
    Broker,
    Company,
    FloorsheetPage,
    FloorsheetTrade,
    IndexTimeseriesPoint,
    IndexValue,
    KeyStatsRow,
    LiveStock,
    MarketSummary,
    TimeseriesPoint,
)
from .sectors import NON_EQUITY_SECTORS, is_equity_sector, normalize_sector

__all__ = [
    "SMTMClient",
    "SMTMError",
    "SMTMSettings",
    "get_smtm_settings",
    "Broker",
    "Company",
    "FloorsheetPage",
    "FloorsheetTrade",
    "IndexTimeseriesPoint",
    "IndexValue",
    "KeyStatsRow",
    "LiveStock",
    "MarketSummary",
    "TimeseriesPoint",
    "normalize_sector",
    "is_equity_sector",
    "NON_EQUITY_SECTORS",
]
