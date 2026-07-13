# NEPSE Research Platform — Data Contract & Catalog

*A reference document for the Shreyas / data-vendor team, describing what the NEPSE Research Platform currently ingests, the schema conventions future drops must follow, and the additional data domains we would like to explore. Intended to be returned as a marked-up checklist.*

**Recipient:** Shreyas & data-vendor team
**From:** NIMB Ace Capital — Platform Engineering
**Version:** v1 · April 2026
**Action requested:** Review §4, §5, and §8. Fill in the checkbox columns indicating what you can provide, and at what cadence. Return the marked-up document.

---

## 1 · Purpose

The NEPSE Research Platform is a fully automated pipeline. Every vendor drop flows through the same stages — Bronze → Silver → Gold → serving DB → research UI — without manual intervention beyond the initial file delivery.

To keep the pipeline automatic and stable, we need three things from every dataset the vendor provides:

1. **A stable schema.** The same column names, in the same positions, with the same data types and units, across every drop.
2. **A predictable cadence.** Known delivery windows so downstream jobs can be scheduled safely.
3. **A machine-readable drop location.** A shared SFTP or S3 bucket where files appear under a conventional folder layout — replacing the current manual OneDrive flow.

This document describes what we currently receive, what we need regularly, what we would like to explore adding, and the schema conventions any new dataset must satisfy.

The document covers **data** only — what domains, what fields, what units, what cadence. It does not discuss how the platform uses the data downstream.

---

## 2 · Delivery format conventions

Any CSV (existing or new) provided to the platform must follow these rules. These are non-negotiable once a dataset is wired in — changes to any of them break the automated ingest.

### 2.1 · File format

| Requirement | Specification |
|---|---|
| Encoding | UTF-8 (no BOM) |
| Delimiter | Comma (`,`) |
| Quoting | RFC 4180 — double-quote any field containing commas, line breaks, or double quotes (which themselves become `""`) |
| Line ending | `\n` (Unix) or `\r\n` (Windows) — parser accepts either, but be consistent within a single file |
| Header row | Required — row 1 is column names |
| Empty lines | Not permitted mid-file |

### 2.2 · Column naming

| Rule | Example |
|---|---|
| lowercase snake_case | `total_assets`, `npl_ratio`, `fiscal_year_bs` |
| No units in column names (units documented separately) | `total_assets` (not `total_assets_rs_000`) |
| No spaces, parentheses, slashes, or special characters | `price_to_earnings_ratio` (not `P/E Ratio (TTM)`) |
| Consistent name across all files in the same dataset family | `scrip` everywhere, not a mix of `ticker` / `symbol` / `Ticker` |

### 2.3 · Key columns (mandatory on every row)

| Column | Type | Example | Notes |
|---|---|---|---|
| `scrip` | VARCHAR(20) | `NABIL` | Uppercase NEPSE ticker; **not** the full company name |
| `fiscal_year_bs` | INTEGER | `2082` | 4-digit Bikram Sambat year (first year of the FY, e.g. FY 2082/83 = `2082`) |
| `quarter` | INTEGER | `1`..`4` | Integer 1–4, not `Q1` / `Q2` strings |
| `date` | DATE | `2026-04-15` | ISO-8601 `YYYY-MM-DD`, AD calendar |

For datasets with a different grain, document the key columns in the file header comment and in this contract.

### 2.4 · Units & conventions

| Domain | Convention | Example |
|---|---|---|
| Monetary values | **NPR thousands** unless the dataset explicitly states otherwise. Never mix units within a single file. | `total_assets = 697025625` means NPR 697.02 billion |
| Ratios & percentages | **Decimal fractions**. `0.1438` means 14.38%. | `roe = 0.1438` |
| Per-share values | **Raw NPR**. | `eps = 85.24` means NPR 85.24 per share |
| Share counts | **Thousands of shares**. | `ordinary_shares = 243857` means 243.857 million shares |
| Dates | `YYYY-MM-DD` AD. If BS, suffix the column with `_bs` and document in a header comment. | `announcement_date = 2026-04-15` |
| Null values | **Empty string** (`,,`). Do not use `NA`, `N/A`, `-`, `NULL`, or `0`. Null ≠ zero. | `,net_profit,` — not `,NA,` |
| Restatements | Include a boolean column `is_restatement` (0/1) and re-deliver the file. Don't silently overwrite prior-quarter figures. | `is_restatement = 1` on restated rows |

