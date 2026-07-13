"""Scrip master — static reference data per listed company."""
from __future__ import annotations
from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from .common import Scrip


class ScripMaster(BaseModel):
    """One row per listed scrip. Maps to silver.scrips / Postgres `scrips` serving table."""
    model_config = ConfigDict(extra="forbid")

    scrip: Scrip
    company_name: str
    sector: str                                      # one of nrc_contracts.common.SECTORS
    sub_sector: str | None = None

    # Share structure
    listed_shares: float | None = Field(default=None, ge=0)   # total listed
    paid_up_value: float | None = Field(default=None, ge=0)   # face value per share (usually 100)
    paid_up_capital: float | None = Field(default=None, ge=0) # total (= listed_shares × paid_up_value)
    promoter_shares: float | None = Field(default=None, ge=0)
    public_shares: float | None = Field(default=None, ge=0)
    isin: str | None = None

    # Corporate
    registered_date: date | None = None              # listing / operation date
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    website: str | None = None

    is_active: bool = True
    company_id: int | None = None                    # Sharesansar internal numeric id
