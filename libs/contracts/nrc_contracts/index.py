"""NEPSE main index + sector sub-indices."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from .common import TradingDate


class IndexSnapshot(BaseModel):
    """Daily close of one index. Treated like a scrip with scrip=index_name.
    Maps to silver.prices with scrip IN ('NEPSE','BANKING',...) OR to its own table."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    index_name: str = Field(min_length=1, max_length=30)  # NEPSE, BANKING, DEV_BANK, HYDRO, ...
    date: TradingDate
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    turnover: float | None = Field(default=None, ge=0)
    change: float | None = None
    percent_change: float | None = None
    computed_at: datetime | None = None