### 2.5 · File naming

Pattern: `<dataset>_<YYYYMMDD>.csv` where `YYYYMMDD` is the drop date.

Examples:
- `cbbalancesheet2_20260424.csv`
- `cbincomestatement_20260424.csv`
- `daily_bars_20260424.csv`

Multiple files of the same family in the same drop folder are rejected — keep only the latest.

---

## 3 · What we have today (Inventory)

Datasets currently flowing into the platform, with their current schema and status.

### 3.1 · Shreyas tidy quarterly CSVs — `CLIENT_AUTHORITATIVE` tier

Three files, one per financial statement section. Keyed on (Ticker, Year, Quarter). Monetary in NPR thousands; ratios as decimals. Silver treats this as the top source tier — these rows beat any scraped or Format B row covering the same key.

| File | Grain | Cadence today | Key fields (sample) | Status |
|---|---|---|---|---|
| `cbbalancesheet2_*.csv` | (scrip, fy, q) | Quarterly, ad-hoc | `Ticker, Year, Quarter, TotalAssets, CashAndBankBalance, Loans, Deposits, …` ~45 columns | ✓ Receiving |
| `cbincomestatement_*.csv` | (scrip, fy, q) | Quarterly, ad-hoc | `Ticker, Year, Quarter, InterestIncome, NetProfit, OperatingProfit, …` ~30 columns | ✓ Receiving |
| `cbadditionalinfo_*.csv` | (scrip, fy, q) | Quarterly, ad-hoc | `Ticker, Year, Quarter, CAR, NPL, CostOfFunds, MVPS, EPS, PE, BVPS, cash_dividend_pct, bonus_pct, tier1_capital, tier2_capital` ~19 columns | ✓ Receiving |

Coverage: FY 2020/21 → present. Silver destination: `silver.fundamentals` (long) + `silver.additional_info` (wide).

> **Open question for the vendor:** Can these three files be delivered on a committed cadence (e.g. within 15 days of NEPSE-filing deadline) rather than ad-hoc?

### 3.2 · Format B wide historical CSVs — `CLIENT_HISTORICAL` tier

Historical backfill, one CSV per scrip per statement, wide-pivoted with year/quarter columns and metric rows below. Coverage: FY 2010/11 → present. Loses to Shreyas at Silver-merge time for any overlapping key.

| Folder | File pattern | Grain | Cadence | Status |
|---|---|---|---|---|
| `Commercial bank key stats/` | `<TICKER>.csv` | (scrip, fy, q) | One-off backfill | ✓ Historical received |
| `Commercial bank balance sheet/` | `<TICKER>.csv` | (scrip, fy, q) | One-off backfill | ✓ Historical received |
| `Commercial bank Income Statement/` | `<TICKER>.csv` | (scrip, fy, q) | One-off backfill | ✓ Historical received |

> **Open question for the vendor:** Once the Shreyas tidy format covers a quarter, Format B is no longer needed for that quarter. Can we agree that Format B is a one-off historical backfill and future drops are Shreyas-format only?

### 3.3 · Format B close-only price CSVs — `CLIENT_HISTORICAL` tier

One file per scrip. Headerless, two columns: `date, close`. Coverage: 2011-07-17 → present.

| Path | Grain | Cadence | Status |
|---|---|---|---|
| `Commercial bank Price 5 years/<TICKER>.csv` | (scrip, date) | One-off backfill | ✓ Historical received |

Silver destination: `silver.closes`. Kept separate from `silver.prices` (which requires full OHLCV) so downstream consumers of candlestick data never silently read a null high/low.

> **Open question for the vendor:** Going forward we'd like full OHLCV (see §4.2) — is close-only continuing, or is it being replaced?

---

## 4 · What we need on a regular cadence (Requirements)

The platform runs a daily end-of-day batch. To run without manual intervention, the following items must arrive on a predictable schedule at a predictable location. Each item lists our target format, cadence, and delay SLA.

For each item, please tick the relevant checkbox under **"Can provide regular?"** in §8, or annotate with what's feasible.

### 4.1 · Quarterly fundamentals (Shreyas tidy format)

