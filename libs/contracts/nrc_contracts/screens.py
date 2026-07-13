"""Stage 1 / Stage 2 screen results and valuation (gold tables)."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from .common import FiscalYearBS, Quarter, Scrip, TradingDate


class Stage1Result(BaseModel):
    """Output of gold.stage1_screen_results.

    Ranks scrips in their sector on profitability / revenue growth / return-ratio
    z-score components; passed=True if in top `pass_threshold_percentile` of sector."""
    model_config = ConfigDict(extra="forbid")

    scrip: Scrip
    sector: str
    fiscal_year_bs: FiscalYearBS
    quarter: Quarter

    profitability_score: float
    revenue_growth_score: float
    return_ratio_score: float
    composite_score: float

    passed: bool
    rank: int = Field(ge=1)
    computed_at: datetime


class Stage2BankResult(BaseModel):
    """Sector-aware deep screen — gold.stage2_bank_screen.

    Legacy name (kept to avoid churning the serving table / API / tool), but
    covers ALL sectors. Percentiles are computed within `sector`. BFI sectors
    (Commercial Bank, Development Bank, Finance, Microfinance) populate the
    NPL/CAR/CD ratio block; other sectors leave those NULL and are scored on
    ROE/ROA/net-margin instead."""
    model_config = ConfigDict(extra="forbid")

    scrip: Scrip
    sector: str
    fiscal_year_bs: FiscalYearBS
    quarter: Quarter

    roe: float | None = None
    roe_percentile: float | None = Field(default=None, ge=0, le=1)
    roa: float | None = None
    roa_percentile: float | None = Field(default=None, ge=0, le=1)
    net_margin: float | None = None                   # net_profit / total_revenue
    net_margin_percentile: float | None = Field(default=None, ge=0, le=1)
    npl_ratio: float | None = None
    npl_percentile: float | None = Field(default=None, ge=0, le=1)
    car: float | None = None
    car_percentile: float | None = Field(default=None, ge=0, le=1)
    cd_ratio: float | None = None
    cd_percentile: float | None = Field(default=None, ge=0, le=1)

    composite_score: float
    flags: list[str] = Field(default_factory=list)    # e.g. ["NPL_HIGH","CAR_LOW"] or ["LOSS"]
    computed_at: datetime


class Valuation(BaseModel):
    """Per-scrip per-date valuation snapshot — gold.valuation."""
    model_config = ConfigDict(extra="forbid")

    scrip: Scrip
    date: TradingDate

    pe_trailing: float | None = None
    pe_forward: float | None = None
    pb: float | None = None

    peer_pe_median: float | None = None
    peer_pb_median: float | None = None
    pe_vs_peer_pct: float | None = None               # positive = premium, negative = discount

    fair_value_forward_eps: float | None = None       # fair value estimate from forward EPS × peer P/E
    upside_pct: float | None = None

    computed_at: datetime
