"""Map raw upstream metric labels to the canonical names used in
nrc_contracts.FundamentalSnapshot fields. One mapping table, one source of truth.

Each key is a (section, metric) pair; `section` identifies which upstream
source wrote the Bronze row:

  * 'balance' / 'profitloss' / 'keymetrics'   — Sharesansar scraper
  * 'shreyas_bs' / 'shreyas_is'              — Shreyas tidy CSVs
  * 'format_b_bs' / 'format_b_is' /
    'format_b_key_stats'                      — Format B wide CSVs

Names on the right are the snake_case snapshot field names. Metrics not in
the map stay in Bronze but are DROPPED from Silver. When adding a new
source, extend this map rather than adding parallel mapping logic."""
from __future__ import annotations

# (section, metric) → canonical_name
METRIC_MAP: dict[tuple[str, str], str] = {
    # ==================== Sharesansar (scraped, lowest priority) ========
    # --- profitloss ---
    ("profitloss", "Profit for the period"):           "net_profit",
    ("profitloss", "Operating Profit"):                "operating_profit",
    ("profitloss", "Net interest income"):             "net_interest_income",

    # --- keymetrics (the core ratios + per-share) ---
    ("keymetrics", "Basic Earnings Per Share(Annualized EPS)"): "eps",
    ("keymetrics", "Net Worth Per Share"):             "bvps",
    ("keymetrics", "Return on Equity"):                "roe",
    ("keymetrics", "Return on Assets"):                "roa",
    ("keymetrics", "Non-Performing loan(NPL) to Total Loan"):   "npl_ratio",
    ("keymetrics", "Capital fund to RWA"):             "car",
    ("keymetrics", "Credit to Deposit Ratio"):         "cd_ratio",
    ("keymetrics", "P/E Ratio"):                       "pe_ratio",
    ("keymetrics", "Price to Book (P/B) Ratio"):       "pb_ratio",

    # --- balance sheet aggregates ---
    ("balance", "Deposits from customers"):            "total_deposits",
    ("balance", "Loans and advances to customers"):    "total_loans",
    ("balance", "Share capital"):                      "paid_up_capital",

    # ==================== Shreyas tidy CSV (client authoritative) =======
    # Column names come verbatim from the CSV headers; mapping to snake_case
    # field names on FundamentalSnapshot.

    # --- shreyas_bs (cbbalancesheet2) ---
    ("shreyas_bs", "TotalAssets"):                     "total_assets",
    ("shreyas_bs", "CashAndBankBalance"):              "cash_and_bank_balance",
    ("shreyas_bs", "MoneyAtCallAndShortNotice"):       "money_at_call",
    ("shreyas_bs", "DueFromNrb"):                      "due_from_nrb",
    ("shreyas_bs", "PlacementwithBFIs"):               "placement_with_bfis",
    ("shreyas_bs", "LoanAndAdvances"):                 "total_loans",
    ("shreyas_bs", "LoanandadvancestoBFIs"):           "loans_to_bfis",
    ("shreyas_bs", "Loansandadvancestocustomers"):     "loans_to_customers",
    ("shreyas_bs", "Investments"):                     "investments",
    ("shreyas_bs", "InvestmentSecurities"):            "investment_securities",
    ("shreyas_bs", "PropEquip"):                       "property_equipment",
    ("shreyas_bs", "Liabilities"):                     "total_liabilities",
    ("shreyas_bs", "BorrowingsTot"):                   "borrowings_total",
    ("shreyas_bs", "DuetoBankandFinancialInstitutions"): "due_to_bfis",
    ("shreyas_bs", "DuetoNRB"):                        "due_to_nrb",
    ("shreyas_bs", "DebtSecuritiesIssued"):            "debt_securities_issued",
    ("shreyas_bs", "Deposits"):                        "total_deposits",
    ("shreyas_bs", "Equity"):                          "shareholders_equity",
    ("shreyas_bs", "PaidUpCapital"):                   "paid_up_capital",
    ("shreyas_bs", "ReservesAndSurplus"):              "reserves_and_surplus",
    ("shreyas_bs", "SharePremium"):                    "share_premium",
    ("shreyas_bs", "RetainedEarnings"):                "retained_earnings",
    ("shreyas_bs", "Reserves"):                        "reserves",
    ("shreyas_bs", "OrdinaryShares"):                  "ordinary_shares",
    ("shreyas_bs", "PrefShares"):                      "preferred_shares",

    # --- shreyas_is (cbincomestatement) ---
    ("shreyas_is", "InterestIncome"):                  "interest_income",
    ("shreyas_is", "InterestExpense"):                 "interest_expense",
    ("shreyas_is", "NetInterestIncome"):               "net_interest_income",
    ("shreyas_is", "FeesIncome"):                      "fees_income",
    ("shreyas_is", "FeesExpense"):                     "fees_expense",
    ("shreyas_is", "NetFeesIncome"):                   "net_fees_income",
    ("shreyas_is", "NetTradingIncome"):                "net_trading_income",
    ("shreyas_is", "OtherOperatingIncome"):            "other_operating_income",
    ("shreyas_is", "TotalOperatingIncome"):            "total_operating_income",
    ("shreyas_is", "Impairment"):                      "impairment_charge",
    ("shreyas_is", "NetOpIncome"):                     "net_operating_income",
    ("shreyas_is", "StaffExpenses"):                   "staff_expenses",
    ("shreyas_is", "OtherOperatingExpenses"):          "other_operating_expenses",
    ("shreyas_is", "DepreciationandAmortization"):     "depreciation_amortization",
    ("shreyas_is", "OperatingProfit"):                 "operating_profit",
    ("shreyas_is", "Nonoperatingincome"):              "non_operating_income",
    ("shreyas_is", "Nonoperatingexpense"):             "non_operating_expense",
    ("shreyas_is", "ProfitbeforeTax"):                 "profit_before_tax",
    ("shreyas_is", "IncomeTax"):                       "income_tax",
    ("shreyas_is", "CurrentTax"):                      "current_tax",
    ("shreyas_is", "DeferredTax"):                     "deferred_tax",
    ("shreyas_is", "NetProfitOrLoss"):                 "net_profit",
    ("shreyas_is", "CompIncome"):                      "comprehensive_income",
    ("shreyas_is", "FreeProfit"):                      "distributable_profit",

    # ==================== Format B wide CSVs (client historical) ========
    # These are long-range backfill (2010/11→present). Metric labels are the
    # row headers from the wide CSVs after _clean_metric strips annotations.

    # --- format_b_bs ---
    ("format_b_bs", "TOTAL ASSETS"):                   "total_assets",
    ("format_b_bs", "CASH AND BANK BALANCE"):          "cash_and_bank_balance",
    ("format_b_bs", "MONEY AT SHORT NOTICE"):          "money_at_call",
    ("format_b_bs", "Due from NRB"):                   "due_from_nrb",
    ("format_b_bs", "Placement with BFIs"):            "placement_with_bfis",
    ("format_b_bs", "LOANS"):                          "total_loans",
    ("format_b_bs", "Loans and Advances to BFIs"):     "loans_to_bfis",
    ("format_b_bs", "Loans and Advances to Customers"): "loans_to_customers",
    ("format_b_bs", "INVESTMENTS"):                    "investments",
    ("format_b_bs", "Investment Securities"):          "investment_securities",
    ("format_b_bs", "PROPERTY AND EQUIPMENT"):         "property_equipment",
    ("format_b_bs", "LIABILITIES"):                    "total_liabilities",
    ("format_b_bs", "BORROWINGS"):                     "borrowings_total",
    ("format_b_bs", "Due to BFIs"):                    "due_to_bfis",
    ("format_b_bs", "Due to NRB"):                     "due_to_nrb",
    ("format_b_bs", "Debt Securities Issued"):         "debt_securities_issued",
    ("format_b_bs", "DEPOSITS"):                       "total_deposits",
    ("format_b_bs", "SHAREHOLDERS EQUITY"):            "shareholders_equity",
    ("format_b_bs", "PAID UP CAPITAL"):                "paid_up_capital",
    ("format_b_bs", "RESERVES AND SURPLUSES"):         "reserves_and_surplus",
    ("format_b_bs", "Share Premium"):                  "share_premium",
    ("format_b_bs", "Retained Earnings"):              "retained_earnings",
    ("format_b_bs", "Reserves"):                       "reserves",

    # --- format_b_is ---
    ("format_b_is", "Interest Income"):                "interest_income",
    ("format_b_is", "Interest Expense"):               "interest_expense",
    ("format_b_is", "Net Interest Income"):            "net_interest_income",
    ("format_b_is", "Fees and Commission Income"):     "fees_income",
    ("format_b_is", "Fees and Commission Expense"):    "fees_expense",
    ("format_b_is", "Net Fees and Commission Income"): "net_fees_income",
    ("format_b_is", "Net Trading Income"):             "net_trading_income",
    ("format_b_is", "Other Operating Income"):         "other_operating_income",
    ("format_b_is", "Total Operating Income"):         "total_operating_income",
    ("format_b_is", "Impairment Charge"):              "impairment_charge",
    ("format_b_is", "Net Operating Income"):           "net_operating_income",
    ("format_b_is", "Staff Expenses"):                 "staff_expenses",
    ("format_b_is", "Other Operating Expenses"):       "other_operating_expenses",
    ("format_b_is", "Depreciation and Amortization"):  "depreciation_amortization",
    ("format_b_is", "Operating Profit"):               "operating_profit",
    ("format_b_is", "Non Operating Income"):           "non_operating_income",
    ("format_b_is", "Non Operating Expense"):          "non_operating_expense",
    ("format_b_is", "Profit before Tax"):              "profit_before_tax",
    ("format_b_is", "Current Tax"):                    "current_tax",
    ("format_b_is", "Deferred Tax"):                   "deferred_tax",
    ("format_b_is", "Profit/Loss for the period"):     "net_profit",
    ("format_b_is", "Comprehensive Income"):           "comprehensive_income",
    ("format_b_is", "Distributable Profit"):           "distributable_profit",

    # --- format_b_key_stats (pre-computed per-share + returns + multiples) ---
    ("format_b_key_stats", "EPS"):                     "eps",
    ("format_b_key_stats", "Book Value per Share"):    "bvps",
    ("format_b_key_stats", "Return on Equity"):        "roe",
    ("format_b_key_stats", "Return on Asset"):         "roa",
    ("format_b_key_stats", "Reported PE"):             "pe_ratio",
    ("format_b_key_stats", "Non Performing Loan"):     "npl_ratio",
    ("format_b_key_stats", "Non Performing Loan (NPL) to Total Loan"): "npl_ratio",
    ("format_b_key_stats", "Capital Fund to RWA"):     "car",
    ("format_b_key_stats", "Credit Deposit Ratio as per NRB Calculations"): "cd_ratio",
    ("format_b_key_stats", "Net Income"):              "net_profit",
    ("format_b_key_stats", "Total Revenue"):           "interest_income",

    # ==================== "Data for Automation" multi-sector dump ========
    # (client authoritative) Tidy per-sector BS/IS/KS CSVs spanning 10 sectors.
    # Scope = CROSS-SECTOR KEY METRICS only — line items unique to one sector
    # (insurance contract liabilities, hydro/manufacturing COGS, etc.) are left
    # unmapped and dropped at Silver. Label variants differ by sector, so each
    # canonical target lists every spelling seen across the dump.

    # --- auto_ks (the cross-sector goldmine: present for every sector) ---
    ("auto_ks", "Total Revenue (Rs. 000)"):            "total_revenue",
    ("auto_ks", "Net Income (Rs. 000)"):               "net_profit",
    ("auto_ks", "Return on Asset (TTM)"):              "roa",
    ("auto_ks", "Return on Asset (TTM) %"):            "roa",
    ("auto_ks", "Return on Equity (TTM)"):             "roe",
    ("auto_ks", "Return on Equity (TTM) %"):           "roe",
    ("auto_ks", "EPS (Annualized)"):                   "eps",
    ("auto_ks", "EPS (Anualized)"):                    "eps",   # misspelled in non-bank files
    ("auto_ks", "Reported PE (Annualized)"):           "pe_ratio",
    ("auto_ks", "Book Value per Share"):               "bvps",
    ("auto_ks", "Market Value per Share"):             "market_value_per_share",
    ("auto_ks", "Market Value Per Share"):             "market_value_per_share",
    ("auto_ks", "Dividend Per Share (Rs.)"):           "dividend_per_share",
    # bank/finance/MF KS ratios
    ("auto_ks", "Capital Fund to RWA"):                "car",
    ("auto_ks", "Non Performing Loan (NPL) to Total Loan"): "npl_ratio",
    ("auto_ks", "Credit Deposit Ratio as per NRB Calculations"): "cd_ratio",

    # --- auto_bs (cross-sector aggregates; label varies by sector) -------
    ("auto_bs", "TOTAL ASSETS"):                       "total_assets",
    ("auto_bs", "SHAREHOLDERS EQUITY"):                "shareholders_equity",
    ("auto_bs", "TOTAL EQUITY"):                       "shareholders_equity",
    ("auto_bs", "TOTAL  EQUITY"):                      "shareholders_equity",  # Life Ins: double space
    ("auto_bs", "Total Equity"):                       "shareholders_equity",
    ("auto_bs", "Capital & Reserves"):                 "shareholders_equity",  # Hotels
    ("auto_bs", "PAID UP CAPITAL"):                    "paid_up_capital",
    ("auto_bs", "Paid Up Capital"):                    "paid_up_capital",      # MF
    ("auto_bs", "Paid up Capital"):                    "paid_up_capital",      # Hydro
    ("auto_bs", "Share Capital"):                      "paid_up_capital",      # insurance/MFG/Hotels/Investment
    ("auto_bs", "DEPOSITS"):                           "total_deposits",
    ("auto_bs", "Deposits"):                           "total_deposits",       # MF
    ("auto_bs", "LOANS"):                              "total_loans",
    ("auto_bs", "Loan and Advances"):                  "total_loans",          # MF
    ("auto_bs", "Share Premium"):                      "share_premium",
    ("auto_bs", "Retained Earnings"):                  "retained_earnings",

    # --- auto_is (cross-sector profit lines; label varies by sector) -----
    # net_profit — every IS layout spells the bottom line differently
    ("auto_is", "Profit/Loss for the period"):         "net_profit",   # banks (CB/DB/Finance)
    ("auto_is", "Net Profit/Loss"):                    "net_profit",   # MF
    ("auto_is", "Net Profit"):                         "net_profit",   # Hydro/Investment/MFG
    ("auto_is", "Net Profit After Tax"):               "net_profit",   # Hotels
    ("auto_is", "NET PROFIT "):                        "net_profit",   # Life/NLI (trailing space)
    # operating_profit
    ("auto_is", "Operating Profit"):                   "operating_profit",
    ("auto_is", "Gross Operating Profit"):             "operating_profit",  # Hotels
    # top-line operating income (banks/MF use "Total Operating Income")
    ("auto_is", "Total Operating Income"):             "total_operating_income",
    # interest income / NII (banks, MF, hydro)
    ("auto_is", "Interest Income"):                    "interest_income",
    ("auto_is", "Net Interest Income"):                "net_interest_income",
    # profit before tax
    ("auto_is", "Profit before Tax"):                  "profit_before_tax",
    ("auto_is", "Profit Before Tax"):                  "profit_before_tax",
    ("auto_is", "Profit Before Taxes"):                "profit_before_tax",  # Investment
    # distributable profit
    ("auto_is", "Distributable Profit"):               "distributable_profit",
    ("auto_is", "Total Distributable Profit"):         "distributable_profit",  # Life/NLI
}

CANONICAL_METRICS: frozenset[str] = frozenset(METRIC_MAP.values())