| Attribute | Specification |
|---|---|
| Format | Three CSVs per drop (`cbbalancesheet2_*`, `cbincomestatement_*`, `cbadditionalinfo_*`) |
| Grain | (scrip, fiscal_year_bs, quarter) |
| Coverage per drop | All 19 active Commercial Banks, latest completed quarter |
| Target cadence | Quarterly |
| Target SLA | Within **15 calendar days** of the quarter-end NEPSE filing deadline |
| Schema | As §3.1 — no column name or unit changes without 30-day notice |

### 4.2 · Daily EOD bars

OHLCV + turnover + trade count. This is the backbone of every technical, return, and valuation calculation.

| Attribute | Specification |
|---|---|
| Format | One CSV per trading day, all 19 scrips |
| File name | `daily_bars_<YYYYMMDD>.csv` |
| Columns | `scrip, date, open, high, low, close, volume, turnover, num_transactions, previous_close` |
| Units | Prices in raw NPR (not thousands), `volume` in shares, `turnover` in raw NPR |
| Grain | (scrip, date) |
| Target cadence | Every NEPSE trading day |
| Target SLA | Same day, by **18:00 NPT** |

> Currently this comes from the Sharesansar scraper. Migrating to a vendor-provided feed removes scraper fragility.

### 4.3 · Corporate actions

Cash dividends, bonus shares, rights issues, splits, mergers.

| Attribute | Specification |
|---|---|
| Format | Single CSV, append-only |
| File name | `corporate_actions_<YYYYMMDD>.csv` |
| Columns | `scrip, action_type, ratio, amount, announcement_date, book_closure_date, ex_date, fiscal_year_bs, source` |
| `action_type` values | `cash_dividend` / `bonus_share` / `rights_share` / `split` / `merger` |
| `ratio` | Decimal (0.125 = 12.5%) for bonus / rights / split |
| `amount` | NPR per share for `cash_dividend` |
| Cadence | As events occur |
| Target SLA | Within **3 business days** of the company board decision |

### 4.4 · Sector & market indices

NEPSE main index and all sector sub-indices (Commercial Banking, Development Banking, Finance, Insurance, Hydropower, Manufacturing, Hotels, Trading, Others, Microfinance).

| Attribute | Specification |
|---|---|
| Format | One CSV per trading day |
| File name | `indices_<YYYYMMDD>.csv` |
| Columns | `index_name, date, open, high, low, close, change, percent_change, turnover` |
| Grain | (index_name, date) |
| Target cadence | Every NEPSE trading day |
| Target SLA | Same day, by **18:00 NPT** |

### 4.5 · Scrip master updates

Listings, delistings, name changes, sector re-classifications, share-structure updates (new issues, buybacks).

| Attribute | Specification |
|---|---|
| Format | Delta CSV — only changed rows |
| File name | `scrip_master_delta_<YYYYMMDD>.csv` |
| Columns | `scrip, company_name, sector, sub_sector, listed_shares, paid_up_capital, paid_up_value, promoter_shares, public_shares, isin, registered_date, is_active, change_reason, effective_date` |
| Cadence | As changes occur |
| Target SLA | On the effective date |

### 4.6 · Fiscal calendar corrections & restatements

When a company restates prior-quarter figures (audit adjustments, reclassifications).

| Attribute | Specification |
|---|---|
| Format | Re-deliver the affected Shreyas files with `is_restatement = 1` on restated rows |
| Cadence | Ad-hoc |
| Target SLA | Within 5 business days of the restated filing |

### 4.7 · Checklist — §4 (vendor, please respond)

| Item | Can provide at target cadence / SLA? | Notes |
|---|---|---|
| 4.1 Quarterly fundamentals (Shreyas) within 15 days of filing | [ ] Yes  [ ] Partially  [ ] No | |
| 4.2 Daily EOD bars by 18:00 NPT | [ ] Yes  [ ] Partially  [ ] No | |
| 4.3 Corporate actions within 3 business days | [ ] Yes  [ ] Partially  [ ] No | |
| 4.4 Index daily closes by 18:00 NPT | [ ] Yes  [ ] Partially  [ ] No | |
| 4.5 Scrip master delta on effective date | [ ] Yes  [ ] Partially  [ ] No | |
| 4.6 Restatements with `is_restatement` flag | [ ] Yes  [ ] Partially  [ ] No | |

---

## 5 · What would extend the platform (Nice-to-have)

