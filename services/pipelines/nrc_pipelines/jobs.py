"""Dagster jobs — selections of assets that run together.

Three jobs:

  * daily_eod_job        — the primary refresh. Client CSV → Silver → Gold
                           → Postgres. Excludes scraper-backed assets so
                           scraping never runs automatically.
  * manual_scrape_job    — scraper Bronze assets + the Silver assets that
                           depend only on scraper data. Opt-in; run this
                           when client CSVs are stale or missing.
  * postgres_sync_job    — just the Gold → Postgres sync, for when Gold is
                           already fresh but serving-layer drifted.

Jobs use AssetSelection.keys() for explicit, readable selection. If you
add a new asset, decide which job it belongs to and add it here."""
from __future__ import annotations

from dagster import AssetKey, AssetSelection, define_asset_job

# ---------------------------------------------------------- daily_eod_job
# Client CSV sources + everything derivable without scraper data.
_DAILY_EOD_KEYS = [
    # Bronze — SMTM live universe (all-sector) + EOD prices + client CSV
    ["bronze", "bronze_smtm_company_list"],
    ["bronze", "bronze_smtm_eod_prices"],
    ["bronze", "bronze_shreyas_fundamentals"],
    ["bronze", "bronze_shreyas_additional_info"],
    ["bronze", "bronze_automation_fundamentals"],
    ["bronze", "bronze_format_b_fundamentals"],
    ["bronze", "bronze_format_b_closes"],
    # Silver — all that don't *exclusively* need scraper data.
    # silver_scrip_master stays in the default job because silver.scrip_master
    # is a blocking dep for every downstream Silver asset. It reads from a
    # pre-existing bronze.scrip_master_raw — bootstrap that once via
    # manual_scrape_job, then daily_eod works indefinitely.
    ["silver", "silver_scrip_master"],
    ["silver", "silver_prices"],          # all-sector EOD bars from SMTM
    ["silver", "silver_closes"],
    ["silver", "silver_fundamentals_long"],
    ["silver", "silver_fundamentals_snapshots"],
    ["silver", "silver_additional_info"],
    # Gold — fundamentals + the price-derived models (now fed by the all-sector
    # SMTM EOD prices, so they cover every sector, not just scraped banks).
    ["gold", "indicators_daily"],
    ["gold", "technical_signal_summary"],
    ["gold", "valuation"],
    ["gold", "beta_and_volatility"],
    ["gold", "peer_rankings_quarterly"],
    ["gold", "stage1_screen_results"],
    ["gold", "stage2_bank_screen"],
    # Phase-I expansions — bank financial analytics.
    ["gold", "ttm_fundamentals"],
    ["gold", "quarterly_growth"],
    ["gold", "dupont_decomposition"],
    ["gold", "cost_efficiency"],
    ["gold", "revenue_quality"],
    ["gold", "asset_quality_trends"],
    ["gold", "capital_strength"],
    ["gold", "dividend_yield"],
    ["gold", "piotroski_f_score"],
    # Price-based (use silver.closes — client, not scraper).
    ["gold", "price_returns"],
    # Phase-J additions
    ["gold", "valuation_history"],
    ["gold", "operating_leverage"],
    ["gold", "market_cap_metrics"],
    ["gold", "total_shareholder_return"],
    ["gold", "sector_momentum"],
    # Composites — depend on all the above.
    ["gold", "fundamental_quality_composite"],
    ["gold", "quality_momentum_matrix"],
    ["gold", "investment_scorecard"],
    # Postgres — schema + sync
    ["postgres", "postgres_schema"],
    ["postgres", "postgres_sync"],
]

daily_eod_job = define_asset_job(
    name="daily_eod_job",
    selection=AssetSelection.keys(*(AssetKey(k) for k in _DAILY_EOD_KEYS)),
    description=(
        "Primary daily refresh — client CSV Bronze through Postgres sync. "
        "Does NOT run scrapers. silver_scrip_master assumes its Bronze has "
        "been bootstrapped via manual_scrape_job at least once."
    ),
)

# ---------------------------------------------------------- manual_scrape_job
# Scraper Bronze assets + Silver assets whose only source is the scraper.
# Run this manually when client CSVs are stale, missing, or out of universe.
_MANUAL_SCRAPE_KEYS = [
    # Bronze — scraper
    ["bronze", "bronze_scraper_scrip_master"],
    ["bronze", "bronze_scraper_prices"],
    ["bronze", "bronze_scraper_fundamentals"],
    ["bronze", "bronze_scraper_corporate_actions"],
    ["bronze", "bronze_scraper_news"],
    ["bronze", "bronze_scraper_index_history"],
    # Silver — scraper-exclusive
    ["silver", "silver_prices"],
    ["silver", "silver_corporate_actions"],
    ["silver", "silver_news"],
    ["silver", "silver_index"],
    # Gold — scraper-derived dbt models
    ["gold", "indicators_daily"],
    ["gold", "valuation"],
    ["gold", "beta_and_volatility"],       # needs silver.index_snapshots (scraper)
    ["gold", "technical_signal_summary"],  # depends on indicators_daily
]

manual_scrape_job = define_asset_job(
    name="manual_scrape_job",
    selection=AssetSelection.keys(*(AssetKey(k) for k in _MANUAL_SCRAPE_KEYS)),
    description=(
        "Opt-in scraper run. Populates Bronze from Sharesansar scraped CSVs "
        "and their Silver/Gold downstreams. Never scheduled — invoke from "
        "the UI or `dagster job execute -j manual_scrape_job`."
    ),
)

