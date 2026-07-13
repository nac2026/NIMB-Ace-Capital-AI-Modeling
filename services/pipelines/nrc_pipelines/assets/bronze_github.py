"""Bronze asset for the GitHub community price backfill (fallback source).

Wraps ingest_github_nepse_prices — downloads the Aabishkar2/nepse-data
company-wise OHLCV CSVs and lands them in bronze.prices_raw at the SCRAPED
tier. This is the historical/fallback price source: SMTM's live EOD feed
(LIVE_API tier) always wins on overlapping (scrip, date), so this only fills
the deep history SMTM doesn't have yet. Covers ~7 sectors (banks, finance,
hydro, investment, hotels, life insurance) — the repo has no microfinance,
non-life-insurance, manufacturing, trading, or "others" companies.

Group: bronze_github. Materialized on its own schedule/job, NOT in the daily
critical path — so a GitHub outage never blocks the SMTM-driven daily refresh.
The next silver_prices run picks up whatever this lands in bronze."""
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from nrc_ingestion import ingest_github_nepse_prices

from ..resources import StorageResource

_GROUP = "bronze_github"


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description=(
        "Per-company daily OHLCV backfill from the Aabishkar2/nepse-data GitHub "
        "repo → bronze.prices_raw (source='github_nepse_data', tier='scraped'). "
        "Fallback/historical price source; SMTM live EOD wins on overlap."
    ),
    metadata={"table": "bronze.prices_raw", "tier": "scraped", "source": "github_nepse_data"},
    compute_kind="python",
)
def bronze_github_prices(
    context: AssetExecutionContext,
    storage: StorageResource,
) -> Output[int]:
    """Download + ingest the GitHub community price history into Bronze."""
    report = ingest_github_nepse_prices(settings=storage.settings, mode="overwrite")
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
