"""Floor-sheet: NEPSE's per-trade record (buyer broker, seller broker, qty, rate).

This is the microstructure dataset that powers broker-flow, accumulation, and
manipulation/speculation detection — NIMB Ace's most distinctive data edge.
One row per executed trade. `contract_number` is the unique key (monotonic,
date-encoded by SMTM). Maps to bronze.floorsheet_raw → silver.floorsheet."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from .common import Scrip, SourceTier, TradingDate


class FloorsheetTrade(BaseModel):
    """One executed NEPSE trade. Buyer/seller brokers are integer broker IDs."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    scrip: Scrip
    contract_number: int = Field(gt=0)              # unique, monotonic, date-encoded
    serial_number: int | None = Field(default=None, ge=0)
    buyer_broker: int = Field(ge=0)
    seller_broker: int = Field(ge=0)
    quantity: float = Field(gt=0)
    rate: float = Field(gt=0)                        # price per share, NPR
    amount: float = Field(ge=0)                      # quantity × rate, NPR
    traded_at: datetime                              # full trade timestamp
    trade_date: TradingDate                          # partition key
    source: str = "smtm"
    source_tier: SourceTier | None = None
    ingested_at: datetime