Data domains the platform team has identified as high-value additions. Most trace back to specific research-framework categories. For each item, please tick a feasibility in §8.

### 5.1 · Market microstructure

| Item | Expected shape |
|---|---|
| **Broker-wise net flows per scrip per day** | `(scrip, date, broker_id, broker_name, net_bought_shares, net_bought_value, buy_volume, sell_volume)` |
| **Floor-sheet / transaction tape** | Per-trade or per-minute: `(scrip, trade_time, price, quantity, buyer_broker_id, seller_broker_id, trade_type)` |
| **Circuit-touch events** | `(scrip, date, circuit_direction, limit_price, time_hit, time_released)` |
| **Intraday volume profile** | OHLCV at 1-min / 5-min / 15-min resolution |
| **Upper/lower-circuit dependency** | Daily counts of days closed at circuit limits per scrip |

### 5.2 · Float & supply

| Item | Expected shape |
|---|---|
| **Public float vs promoter split** | `(scrip, date, public_shares, promoter_shares, locked_in_shares, free_float_shares)` |
| **Locked-in share schedule** | `(scrip, lock_in_start, lock_in_end, shares_locked, reason)` |
| **Lock-in expiry calendar** | Forward-looking view of §above for planning |
| **Promoter pledging status** | `(scrip, date, shares_pledged, pledgor, pledgee)` |
| **Insider transactions** | `(scrip, transaction_date, insider_name, role, transaction_type, shares, price)` |

### 5.3 · Deeper income-statement / balance-sheet

| Item | Expected shape |
|---|---|
| **Segment-wise revenue** | `(scrip, fy, q, segment_name, revenue, operating_income)` — branches, products, geographies |
| **Operating cash flow** | Direct or indirect cash flow statement rows per quarter |
| **One-off income flags** | Which line items in a quarter are non-recurring |
| **FX exposure breakdown** | Loan book / investment portfolio split by currency |
| **Debt maturity ladder** | `(scrip, fy, q, maturity_bucket, amount)` — < 1 year, 1-3 years, 3-5 years, > 5 years |
| **Revaluation reserve movement** | `(scrip, fy, q, reserve_type, opening_balance, additions, transfers, closing_balance)` |

### 5.4 · Governance & integrity

| Item | Expected shape |
|---|---|
| **Related-party transactions** | `(scrip, fy, q, related_party_name, transaction_type, amount)` |
| **Auditor qualifications / flags** | `(scrip, fy, auditor_name, has_qualification, qualification_text)` |
| **Board meeting outcomes** | `(scrip, meeting_date, decision_text, declared_actions)` |
| **Board composition changes** | `(scrip, effective_date, member_name, role, action_type)` |

### 5.5 · Corporate actions — richer

| Item | Expected shape |
|---|---|
| **Announced vs executed dates** | Separate `announcement_date`, `record_date`, `book_closure_date`, `ex_date` for every action |
| **Rights issue calendars** | `(scrip, rights_ratio, offer_price, open_date, close_date)` |
| **Merger / acquisition notes** | `(scrip, counterparty, action_type, swap_ratio, effective_date, notes)` |

### 5.6 · Regulatory & macro

| Item | Expected shape |
|---|---|
| **SEBON circular feed** | `(circular_id, issued_date, effective_date, title, affected_sectors, summary, full_text_url)` |
| **NRB policy circulars** | Same shape, issuer = NRB |
| **Treasury-yield curve daily** | `(date, tenor_months, yield_pct)` — 3M, 6M, 1Y, 5Y, 10Y |
| **Policy / base rate daily** | `(date, rate_name, rate_value)` — NRB repo, reverse repo, CRR, SLR |
| **CPI, GDP, remittance monthly** | `(month, metric, value, units)` |

### 5.7 · News & announcements

| Item | Expected shape |
|---|---|
| **Company disclosures** | `(scrip, published_at, disclosure_type, title, body_text, source_url)` |
| **NEPSE announcements** | `(announcement_id, published_at, scope, affected_scrips, title, body)` |
| **Press releases** | `(scrip, published_at, title, body, source)` |

### 5.8 · Streaming / real-time

