# Cover email — NEPSE data request (attach: NIMB_Ace_NEPSE_Data_Requirements.xlsx)

**To:** NIMB Ace Capital — Investment / Data team
**(to coordinate with:** SMTM Capital — data provider)
**Subject:** NEPSE data — request to enable historical + fundamental data for all sectors
**Attachment:** NIMB_Ace_NEPSE_Data_Requirements.xlsx

---

Hi [Name],

The research & portfolio-intelligence platform is now connected **live** to the SMTM Data API and is already pulling current data across **all ~300 listed companies, every sector** — live prices, market indices, market summary, the company master list, and the full floor-sheet (every trade with buyer/seller broker). On top of that we've built broker-flow, accumulation and manipulation/speculation analytics, plus live news sentiment (sourced separately by us).

We're now retiring the interim data we started with (a one-off commercial-bank spreadsheet and some website scraping) and standardising on SMTM as the single source. To do that — and to give every sector the same depth the 19 commercial banks have today — we need a few datasets that **aren't included in our current API access**. The attached workbook is the full, precise specification; the summary of what we're asking for:

1. **Enable historical access for our API user (`nimb`).** We currently have the `live-data` and `general-data` scopes; historical requests return *"Insufficient permissions."* Please enable the historical tier and confirm what it includes — historical **OHLCV**, **index** values, and **floor-sheet**, with the available date range.

2. **Company fundamentals / financial statements for all sectors** — quarterly & annual **balance sheet, P&L, cash flow**, plus ratios and per-share metrics (EPS, BVPS, ROE, ROA, NPL, CAR, P/E, P/B, …). The attachment lists every data point we use (≈80 fields) with our field names so it can be delivered in a directly-usable shape. Is this available via SMTM, and how?

3. **Corporate actions & dividends** — bonus / rights / cash-dividend history with book-closure dates.

4. **Broker master** — broker ID → broker name/code (the floor-sheet only carries numeric IDs).

5. **Delivery format** — we'd like, per dataset:
   - **Live JSON endpoints** for real-time data (prices, indices, market summary, company list) — already integrated, no change needed.
   - **Bulk file exports (CSV or Parquet; Excel is fine)** for fundamentals and the one-time historical price/floor-sheet backfill — far easier for us to load than paginating, and these reload infrequently.
   - For **floor-sheet specifically**, we'd like **both**: keep the live API, but we'd prefer a **daily end-of-day file export** for routine pulls so we don't paginate ~110 pages each day.

6. **Please also confirm:** coverage across **all sectors** (not just commercial banks), **how many years of history** are available (prices & fundamentals), and any **rate/volume limits** on bulk or historical pulls.

The attached **NIMB_Ace_NEPSE_Data_Requirements.xlsx** has the detail — a summary tab, the delivery/format matrix (JSON vs. file, file type, frequency per dataset), the full fundamentals data-point list, price/corporate-action fields, and the floor-sheet specifics.

Happy to jump on a short call to align on scope, format and timelines. Thank you!

Best regards,
[Your name]
NIMB Ace — Research Platform team
[email / phone]
