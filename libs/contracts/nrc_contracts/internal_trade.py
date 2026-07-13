"""Internal trade book: NIMB Ace Capital's own executed trades (the firm's fills).

One row per executed fill from the firm's daily trade-book dump. `contract_number`
is the NEPSE contract id — the SAME key as `silver.floorsheet.contract_number` — so
joining the two recovers the broker the fund traded through and the counterparty
broker for every internal trade. That join is the spine of internal-trade
surveillance (bad fills, trading into manipulated names, collusion-proxy signals).

Attribution is at the fund/portfolio level (`client_code` / `client_name`), not the
individual dealer. Maps to bronze.internal_trades_raw → silver.internal_trades."""
from __future__ import annotations
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Scrip, SourceTier, TradingDate


class InternalTrade(BaseModel):
    """One executed fill from the firm's trade book. `side` is 'B' (Buy) or 'S' (Sell)."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    scrip: Scrip
    contract_number: int = Field(gt=0)              # NEPSE contract id — joins silver.floorsheet
    client_code: str = Field(min_length=1)          # the managed fund/portfolio account
    client_name: str = Field(min_length=1)
    side: Literal["B", "S"]                         # B = Buy, S = Sell
    price: float = Field(gt=0)                       # fill price per share, NPR
    quantity: float = Field(gt=0)                    # shares filled
    value: float = Field(ge=0)                       # price × quantity, NPR
    order_id: int = Field(ge=0)                      # groups fills of one parent order
    traded_at: datetime                              # fill timestamp (NPT-local)
    trade_date: TradingDate                          # partition key
    source: str = "client_internal"
    source_tier: SourceTier | None = None
    ingested_at: datetime