| Item | Expected shape |
|---|---|
| **Live quote ticks** | `(scrip, tick_time, price, open, high, low, volume, turnover, change_abs, change_pct, prev_close)` — WebSocket or FIX preferred |
| **Floor-sheet live feed** | Same shape as 5.1 floor-sheet but streaming |
| **Intraday index snapshots** | Per-minute NEPSE / sector index values |
| **Delivery protocol options** | WebSocket JSON · FIX · REST long-poll — please indicate what's available |

### 5.9 · NIMB internal systems (not from external vendor — flagged for completeness)

| Item | Expected shape |
|---|---|
| **Approved investment list** | `(scrip, approval_date, approval_status, approved_by, notes)` — from the internal compliance system |
| **Historical order placement** | `(order_id, placed_at, scrip, side, quantity, price, order_type, decision_rationale)` — for backtesting future System B |
| **Portfolio holdings snapshot** | `(portfolio_id, scrip, shares, cost_basis, purchase_date)` |

### 5.10 · Checklist — §5 (vendor, please respond)

Feel free to skip rows outside your scope; annotate source suggestions for us to pursue separately.

| Item | Have today? | Can provide regular? | One-off dump? | Not possible | Notes |
|---|---|---|---|---|---|
| 5.1 Broker-wise net flows | [ ] | [ ] | [ ] | [ ] | |
| 5.1 Floor-sheet / transaction tape | [ ] | [ ] | [ ] | [ ] | |
| 5.1 Circuit-touch events | [ ] | [ ] | [ ] | [ ] | |
| 5.1 Intraday volume profile | [ ] | [ ] | [ ] | [ ] | |
| 5.2 Public float vs promoter split | [ ] | [ ] | [ ] | [ ] | |
| 5.2 Locked-in share schedule | [ ] | [ ] | [ ] | [ ] | |
| 5.2 Lock-in expiry calendar | [ ] | [ ] | [ ] | [ ] | |
| 5.2 Promoter pledging | [ ] | [ ] | [ ] | [ ] | |
| 5.2 Insider transactions | [ ] | [ ] | [ ] | [ ] | |
| 5.3 Segment-wise revenue | [ ] | [ ] | [ ] | [ ] | |
| 5.3 Operating cash flow | [ ] | [ ] | [ ] | [ ] | |
| 5.3 One-off income flags | [ ] | [ ] | [ ] | [ ] | |
| 5.3 FX exposure breakdown | [ ] | [ ] | [ ] | [ ] | |
| 5.3 Debt maturity ladder | [ ] | [ ] | [ ] | [ ] | |
| 5.3 Revaluation reserve | [ ] | [ ] | [ ] | [ ] | |
| 5.4 Related-party transactions | [ ] | [ ] | [ ] | [ ] | |
| 5.4 Auditor qualifications | [ ] | [ ] | [ ] | [ ] | |
| 5.4 Board meeting outcomes | [ ] | [ ] | [ ] | [ ] | |
| 5.4 Board composition changes | [ ] | [ ] | [ ] | [ ] | |
| 5.5 Announced vs executed dates | [ ] | [ ] | [ ] | [ ] | |
| 5.5 Rights issue calendars | [ ] | [ ] | [ ] | [ ] | |
| 5.5 Merger / acquisition notes | [ ] | [ ] | [ ] | [ ] | |
| 5.6 SEBON circulars | [ ] | [ ] | [ ] | [ ] | |
| 5.6 NRB circulars | [ ] | [ ] | [ ] | [ ] | |
| 5.6 Treasury-yield curve | [ ] | [ ] | [ ] | [ ] | |
| 5.6 Policy / base rate | [ ] | [ ] | [ ] | [ ] | |
| 5.6 CPI / GDP / remittance | [ ] | [ ] | [ ] | [ ] | |
| 5.7 Company disclosures | [ ] | [ ] | [ ] | [ ] | |
| 5.7 NEPSE announcements | [ ] | [ ] | [ ] | [ ] | |
| 5.7 Press releases | [ ] | [ ] | [ ] | [ ] | |
| 5.8 Live quote ticks | [ ] | [ ] | [ ] | [ ] | |
| 5.8 Floor-sheet live feed | [ ] | [ ] | [ ] | [ ] | |
| 5.8 Intraday index snapshots | [ ] | [ ] | [ ] | [ ] | |
| 5.9 Approved investment list (internal) | [ ] | [ ] | [ ] | [ ] | |
| 5.9 Historical order placement (internal) | [ ] | [ ] | [ ] | [ ] | |
| 5.9 Portfolio holdings (internal) | [ ] | [ ] | [ ] | [ ] | |

