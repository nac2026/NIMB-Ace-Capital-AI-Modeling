"""Quarterly fundamentals — long-format metric rows plus wide snapshot + peer rank."""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field
from .common import FiscalYearBS, Quarter, Scrip, SourceTier


class FundamentalMetric(BaseModel):
    """Long format — one row per (scrip, fy, quarter, metric_name).
    Maps 1:1 to silver.fundamentals rows.

    Monetary values are in NPR thousands (Rs. '000) — matching the client CSV
    convention (confirmed against NABIL Q4 FY 2023-24 published interim
    report). Ratios are decimal fractions (0.1438 = 14.38%). Per-share values
    are raw NPR. Share counts are in thousands of shares."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    scrip: Scrip
    fiscal_year_bs: FiscalYearBS
    quarter: Quarter
    metric_name: str                                # canonical: eps, bvps, roe, npl_ratio, ...
    value: float
    reported_date: date | None = None
    fiscal_year_ad_start: date | None = None        # AD equivalent of BS FY start for joins
    source: str = "sharesansar"
    source_tier: SourceTier | None = None
    ingested_at: datetime


class FundamentalSnapshot(BaseModel):
    """Wide format — one row per (scrip, fy, quarter). Derived from FundamentalMetric.
    Returned by the get_fundamentals tool.

    Monetary fields are in NPR thousands. Ratios in decimal fractions.
    Per-share in raw NPR. Share counts in thousands of shares."""
    scrip: Scrip
    fiscal_year_bs: FiscalYearBS
    quarter: Quarter

    # --- Income statement: revenue & margins -------------------------------
    total_revenue: float | None = None              # generic top line (non-bank sectors)
    interest_income: float | None = None
    interest_expense: float | None = None
    net_interest_income: float | None = None
    fees_income: float | None = None
    fees_expense: float | None = None
    net_fees_income: float | None = None
    net_trading_income: float | None = None
    other_operating_income: float | None = None
    total_operating_income: float | None = None
    impairment_charge: float | None = None
    net_operating_income: float | None = None

    # --- Income statement: expenses & profit -------------------------------
    staff_expenses: float | None = None
    other_operating_expenses: float | None = None
    depreciation_amortization: float | None = None
    operating_profit: float | None = None
    non_operating_income: float | None = None
    non_operating_expense: float | None = None
    profit_before_tax: float | None = None
    income_tax: float | None = None
    current_tax: float | None = None
    deferred_tax: float | None = None
    net_profit: float | None = None
    comprehensive_income: float | None = None
    distributable_profit: float | None = None

    # --- Balance sheet: assets --------------------------------------------
    total_assets: float | None = None
    cash_and_bank_balance: float | None = None
    money_at_call: float | None = None
    due_from_nrb: float | None = None
    placement_with_bfis: float | None = None
    loans_to_bfis: float | None = None
    loans_to_customers: float | None = None
    total_loans: float | None = None                # loans_to_bfis + loans_to_customers
    investments: float | None = None
    investment_securities: float | None = None
    property_equipment: float | None = None

    # --- Balance sheet: liabilities & equity ------------------------------
    total_liabilities: float | None = None
    borrowings_total: float | None = None
    due_to_bfis: float | None = None
    due_to_nrb: float | None = None
    debt_securities_issued: float | None = None
    total_deposits: float | None = None
    shareholders_equity: float | None = None
    paid_up_capital: float | None = None
    reserves_and_surplus: float | None = None
    share_premium: float | None = None
    retained_earnings: float | None = None
    reserves: float | None = None

    # --- Share counts (in thousands of shares) ----------------------------
    ordinary_shares: float | None = None
    preferred_shares: float | None = None

    # --- Derived per-share / returns / multiples --------------------------
    eps: float | None = None
    bvps: float | None = None
    roe: float | None = None
    roa: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    market_value_per_share: float | None = None     # closing price at quarter end (NPR)
    dividend_per_share: float | None = None          # DPS for the period (NPR)

    # --- Bank-specific health ratios --------------------------------------
    npl_ratio: float | None = None
    car: float | None = None                        # capital adequacy ratio
    cd_ratio: float | None = None                   # credit-to-deposit


class AdditionalInfoSnapshot(BaseModel):
    """Pre-computed quarterly bank-health metrics from the Shreyas dump.

    Parallel to FundamentalSnapshot but holds only ratio/capital fields the
    client has already derived — keeping these separate makes it explicit
    that these values came from the regulator/filing rather than being
    computed by us."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    scrip: Scrip
    fiscal_year_bs: FiscalYearBS
    quarter: Quarter

    # Health ratios (decimal fractions)
    capital_fund_to_rwa: float | None = None        # CAR
    npl_ratio: float | None = None                  # NPL / total loans
    llp_to_npl_ratio: float | None = None           # loan-loss provision coverage
    cost_of_funds: float | None = None
    cd_ratio: float | None = None                   # credit-to-deposit (NRB calc)
    base_rate: float | None = None
    avg_interest_spread: float | None = None
    avg_yield: float | None = None
    net_liquid_asset_ratio: float | None = None

    # Per-share / valuation (raw NPR)
    market_value_per_share: float | None = None
    earnings_per_share: float | None = None
    pe_ratio: float | None = None
    net_worth_per_share: float | None = None        # BVPS

    # Capital in NPR thousands
    tier1_capital: float | None = None
    tier2_capital: float | None = None
    total_capital: float | None = None

    # Ordinary share count (thousands of shares)
    ordinary_shares: float | None = None

    # Corporate actions declared for the period
    cash_dividend_pct: float | None = None
    bonus_pct: float | None = None

    source: str
    source_tier: SourceTier
    ingested_at: datetime


class PeerRanking(BaseModel):
    """A scrip's rank on one metric within its sector for one quarter.
    Maps to gold.peer_rankings_quarterly rows."""
    scrip: Scrip
    sector: str
    fiscal_year_bs: FiscalYearBS
    quarter: Quarter
    metric_name: str
    value: float
    rank_in_sector: int = Field(ge=1)
    percentile_in_sector: float = Field(ge=0, le=1)
    sector_median: float
    sector_mean: float
    computed_at: datetime
