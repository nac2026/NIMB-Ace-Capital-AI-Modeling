"""Market data: daily OHLCV bars, latest quote snapshot, corporate actions."""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field
from .common import ActionType, FiscalYearBS, Scrip, SourceTier, TradingDate


class DailyBar(BaseModel):
    """One trading day of OHLCV + turnover for a scrip. Raw, not adjusted.
    Maps 1:1 to silver.prices rows.

    Requires full OHLCV. Close-only historical rows live in DailyClose and
    silver.closes; tool layer unions the two when serving price history."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    scrip: Scrip
    date: TradingDate
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)                       # traded shares
    turnover: float = Field(ge=0)                   # NPR (amount = price × shares)
    num_transactions: int | None = Field(default=None, ge=0)
    previous_close: float | None = Field(default=None, gt=0)
    vwap: float | None = Field(default=None, gt=0)
    adjusted_close: float | None = Field(default=None, gt=0)
    source: str = "sharesansar"
    source_tier: SourceTier | None = None
    ingested_at: datetime


class DailyClose(BaseModel):
    """One trading day — close only. Used for long-history client dumps where
    open/high/low/volume aren't available (e.g. 14-year close series).
    Maps 1:1 to silver.closes rows; kept distinct from DailyBar so OHLCV
    consumers never silently read a null high/low as zero."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    scrip: Scrip
    date: TradingDate
    close: float = Field(gt=0)
    source: str
    source_tier: SourceTier
    ingested_at: datetime


class Quote(BaseModel):
    """Latest EOD snapshot — returned by the get_quote tool."""
    scrip: Scrip
    close: float
    change: float                                   # absolute NPR vs prev close
    percent_change: float                           # signed %
    volume: int
    turnover: float
    as_of: datetime


class LiveTick(BaseModel):
    """Intraday tick from the real-time feed (simulator or live API)."""
    scrip: Scrip
    price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int = 0
    turnover: float = 0.0
    change_abs: float | None = None
    change_pct: float | None = None
    prev_close: float | None = None
    tick_at: datetime
    source: str = "simulator"


class CorporateAction(BaseModel):
    """Bonus / rights / cash-dividend / split / merger event."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    scrip: Scrip
    action_type: ActionType
    ratio: float | None = None                      # 0.125 for 12.5% bonus, split factor, etc.
    amount: float | None = None                     # per-share NPR for cash_dividend
    announcement_date: date | None = None
    book_closure_date: date | None = None
    ex_date: date | None = None
    fiscal_year_bs: FiscalYearBS | None = None
    source: str = "sharesansar"
