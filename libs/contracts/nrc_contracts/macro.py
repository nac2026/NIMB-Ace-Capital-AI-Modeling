"""Macroeconomic indicators (monthly). Schema defined now; scraper deferred per scope."""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class MacroIndicator(BaseModel):
    """One observation of one indicator on one date.
    Maps 1:1 to silver.macro rows."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    indicator: str = Field(min_length=1)
    # Canonical names: policy_rate, crr, slr, inflation_cpi, m2, remittance,
    # forex_reserve, interbank_rate, tbill_91day, base_rate_banking_sector
    date: date                                       # first of month for monthly indicators
    value: float
    unit: str                                        # "%", "NPR_billion", etc.
    source: str = "nrb"
    ingested_at: datetime
