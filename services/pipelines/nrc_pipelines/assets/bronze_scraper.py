"""Bronze assets wrapping the Sharesansar scraper — manual, opt-in only.

These assets exist in the Dagster UI but are NOT part of the default
daily_eod_job. They appear as a separate group (`bronze_scraper`) and can
only be materialized via the `manual_scrape_job` or a direct asset
materialization from the UI.

Rows written by this path carry source_tier='scraped' — lowest precedence
at Silver-merge time. The scraper is kept available as fallback when client
CSVs are stale, missing, or out of universe (hydropower, insurance, etc.)
but is not a primary data source.

Input location: scrapers/output/* inside the repo. The Sharesansar scrape
itself runs outside this package (see scrapers/sharesansar/); these assets
only ingest the scraped CSVs into Bronze Delta."""
from pathlib import Path

from dagster import AssetExecutionContext, MetadataValue, Output, asset

from nrc_ingestion import (
    ingest_corporate_actions,
    ingest_fundamentals,
    ingest_index_history,
    ingest_news,
    ingest_prices,
    ingest_scrip_master,
)

from ..resources import StorageResource

_GROUP = "bronze_scraper"
_COMPUTE_KIND = "python"

# Scraped CSVs live inside the repo under scrapers/output/. We resolve this
# at asset-run time rather than at import time so the path is stable even
# if CWD drifts between CLI and `dagster dev`.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRAPE_DIR = _REPO_ROOT / "scrapers" / "output"


def _emit_report(context: AssetExecutionContext, report) -> Output[int]:
    """Helper: log the ingestion summary and wrap it as a Dagster Output."""
    context.log.info(report.summary())
    return Output(
        value=report.rows_written,
        metadata={
            "rows_written": MetadataValue.int(report.rows_written),
            "rows_read": MetadataValue.int(report.rows_read),
            "source_files": MetadataValue.int(report.source_files),
            "delta_version": MetadataValue.int(report.delta_version),
            "duration_s": MetadataValue.float(report.duration_s),
        },
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description="Scraped Sharesansar scrip master (sector, listed shares, contact info).",
    metadata={"table": "bronze.scrip_master_raw", "tier": "scraped"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_scraper_scrip_master(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(
        context, ingest_scrip_master(_SCRAPE_DIR / "company_info", settings=storage.settings)
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description="Scraped Sharesansar OHLCV daily prices — full candles, unlike client closes-only.",
    metadata={"table": "bronze.prices_raw", "tier": "scraped"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_scraper_prices(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(
        context, ingest_prices(_SCRAPE_DIR / "prices", settings=storage.settings)
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description=(
        "Scraped Sharesansar fundamentals (free-text period_raw). Loses to "
        "client_csv_shreyas at Silver-merge for overlapping quarters."
    ),
    metadata={"table": "bronze.fundamentals_raw", "tier": "scraped"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_scraper_fundamentals(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(
        context, ingest_fundamentals(_SCRAPE_DIR / "fundamentals", settings=storage.settings)
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description="Scraped corporate actions — bonus, cash dividend, rights issues.",
    metadata={"table": "bronze.corporate_actions_raw", "tier": "scraped"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_scraper_corporate_actions(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(
        context, ingest_corporate_actions(_SCRAPE_DIR / "dividends", settings=storage.settings)
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description="Scraped Sharesansar news index (title, URL, published date, scrip tag).",
    metadata={"table": "bronze.news_raw", "tier": "scraped"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_scraper_news(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(
        context, ingest_news(_SCRAPE_DIR / "news", settings=storage.settings)
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description="Scraped NEPSE + sector index daily history.",
    metadata={"table": "bronze.index_history_raw", "tier": "scraped"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_scraper_index_history(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(
        context, ingest_index_history(_SCRAPE_DIR / "index", settings=storage.settings)
    )
