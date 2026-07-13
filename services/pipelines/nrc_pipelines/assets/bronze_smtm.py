"""Bronze assets for the SMTM live NEPSE feed (tier=LIVE_API).

Two assets:
  * bronze_smtm_company_list — the all-sector universe (~349 active scrips).
    Now the PRIMARY universe source; silver_scrip_master reads it.
  * bronze_smtm_floorsheet    — every executed trade (buyer/seller broker).
    A full-day pull (after_contract=None); Bronze is append-only and Silver
    dedups on contract_number, so re-running a day is safe. True intraday
    incremental pulls are handled by the marketfeed floorsheet_puller
    service (using the feed_cursors table); this asset is the EOD batch path.

These hit the live SMTM API, so unlike the client-CSV Bronze they require
network + valid SMTM_* credentials in .env."""
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from nrc_ingestion import ingest_smtm_company_list, ingest_smtm_eod_prices, ingest_smtm_floorsheet

from ..resources import StorageResource

_GROUP = "bronze_smtm"
_COMPUTE_KIND = "python"


def _emit_report(context: AssetExecutionContext, report) -> Output[int]:
    context.log.info(report.summary())
    return Output(
        value=report.rows_written,
        metadata={
            "rows_written": MetadataValue.int(report.rows_written),
            "rows_read": MetadataValue.int(report.rows_read),
            "delta_version": MetadataValue.int(report.delta_version),
            "duration_s": MetadataValue.float(report.duration_s),
        },
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description=(
        "SMTM company list — the all-sector NEPSE universe (~349 active scrips). "
        "Sectors normalized to canonical labels; status drives is_active. "
        "Primary universe source feeding silver.scrip_master."
    ),
    metadata={"table": "bronze.scrip_master_smtm_raw", "tier": "live_api"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_smtm_company_list(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(context, ingest_smtm_company_list(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description=(
        "SMTM floor-sheet — every executed trade with buyer/seller broker IDs. "
        "Full-day pull; appended to bronze.floorsheet_raw (Silver dedups on "
        "contract_number). The microstructure base for broker-flow + "
        "speculation detection."
    ),
    metadata={"table": "bronze.floorsheet_raw", "tier": "live_api"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_smtm_floorsheet(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(
        context, ingest_smtm_floorsheet(after_contract=None, settings=storage.settings)
    )


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description=(
        "SMTM EOD price snapshot — one OHLCV bar per scrip for the WHOLE market "
        "(all sectors) from stock-live-v2. The all-sector price source; works on "
        "the live-data scope (no historical entitlement). Accrues history daily."
    ),
    metadata={"table": "bronze.prices_raw", "tier": "live_api"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_smtm_eod_prices(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit_report(context, ingest_smtm_eod_prices(settings=storage.settings))
