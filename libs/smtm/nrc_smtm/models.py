"""Typed views over SMTM Data API payloads.

These mirror the *wire* shape (camelCase, tolerant of unknown fields) — they are
NOT the Bronze contracts. Ingestion adapters translate these into the canonical
`nrc_contracts` models before writing Delta. Field shapes verified against the
live API on 2026-05-29 (see scripts/smtm_smoke.py)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Wire(BaseModel):
    # Tolerate fields the API adds without notice; never fail ingestion on an extra key.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Company(_Wire):
    """One row of /smtm/general/company_list."""
    company_id: int | None = Field(default=None, alias="id")
    symbol: str
    company_name: str | None = Field(default=None, alias="companyName")
    security_name: str | None = Field(default=None, alias="securityName")
    status: str | None = None                      # "A" active, "D" delisted/inactive
    sector: str | None = None                      # raw SMTM label; normalize via sectors.py
    regulatory_body: str | None = Field(default=None, alias="regulatoryBody")
    instrument_type: str | None = Field(default=None, alias="instrumentType")
    company_email: str | None = Field(default=None, alias="companyEmail")
    website: str | None = None


class LiveStock(_Wire):
    """One row of /smtm/live/stock-live-v2 (whole market in a single call)."""
    symbol: str
    sector: str | None = None
    full_name: str | None = Field(default=None, alias="fullName")
    ltp: float | None = Field(default=None, alias="latestTransactionPrice")
    ltv: float | None = Field(default=None, alias="latestTransactionVolume")
    point_change: float | None = Field(default=None, alias="pointChange")
    percentage_change: float | None = Field(default=None, alias="percentageChange")
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    previous_closing: float | None = Field(default=None, alias="previousClosing")
    timestamp: str | None = None
    year_high: float | None = Field(default=None, alias="yearHigh")
    year_low: float | None = Field(default=None, alias="yearLow")
    market_cap: float | None = Field(default=None, alias="marketCap")
    turnover: float | None = None
    transactions: int | None = None


class FloorsheetTrade(_Wire):
    """One trade from /smtm/live/floorsheet-live. `contractNumber` is monotonic and
    date-encoded (YYYYMMDD01NNNNNN) — the incremental-pull cursor."""
    serial_number: int | None = Field(default=None, alias="serialNumber")
    contract_number: int = Field(alias="contractNumber")
    stock_symbol: str = Field(alias="stockSymbol")
    buyer_broker: int = Field(alias="buyerBroker")
    seller_broker: int = Field(alias="sellerBroker")
    quantity: float
    rate: float
    amount: float
    timestamp: str

    @property
    def trade_date(self) -> str:
        """YYYY-MM-DD derived from the date-encoded contract number."""
        s = str(self.contract_number)
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


class FloorsheetPage(_Wire):
    total_count: int = Field(alias="totalCount")
    total_pages: int = Field(alias="totalPages")
    current_page: int = Field(alias="currentPage")
    data: list[FloorsheetTrade] = Field(default_factory=list)


class IndexValue(_Wire):
    """One row of /smtm/live/indices-live."""
    indices_name: str = Field(alias="indicesName")
    latest_value: float | None = Field(default=None, alias="latestValue")
    point_change: float | None = Field(default=None, alias="pointChange")
    percentage_change: float | None = Field(default=None, alias="percentageChange")
    timestamp: str | None = None
    slug_name: str | None = Field(default=None, alias="slugName")


class MarketSummary(_Wire):
    total_turnover: float | None = Field(default=None, alias="totalTurnover")
    total_traded_shares: float | None = Field(default=None, alias="totalTradedShares")
    total_transactions: int | None = Field(default=None, alias="totalTransactions")
    total_scrips_traded: int | None = Field(default=None, alias="totalScripsTraded")
    float_market_cap: float | None = Field(default=None, alias="floatMarketCap")
    market_cap: float | None = Field(default=None, alias="marketCap")
    timestamp: str | None = None


class Broker(_Wire):
    """One row of /smtm/general/broker_list — the authoritative NEPSE broker
    directory (code → firm name + logo). Replaces the hand-seeded reference."""
    broker: int = Field(alias="brokerNumber")
    name: str = Field(alias="brokerName")
    icon: str | None = None                        # logo path, e.g. images.smtmcapital.com.np/logos/1.png


class TimeseriesPoint(_Wire):
    """One point of /smtm/live/stock-timeseries/{symbol} — an intraday minute bar
    for the CURRENT session only (newest-first). Not multi-day history."""
    symbol: str | None = None
    timestamp: str                                 # "YYYY-MM-DD HH:MM:SS"
    closing_price: float | None = Field(default=None, alias="closingPrice")
    volume: float | None = None
    amount: float | None = None


class IndexTimeseriesPoint(_Wire):
    """One point of /smtm/live/indices-timeseries/{slugName}."""
    indices_name: str | None = Field(default=None, alias="indicesName")
    slug_name: str | None = Field(default=None, alias="slugName")
    timestamp: str
    value: float | None = None
    turnover: float | None = None


class KeyStatsRow(_Wire):
    """One period of /smtm/financials/get-{annual,quarterly}-key-stats/{ticker}.

    The wire schema is broad and sector-dependent (banking rows carry NPL/CAR,
    others don't). We type the cross-sector subset the UI charts and ignore the
    rest. `Year` is a fiscal label like "2024/25"; `Quarter` is 1-4."""
    ticker: str | None = Field(default=None, alias="Ticker")
    year: str | None = Field(default=None, alias="Year")
    quarter: int | None = Field(default=None, alias="Quarter")
    data_source: str | None = Field(default=None, alias="DataSource")   # Audited / Published
    total_revenue: float | None = Field(default=None, alias="TotalRevenue")
    net_income: float | None = Field(default=None, alias="NetIncome")
    net_income_margin: float | None = Field(default=None, alias="NetIncomeMargin")
    gross_profit_margin: float | None = Field(default=None, alias="GrossProfitMargin")
    roa: float | None = Field(default=None, alias="ReturnOnAsset")
    roe: float | None = Field(default=None, alias="ReturnOnEquity")
    eps: float | None = Field(default=None, alias="EpsAnnualized")
    pe: float | None = Field(default=None, alias="ReportedPeAnnualized")
    book_value_per_share: float | None = Field(default=None, alias="BookValuePerShare")
    dividend_per_share: float | None = Field(default=None, alias="DividendPerShare")
    market_cap: float | None = Field(default=None, alias="MarketCapitalization")
    mps: float | None = Field(default=None, alias="Mps")
    npl: float | None = Field(default=None, alias="NonPerformingLoanNplToTotalLoan")
    capital_adequacy: float | None = Field(default=None, alias="CapitalFundToRwa")