# ---------------------------------------------------------- floorsheet_job
# SMTM floor-sheet → Silver → broker-flow Gold → broker serving sync.
# Runnable after market close (EOD reconcile of the full day's trades) or
# on a tighter intraday cadence. Independent of the fundamentals path so it
# can run on the floor-sheet's own schedule.
_FLOORSHEET_KEYS = [
    ["bronze", "bronze_smtm_floorsheet"],
    ["silver", "silver_floorsheet"],
    ["gold", "broker_flow_daily"],
    ["gold", "broker_concentration_daily"],
    ["gold", "broker_accumulation"],
    ["gold", "broker_pair_graph"],
    ["gold", "speculation_score"],
    # Internal-trade surveillance — re-ingest the desk's trade-book xlsx drop
    # and rebuild the per-fill scoring against the fresh floor-sheet. Riding
    # the floorsheet cadence keeps the CEO board current the same evening.
    ["bronze", "bronze_internal_trades"],
    ["silver", "silver_internal_trades"],
    ["gold", "internal_trade_enriched"],
    ["gold", "internal_counterparty_exposure"],
    ["gold", "internal_cross_trade"],
    ["gold", "internal_trade_surveillance"],
    ["postgres", "postgres_schema"],
    ["postgres", "postgres_sync_broker"],
]

floorsheet_job = define_asset_job(
    name="floorsheet_job",
    selection=AssetSelection.keys(*(AssetKey(k) for k in _FLOORSHEET_KEYS)),
    description=(
        "SMTM floor-sheet → silver.floorsheet → broker-flow Gold models → "
        "internal-trade surveillance → serving tables. Hits the live SMTM API; "
        "run after close for the full-day reconcile or on an intraday cadence. "
        "CRITICAL: SMTM exposes only the current session — a missed trading "
        "day's floor-sheet is unrecoverable."
    ),
)

# ---------------------------------------------------------- tradebook_job
# Internal trade-book reload WITHOUT the SMTM floor-sheet pull. The desk drops
# new Trade_Book_Details*.xlsx into NRC_INTERNAL_TRADES_DIR and triggers this
# from the surveillance board ("Load new trade-book data"). It re-ingests the
# whole drop folder, rebuilds the internal surveillance Gold models against the
# floor sheet already in the lakehouse, and re-syncs serving. No live-API
# dependency, so it works at any hour and never risks the session-only
# floor-sheet path.
_TRADEBOOK_KEYS = [
    ["bronze", "bronze_internal_trades"],
    ["silver", "silver_internal_trades"],
    ["gold", "internal_trade_enriched"],
    ["gold", "internal_counterparty_exposure"],
    ["gold", "internal_cross_trade"],
    ["gold", "internal_trade_surveillance"],
    ["postgres", "postgres_schema"],
    ["postgres", "postgres_sync_broker"],
]

tradebook_job = define_asset_job(
    name="tradebook_job",
    selection=AssetSelection.keys(*(AssetKey(k) for k in _TRADEBOOK_KEYS)),
    description=(
        "Re-ingest the trade-book xlsx drop folder → silver.internal_trades → "
        "internal surveillance Gold models → serving tables. Uses the floor "
        "sheet already in the lakehouse (no SMTM call) — safe to run on demand "
        "from the surveillance board."
    ),
)

# ---------------------------------------------------------- github_prices_backfill_job
# Fallback / historical price backfill from the Aabishkar2/nepse-data GitHub
# repo. Lands deep OHLCV history in bronze.prices_raw (scraped tier), then
# rebuilds silver.prices and the price-derived Gold (returns, momentum,
# indicators, beta, market cap) and syncs serving. Kept OUT of daily_eod_job so
# a GitHub outage never blocks the SMTM-driven daily path; run on its own
# (weekly) schedule or on demand until SMTM supplies full history.
_GITHUB_PRICES_KEYS = [
    ["bronze", "bronze_github_prices"],
    ["silver", "silver_prices"],
    ["gold", "indicators_daily"],
    ["gold", "technical_signal_summary"],
    ["gold", "price_returns"],
    ["gold", "sector_momentum"],
    ["gold", "beta_and_volatility"],
    ["gold", "market_cap_metrics"],
    ["gold", "total_shareholder_return"],
    ["postgres", "postgres_schema"],
    ["postgres", "postgres_sync"],
]

github_prices_backfill_job = define_asset_job(
    name="github_prices_backfill_job",
    selection=AssetSelection.keys(*(AssetKey(k) for k in _GITHUB_PRICES_KEYS)),
    description=(
        "Fallback price backfill: GitHub community OHLCV → bronze.prices_raw "
        "(scraped tier) → silver.prices → price-derived Gold → Postgres. "
        "Independent of the SMTM daily path; run weekly or on demand."
    ),
)

# ---------------------------------------------------------- news_job
# One live news cycle (fetch → Gemini sentiment → rollup). Scheduled ~30 min.
news_job = define_asset_job(
    name="news_job",
    selection=AssetSelection.keys(AssetKey(["news", "news_sentiment"])),
    description="Live news ingestion + sentiment enrichment + scrip_sentiment rollup.",
)

# ---------------------------------------------------------- postgres_sync_job
postgres_sync_job = define_asset_job(
    name="postgres_sync_job",
    selection=AssetSelection.keys(
        AssetKey(["postgres", "postgres_schema"]),
        AssetKey(["postgres", "postgres_sync"]),
    ),
    description=(
        "Re-apply pending migrations and re-COPY Gold tables into Postgres. "
        "Use when the lakehouse is fresh but the serving layer drifted."
    ),
)
