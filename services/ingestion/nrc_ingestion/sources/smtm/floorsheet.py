"""Floor-sheet ingest from the SMTM live API → bronze.floorsheet_raw.

One row per executed NEPSE trade (buyer broker, seller broker, qty, rate). This
is NIMB Ace's distinctive microstructure edge. Bronze is append-only and
partitioned by trade_date; Silver dedups on contract_number, so re-running a
day is safe (duplicates collapse downstream).

`after_contract` drives incremental pulls: pass the last contract_number already
ingested to fetch only newer trades (intraday poller); pass None for a full
backfill of everything the API currently exposes (EOD / bootstrap)."""
from __future__ import annotations

from datetime import datetime, timezone

import pyarrow as pa

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker
from nrc_smtm import SMTMClient
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_TABLE = "bronze.floorsheet_raw"
_SOURCE_NAME = "smtm"
_SOURCE_TIER = SourceTier.LIVE_API.value

_SCHEMA = pa.schema([
    ("scrip", pa.string()),
    ("contract_number", pa.int64()),
    ("serial_number", pa.int64()),
    ("buyer_broker", pa.int32()),
    ("seller_broker", pa.int32()),
    ("quantity", pa.float64()),
    ("rate", pa.float64()),
    ("amount", pa.float64()),
    ("traded_at", pa.timestamp("us")),
    ("trade_date", pa.string()),                # partition key (YYYY-MM-DD)
    ("ingested_at", pa.timestamp("us", tz="UTC")),
    ("source", pa.string()),
    ("source_tier", pa.string()),
])


def _parse_ts(s: str) -> datetime | None:
    """Parse SMTM's 'YYYY-MM-DD HH:MM:SS[.ffffff]' (naive, NPT-local)."""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def ingest_smtm_floorsheet(
    *,
    after_contract: int | None = None,
    page_size: int = 500,
    client: SMTMClient | None = None,
    settings: StorageSettings | None = None,
) -> IngestionReport:
    """Pull floor-sheet trades from SMTM and append to bronze.floorsheet_raw."""
    own_client = client is None
    smtm = client or SMTMClient()
    if own_client:
        smtm.login()
    try:
        trades = smtm.fetch_new_trades(after_contract=after_contract, page_size=page_size)
    finally:
        if own_client:
            smtm.close()
    return write_floorsheet_trades(trades, settings=settings)


def write_floorsheet_trades(
    trades: list,
    *,
    settings: StorageSettings | None = None,
) -> IngestionReport:
    """Append a list of SMTM FloorsheetTrade wire models to bronze.floorsheet_raw.

    Split out from the fetch so the marketfeed floorsheet_puller can manage its
    own incremental cursor (fetch new trades, persist max contract_number) while
    reusing the exact Bronze write + schema."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    rows = {k: [] for k in _SCHEMA.names}
    for t in trades:
        ts = _parse_ts(t.timestamp)
        rows["scrip"].append(canonical_ticker(t.stock_symbol))
        rows["contract_number"].append(int(t.contract_number))
        rows["serial_number"].append(int(t.serial_number) if t.serial_number is not None else None)
        rows["buyer_broker"].append(int(t.buyer_broker))
        rows["seller_broker"].append(int(t.seller_broker))
        rows["quantity"].append(float(t.quantity))
        rows["rate"].append(float(t.rate))
        rows["amount"].append(float(t.amount))
        rows["traded_at"].append(ts)
        rows["trade_date"].append(t.trade_date)
        rows["ingested_at"].append(started_at)
        rows["source"].append(_SOURCE_NAME)
        rows["source_tier"].append(_SOURCE_TIER)

    table = pa.table(rows, schema=_SCHEMA)

    io = DeltaIO(settings)
    if table.num_rows:
        # Bronze is append-only; Silver dedups on contract_number. Partition by
        # trade_date so per-day reads/compaction stay cheap.
        io.write(
            _TABLE, table,
            mode="append" if io.exists(_TABLE) else "overwrite",
            partition_by=["trade_date"],
            schema_mode=None if io.exists(_TABLE) else "overwrite",
        )

    return IngestionReport(
        table=_TABLE,
        rows_read=len(trades),
        rows_written=table.num_rows,
        source_files=0,
        delta_version=io.version(_TABLE) if io.exists(_TABLE) else 0,
        started_at=started_at,
    )