---

## 6 · Schema conventions reference

The canonical schemas the Silver layer normalizes every source into. Future drops are validated against these shapes — any new dataset should fit, or we jointly extend the contract.

### 6.1 · Scrip master — static reference

| Column | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `scrip` | VARCHAR(20) | — | No | Uppercase NEPSE ticker |
| `company_name` | VARCHAR(200) | — | No | Full legal name |
| `sector` | VARCHAR(50) | — | No | Controlled vocabulary |
| `sub_sector` | VARCHAR(50) | — | Yes | |
| `listed_shares` | BIGINT | shares (thousands) | Yes | |
| `paid_up_value` | NUMERIC(10,2) | NPR per share | Yes | Face value, usually 100 |
| `paid_up_capital` | BIGINT | NPR thousands | Yes | = listed_shares × paid_up_value |
| `promoter_shares` | BIGINT | shares (thousands) | Yes | |
| `public_shares` | BIGINT | shares (thousands) | Yes | |
| `isin` | VARCHAR(20) | — | Yes | |
| `registered_date` | DATE | — | Yes | Listing date |
| `is_active` | BOOLEAN | — | No | Default true |

### 6.2 · Daily bar — OHLCV

| Column | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `scrip` | VARCHAR(20) | — | No | |
| `date` | DATE | AD | No | |
| `open` | NUMERIC(12,4) | NPR per share | No | > 0 |
| `high` | NUMERIC(12,4) | NPR per share | No | > 0 |
| `low` | NUMERIC(12,4) | NPR per share | No | > 0 |
| `close` | NUMERIC(12,4) | NPR per share | No | > 0 |
| `volume` | BIGINT | shares | No | ≥ 0 |
| `turnover` | NUMERIC(18,2) | NPR | No | ≥ 0 (= price × shares) |
| `num_transactions` | INTEGER | count | Yes | ≥ 0 |
| `previous_close` | NUMERIC(12,4) | NPR per share | Yes | |
| `vwap` | NUMERIC(12,4) | NPR per share | Yes | |
| `adjusted_close` | NUMERIC(12,4) | NPR per share | Yes | Corporate-action adjusted |

### 6.3 · Fundamentals snapshot — quarterly (wide)

All monetary fields NPR thousands. All ratios decimal fractions. Per-share values raw NPR. Share counts in thousands of shares. One row per (scrip, fiscal_year_bs, quarter).

Key columns: `scrip`, `fiscal_year_bs`, `quarter`.

**Income statement — revenue & margins (NPR thousands):**
`interest_income, interest_expense, net_interest_income, fees_income, fees_expense, net_fees_income, net_trading_income, other_operating_income, total_operating_income, impairment_charge, net_operating_income`

**Income statement — expenses & profit (NPR thousands):**
`staff_expenses, other_operating_expenses, depreciation_amortization, operating_profit, non_operating_income, non_operating_expense, profit_before_tax, income_tax, current_tax, deferred_tax, net_profit, comprehensive_income, distributable_profit`

**Balance sheet — assets (NPR thousands):**
`total_assets, cash_and_bank_balance, money_at_call, due_from_nrb, placement_with_bfis, loans_to_bfis, loans_to_customers, total_loans, investments, investment_securities, property_equipment`

**Balance sheet — liabilities & equity (NPR thousands):**
`total_liabilities, borrowings_total, due_to_bfis, due_to_nrb, debt_securities_issued, total_deposits, shareholders_equity, paid_up_capital, reserves_and_surplus, share_premium, retained_earnings, reserves`

**Share counts (thousands of shares):** `ordinary_shares, preferred_shares`

**Derived (raw NPR / decimal):** `eps, bvps, roe, roa, pe_ratio, pb_ratio`

**Bank-specific health ratios (decimal):** `npl_ratio, car, cd_ratio`

### 6.4 · Additional info — quarterly bank health

