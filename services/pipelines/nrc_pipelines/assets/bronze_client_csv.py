"""Bronze assets for client-provided CSV dumps — the primary data path.

Assets exposed:
  * bronze_shreyas_fundamentals + bronze_shreyas_additional_info
      One multi-asset wrapper around ingest_client_csv_shreyas — populates
      bronze.fundamentals_raw (BS + IS unpivoted) AND bronze.additional_info_raw
      (wide ratio block) in a single pass.
  * bronze_format_b_fundamentals
      Wrapper around ingest_client_csv_format_b_fundamentals — populates
      bronze.fundamentals_raw with long-range (2010/11→) wide CSV data.
  * bronze_format_b_closes
      Wrapper around ingest_client_csv_format_b_prices — populates the
      close-only bronze.closes_raw table.

Group: bronze_client_csv. These are the authoritative sources — their rows
win over scraped rows at Silver-merge time via source_tier precedence.

Note on shared table semantics: both Shreyas and Format B fundamentals land
in the same Bronze table (bronze.fundamentals_raw). The ingestion adapters
use DeltaIO.upsert_source_partition so they only replace their own
`source = '<tag>'` rows — they coexist without clobbering each other."""
from dagster import (
    AssetExecutionContext,
    AssetOut,
    MetadataValue,
    Output,
    asset,
    multi_asset,
)

from nrc_ingestion import (
    ingest_client_csv_automation,
    ingest_client_csv_format_b_fundamentals,
    ingest_client_csv_format_b_prices,
    ingest_client_csv_shreyas,
)

from ..resources import ClientDocsResource, StorageResource

_GROUP = "bronze_client_csv"
_COMPUTE_KIND = "python"


@multi_asset(
    group_name=_GROUP,
    outs={
        "bronze_shreyas_fundamentals": AssetOut(
            key_prefix=["bronze"],
            description=(
                "Long-format unpivoted Shreyas balance-sheet + income-statement "
                "rows. Tagged source_tier='client_authoritative' — highest "
                "precedence at Silver-merge time."
            ),
            metadata={"table": "bronze.fundamentals_raw", "tier": "client_authoritative"},
        ),
        "bronze_shreyas_additional_info": AssetOut(
            key_prefix=["bronze"],
            description=(
                "Wide Shreyas additional-info (ratios, capital, per-share). One "
                "row per (scrip, fy, quarter). Feeds silver.additional_info."
            ),
            metadata={"table": "bronze.additional_info_raw", "tier": "client_authoritative"},
        ),
    },
    compute_kind=_COMPUTE_KIND,
)
def shreyas_bronze(
    context: AssetExecutionContext,
    client_docs: ClientDocsResource,
    storage: StorageResource,
):
    """Ingest the three CB Data by Shreyas/*.csv files into Bronze."""
    reports = ingest_client_csv_shreyas(
        client_docs.shreyas_dir,
        settings=storage.settings,
        mode="overwrite",
    )
    by_table = {r.table: r for r in reports}
    fundamentals_report = by_table["bronze.fundamentals_raw"]
    additional_info_report = by_table["bronze.additional_info_raw"]

    context.log.info(fundamentals_report.summary())
    context.log.info(additional_info_report.summary())

    yield Output(
        value=fundamentals_report.rows_written,
        output_name="bronze_shreyas_fundamentals",
        metadata={
            "rows_written": MetadataValue.int(fundamentals_report.rows_written),
            "rows_read": MetadataValue.int(fundamentals_report.rows_read),
            "source_files": MetadataValue.int(fundamentals_report.source_files),
            "delta_version": MetadataValue.int(fundamentals_report.delta_version),
            "duration_s": MetadataValue.float(fundamentals_report.duration_s),
        },
    )
    yield Output(
        value=additional_info_report.rows_written,
        output_name="bronze_shreyas_additional_info",
        metadata={
            "rows_written": MetadataValue.int(additional_info_report.rows_written),
            "rows_read": MetadataValue.int(additional_info_report.rows_read),
            "source_files": MetadataValue.int(additional_info_report.source_files),
            "delta_version": MetadataValue.int(additional_info_report.delta_version),
            "duration_s": MetadataValue.float(additional_info_report.duration_s),
        },
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description=(
        "Long-format unpivoted multi-sector fundamentals from the 'Data for "
        "Automation' dump — cross-sector key metrics (revenue, net/operating "
        "profit, total assets, equity, EPS, BVPS, ROE, ROA, P/E, MVPS, DPS + "
        "bank ratios) for 10 sectors. Tagged source_tier='client_authoritative' "
        "— wins over other sources at Silver-merge for overlapping quarters."
    ),
    metadata={"table": "bronze.fundamentals_raw", "tier": "client_authoritative"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_automation_fundamentals(
    context: AssetExecutionContext,
    client_docs: ClientDocsResource,
    storage: StorageResource,
) -> Output[int]:
    """Ingest the per-sector '<SECTOR> {BS,IS,KS}.csv' tidy files into Bronze long format."""
    report = ingest_client_csv_automation(
        client_docs.automation_dir,
        settings=storage.settings,
        mode="overwrite",
    )
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
    description=(
        "Long-format unpivoted Format B per-scrip fundamentals (BS, IS, key "
        "stats). Coverage 2010/11 → present. Tagged source_tier="
        "'client_historical' — loses to Shreyas at Silver-merge for overlapping "
        "quarters but provides pre-2020 backfill."
    ),
    metadata={"table": "bronze.fundamentals_raw", "tier": "client_historical"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_format_b_fundamentals(
    context: AssetExecutionContext,
    client_docs: ClientDocsResource,
    storage: StorageResource,
) -> Output[int]:
    """Parse per-scrip wide CSVs under Commercial bank/ into Bronze long format."""
    report = ingest_client_csv_format_b_fundamentals(
        client_docs.format_b_dir,
        settings=storage.settings,
        mode="overwrite",
    )
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
    description=(
        "Close-only daily prices from Format B per-scrip CSVs. Covers "
        "2011-07-17 → present for 18 of the 19-bank universe (SCB missing "
        "— data gap flagged to client data team). Tagged source_tier="
        "'client_historical'."
    ),
    metadata={"table": "bronze.closes_raw", "tier": "client_historical"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_format_b_closes(
    context: AssetExecutionContext,
    client_docs: ClientDocsResource,
    storage: StorageResource,
) -> Output[int]:
    """Ingest close-only price series into bronze.closes_raw."""
    report = ingest_client_csv_format_b_prices(
        client_docs.format_b_prices_dir,
        settings=storage.settings,
        mode="overwrite",
    )
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
