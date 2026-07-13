"""Bronze asset for the firm's internal trade-book xlsx dumps.

One asset:
  * bronze_internal_trades — wrapper around ingest_client_internal_trades.
      Reads every Trade_Book_Details *.xlsx under the drop folder into
      bronze.internal_trades_raw (append-safe: Silver dedups on
      contract_number/client/side, so re-ingesting the folder daily is fine).

Group: bronze_internal. Tagged CLIENT_AUTHORITATIVE — this is the firm's own
record of its executions, the input to internal-trade surveillance."""
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from nrc_ingestion import ingest_client_internal_trades

from ..resources import ClientDocsResource, StorageResource

_GROUP = "bronze_internal"
_COMPUTE_KIND = "python"


@asset(
    group_name=_GROUP,
    key_prefix=["bronze"],
    description=(
        "The firm's own executed fills from the trade-book xlsx dumps "
        "(CONTRACT NO, CLIENT, SYMBOL, TYPE, PRICE, QTY, ORDER ID, TRADE TIME). "
        "contract_number joins silver.floorsheet downstream to recover the "
        "broker/counterparty for surveillance. Tagged client_authoritative."
    ),
    metadata={"table": "bronze.internal_trades_raw", "tier": "client_authoritative"},
    compute_kind=_COMPUTE_KIND,
)
def bronze_internal_trades(
    context: AssetExecutionContext,
    client_docs: ClientDocsResource,
    storage: StorageResource,
) -> Output[int]:
    report = ingest_client_internal_trades(
        client_docs.internal_trades_dir,
        settings=storage.settings,
    )
    context.log.info(report.summary())
    return Output(
        value=report.rows_written,
        metadata={
            "rows_read": MetadataValue.int(report.rows_read),
            "rows_written": MetadataValue.int(report.rows_written),
            "source_files": MetadataValue.int(report.source_files),
            "delta_version": MetadataValue.int(report.delta_version),
        },
    )