| Column | Unit | Notes |
|---|---|---|
| `capital_fund_to_rwa` | decimal | CAR |
| `npl_ratio` | decimal | |
| `llp_to_npl_ratio` | decimal | Loan-loss provision coverage |
| `cost_of_funds` | decimal | |
| `cd_ratio` | decimal | NRB-calculated |
| `base_rate` | decimal | |
| `avg_interest_spread` | decimal | |
| `avg_yield` | decimal | |
| `net_liquid_asset_ratio` | decimal | |
| `market_value_per_share` | NPR raw | MVPS |
| `earnings_per_share` | NPR raw | EPS |
| `pe_ratio` | decimal | |
| `net_worth_per_share` | NPR raw | BVPS |
| `tier1_capital` | NPR thousands | |
| `tier2_capital` | NPR thousands | |
| `total_capital` | NPR thousands | |
| `ordinary_shares` | shares (thousands) | |
| `cash_dividend_pct` | decimal | Rate on par |
| `bonus_pct` | decimal | Rate on par |

### 6.5 · Corporate action

| Column | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| `scrip` | VARCHAR(20) | — | No | |
| `action_type` | VARCHAR(30) | — | No | `cash_dividend` / `bonus_share` / `rights_share` / `split` / `merger` |
| `ratio` | NUMERIC(10,6) | decimal | Yes | 0.125 for 12.5% bonus |
| `amount` | NUMERIC(12,4) | NPR per share | Yes | For cash_dividend |
| `announcement_date` | DATE | AD | Yes | |
| `book_closure_date` | DATE | AD | Yes | |
| `ex_date` | DATE | AD | Yes | |
| `fiscal_year_bs` | INTEGER | BS | Yes | |

---

## 7 · Drop-location & delivery mechanism

Target end-state: all vendor drops arrive at a shared SFTP or S3 bucket under a conventional folder layout. This replaces the current manual OneDrive workflow, removes the "someone has to move files" step, and lets the pipeline pick up new drops automatically.

### 7.1 · Proposed folder layout (vendor-facing)

```
incoming/
├── fundamentals/
│   └── YYYYMMDD/
│       ├── cbbalancesheet2_YYYYMMDD.csv
│       ├── cbincomestatement_YYYYMMDD.csv
│       └── cbadditionalinfo_YYYYMMDD.csv
├── daily_bars/
│   └── YYYY/MM/daily_bars_YYYYMMDD.csv
├── corporate_actions/
│   └── YYYYMMDD/corporate_actions_YYYYMMDD.csv
├── indices/
│   └── YYYY/MM/indices_YYYYMMDD.csv
├── scrip_master/
│   └── YYYYMMDD/scrip_master_delta_YYYYMMDD.csv
└── restatements/
    └── YYYYMMDD/<original_file_name>.csv
```

### 7.2 · Delivery-mechanism checklist

| Mechanism | Vendor can support? | Notes |
|---|---|---|
| SFTP with public-key auth | [ ] Yes  [ ] No | NIMB provisions the server; vendor uploads |
| S3 bucket (AWS) with IAM role | [ ] Yes  [ ] No | NIMB provisions the bucket; vendor receives credentials |
| S3-compatible MinIO (hosted) | [ ] Yes  [ ] No | Same model, NIMB-hosted |
| Continue OneDrive (manual) | [ ] Yes  [ ] No | Current fallback; we prefer to migrate away |

### 7.3 · Delivery notifications

Optional but highly useful: a webhook or email notification to `data-platform@nimb.com.np` when a new drop is complete (so the pipeline can trigger immediately instead of waiting for the next scheduled scan).

| Notification | Vendor can support? |
|---|---|
| Webhook POST to configured URL | [ ] Yes  [ ] No |
| Email to configured address | [ ] Yes  [ ] No |
| Neither (pipeline polls) | [ ] Acceptable |

---

## 8 · Checklist summary

Consolidated checklist. Please fill in the last four columns for every row and return. Free-text column is for caveats, timing commitments, alternative fields, or anything else we should know.

### 8.1 · Required, regular

| # | Item | Have today | Can provide regular | Can provide one-off | Not possible | Notes |
|---|---|:---:|:---:|:---:|:---:|---|
| 4.1 | Quarterly fundamentals (Shreyas) by day+15 | [ ] | [ ] | [ ] | [ ] | |
| 4.2 | Daily EOD bars by 18:00 NPT | [ ] | [ ] | [ ] | [ ] | |
| 4.3 | Corporate actions within 3 business days | [ ] | [ ] | [ ] | [ ] | |
| 4.4 | Index daily closes by 18:00 NPT | [ ] | [ ] | [ ] | [ ] | |
| 4.5 | Scrip master delta on effective date | [ ] | [ ] | [ ] | [ ] | |
| 4.6 | Restatements with flag | [ ] | [ ] | [ ] | [ ] | |

