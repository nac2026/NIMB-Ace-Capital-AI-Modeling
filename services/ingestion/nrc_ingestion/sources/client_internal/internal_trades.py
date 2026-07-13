"""Internal trade-book ingest from the firm's daily Excel dumps → bronze.internal_trades_raw.

Input: `Trade_Book_Details - <ISO timestamp>.xlsx` files dropped by the trading desk,
one per trading day. Each row is one executed fill with columns:
  CONTRACT NO, CLIENT, CLIENT NAME, SYMBOL, TYPE (Buy/Sell), PRICE, QTY, VALUE,
  ORDER ID, TRADE TIME

`CONTRACT NO` is the NEPSE contract id — the same key as silver.floorsheet — so the
internal book joins to the public floor sheet downstream to recover the broker the
fund used and the counterparty broker. `CONTRACT NO` / `ORDER ID` are read as strings
(they are 16-digit ids; float parsing would round them) and stay strings in Bronze;
Silver casts contract_number to BIGINT for the floorsheet join.

Bronze is append-only and partitioned by trade_date; Silver dedups on contract_number,
so re-ingesting a day is safe (duplicates collapse downstream). Tagged
CLIENT_AUTHORITATIVE — this is the firm's own record of its trades."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_TABLE = "bronze.internal_trades_raw"
_SOURCE_NAME = "client_internal"
_SOURCE_TIER = SourceTier.CLIENT_AUTHORITATIVE.value

# Trade-book headers → bronze field names.
_COLUMNS = {
    "CONTRACT NO": "contract_number",
    "CLIENT": "client_code",
    "CLIENT NAME": "client_name",
    "SYMBOL": "scrip",
    "TYPE": "side",
    "PRICE": "price",
    "QTY": "quantity",
    "VALUE": "value",
    "ORDER ID": "order_id",
    "TRADE TIME": "traded_at",
}

_SCHEMA = pa.schema([
    ("scrip", pa.string()),
    ("contract_number", pa.string()),          # as-ingested; Silver casts to BIGINT
    ("client_code", pa.string()),
    ("client_name", pa.string()),
    ("side", pa.string()),                      # 'B' / 'S'
    ("price", pa.float64()),
    ("quantity", pa.float64()),
    ("value", pa.float64()),
    ("order_id", pa.string()),
    ("traded_at", pa.timestamp("us")),
    ("trade_date", pa.string()),                # partition key (YYYY-MM-DD)
    ("ingested_at", pa.timestamp("us", tz="UTC")),
    ("source", pa.string()),
    ("source_tier", pa.string()),
    ("source_file", pa.string()),
])


def _parse_ts(s: object) -> datetime | None:
    """Parse the trade book's 'YYYY-MM-DD HH:MM:SS' (naive, NPT-local)."""
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _norm_side(v: object) -> str | None:
    s = str(v or "").strip().upper()
    if s.startswith("B"):
        return "B"
    if s.startswith("S"):
        return "S"
    return None


def ingest_client_internal_trades(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest every Trade_Book_Details xlsx under `input_dir` into bronze.internal_trades_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    # Exclude Excel lock files (`~$...`) that openpyxl can't read.
    files = sorted(f for f in input_dir.glob("*.xlsx") if not f.name.startswith("~$"))
    if not files:
        raise FileNotFoundError(f"no *.xlsx under {input_dir}")

    rows = {k: [] for k in _SCHEMA.names}
    rows_read = 0
    for f in files:
        # CONTRACT NO / ORDER ID are 16-digit ids — read as str to avoid float rounding.
        df = pd.read_excel(
            f, engine="openpyxl",
            dtype={"CONTRACT NO": str, "ORDER ID": str, "CLIENT": str},
        )
        df = df.rename(columns={k: v for k, v in _COLUMNS.items() if k in df.columns})
        for rec in df.to_dict("records"):
            rows_read += 1
            ts = _parse_ts(rec.get("traded_at"))
            side = _norm_side(rec.get("side"))
            if ts is None or side is None:
                continue
            rows["scrip"].append(canonical_ticker(str(rec.get("scrip", "")).strip()))
            rows["contract_number"].append(str(rec.get("contract_number", "")).strip())
            rows["client_code"].append(str(rec.get("client_code", "")).strip())
            rows["client_name"].append(str(rec.get("client_name", "")).strip())
            rows["side"].append(side)
            rows["price"].append(float(rec.get("price") or 0.0))
            rows["quantity"].append(float(rec.get("quantity") or 0.0))
            rows["value"].append(float(rec.get("value") or 0.0))
            rows["order_id"].append(str(rec.get("order_id", "")).strip())
            rows["traded_at"].append(ts)
            rows["trade_date"].append(ts.strftime("%Y-%m-%d"))
            rows["ingested_at"].append(started_at)
            rows["source"].append(_SOURCE_NAME)
            rows["source_tier"].append(_SOURCE_TIER)
            rows["source_file"].append(f.name)

    table = pa.table(rows, schema=_SCHEMA)

    io = DeltaIO(settings)
    if table.num_rows:
        # Bronze is append-only; Silver dedups on contract_number. Partition by
        # trade_date so per-day reads/compaction stay cheap.
        append = mode != "overwrite" and io.exists(_TABLE)
        io.write(
            _TABLE, table,
            mode="append" if append else "overwrite",
            partition_by=["trade_date"],
            schema_mode=None if append else "overwrite",
        )

    return IngestionReport(
        table=_TABLE,
        rows_read=rows_read,
        rows_written=table.num_rows,
        source_files=len(files),
        delta_version=io.version(_TABLE) if io.exists(_TABLE) else 0,
        started_at=started_at,
    )