### 8.2 · Nice-to-have

| # | Item | Have today | Can provide regular | Can provide one-off | Not possible | Notes |
|---|---|:---:|:---:|:---:|:---:|---|
| 5.1 | Broker-wise net flows | [ ] | [ ] | [ ] | [ ] | |
| 5.1 | Floor-sheet / transaction tape | [ ] | [ ] | [ ] | [ ] | |
| 5.1 | Circuit-touch events | [ ] | [ ] | [ ] | [ ] | |
| 5.1 | Intraday volume profile | [ ] | [ ] | [ ] | [ ] | |
| 5.2 | Public float vs promoter split | [ ] | [ ] | [ ] | [ ] | |
| 5.2 | Locked-in share schedule | [ ] | [ ] | [ ] | [ ] | |
| 5.2 | Lock-in expiry calendar | [ ] | [ ] | [ ] | [ ] | |
| 5.2 | Promoter pledging | [ ] | [ ] | [ ] | [ ] | |
| 5.2 | Insider transactions | [ ] | [ ] | [ ] | [ ] | |
| 5.3 | Segment-wise revenue | [ ] | [ ] | [ ] | [ ] | |
| 5.3 | Operating cash flow | [ ] | [ ] | [ ] | [ ] | |
| 5.3 | One-off income flags | [ ] | [ ] | [ ] | [ ] | |
| 5.3 | FX exposure breakdown | [ ] | [ ] | [ ] | [ ] | |
| 5.3 | Debt maturity ladder | [ ] | [ ] | [ ] | [ ] | |
| 5.3 | Revaluation reserve | [ ] | [ ] | [ ] | [ ] | |
| 5.4 | Related-party transactions | [ ] | [ ] | [ ] | [ ] | |
| 5.4 | Auditor qualifications | [ ] | [ ] | [ ] | [ ] | |
| 5.4 | Board meeting outcomes | [ ] | [ ] | [ ] | [ ] | |
| 5.4 | Board composition changes | [ ] | [ ] | [ ] | [ ] | |
| 5.5 | Announced vs executed dates | [ ] | [ ] | [ ] | [ ] | |
| 5.5 | Rights issue calendars | [ ] | [ ] | [ ] | [ ] | |
| 5.5 | Merger / acquisition notes | [ ] | [ ] | [ ] | [ ] | |
| 5.6 | SEBON circulars | [ ] | [ ] | [ ] | [ ] | |
| 5.6 | NRB circulars | [ ] | [ ] | [ ] | [ ] | |
| 5.6 | Treasury-yield curve | [ ] | [ ] | [ ] | [ ] | |
| 5.6 | Policy / base rate | [ ] | [ ] | [ ] | [ ] | |
| 5.6 | CPI / GDP / remittance | [ ] | [ ] | [ ] | [ ] | |
| 5.7 | Company disclosures | [ ] | [ ] | [ ] | [ ] | |
| 5.7 | NEPSE announcements | [ ] | [ ] | [ ] | [ ] | |
| 5.7 | Press releases | [ ] | [ ] | [ ] | [ ] | |
| 5.8 | Live quote ticks | [ ] | [ ] | [ ] | [ ] | |
| 5.8 | Floor-sheet live feed | [ ] | [ ] | [ ] | [ ] | |
| 5.8 | Intraday index snapshots | [ ] | [ ] | [ ] | [ ] | |

### 8.3 · Delivery mechanism

| Option | Can support | Notes |
|---|:---:|---|
| SFTP with public-key auth | [ ] | |
| S3 (AWS) with IAM role | [ ] | |
| S3-compatible MinIO (NIMB-hosted) | [ ] | |
| OneDrive (continue current) | [ ] | |
| Webhook notification on drop | [ ] | |
| Email notification on drop | [ ] | |

### 8.4 · Contact & follow-up

Please reply with the marked-up document along with:
- Primary technical contact (name, email)
- Escalation contact for schedule changes or delayed drops
- Any constraints on data re-distribution within NIMB

---

*End of contract. Questions, edge cases, or items this document doesn't cover — please annotate inline and return. We will iterate from your response.*
