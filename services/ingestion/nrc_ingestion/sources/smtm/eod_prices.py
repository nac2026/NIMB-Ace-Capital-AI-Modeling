"""EOD price snapshot from SMTM stock-live-v2 → bronze.prices_raw.

`stock-live-v2` returns one snapshot row per scrip for the WHOLE market
(~354 scrips, all sectors) with open/high/low/LTP/volume/turnover. We write one
daily OHLCV bar per scrip into bronze.prices_raw (tier=LIVE_API), which then
flows through the existing transform_prices → silver.prices → indicators/returns.

This is the all-sector price source: it works today with the live-data scope
(no historical entitlement needed), gives every sector a price immediately, and
accrues history one trading day at a time as it runs daily after close.
Tier=LIVE_API beats the scraper's banks-only history at Silver dedup."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker
from nrc_smtm import SMTMClient
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_TABLE = "bronze.prices_raw"
_SOURCE_NAME = "smtm"
_SOURCE_TIER = SourceTier.LIVE_API.value

_SCHEMA = pa.schema([
    ("scrip", pa.string()),
    ("date", pa.date32()),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("per_change", pa.float64()),
    ("volume", pa.int64()),
    ("turnover", pa.float64()),
    ("status", pa.int32()),
    ("ingested_at", pa.timestamp("us", tz="UTC")),
    ("source", pa.string()),
    ("source_tier", pa.string()),
    ("source_file", pa.string()),
])


def _trade_date(ts: str | None) -> date | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def ingest_smtm_eod_prices(
    *,
    client: SMTMClient | None = None,
    settings: StorageSettings | None = None,
    snapshot_date: date | None = None,
) -> IngestionReport:
    """Write today's market snapshot (one bar/scrip) into bronze.prices_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    own = client is None
    smtm = client or SMTMClient()
    if own:
        smtm.login()
    try:
        quotes = smtm.stock_live_v2()
    finally:
        if own:
            smtm.close()

    rows = {k: [] for k in _SCHEMA.names}
    read = 0
    for q in quotes:
        read += 1
        if not q.symbol:
            continue
        # close = last traded price, falling back to previous close for untraded scrips.
        close = q.ltp if (q.ltp and q.ltp > 0) else (q.previous_closing or 0)
        if not close or close <= 0:
            continue
        o = q.open if (q.open and q.open > 0) else close
        hi = q.high if (q.high and q.high > 0) else close
        lo = q.low if (q.low and q.low > 0) else close
        # keep OHLC invariants sane (transform_prices also repairs, but be clean)
        hi = max(o, hi, lo, close)
        lo = min(o, hi, lo, close)
        d = snapshot_date or _trade_date(q.timestamp) or started_at.date()
        rows["scrip"].append(canonical_ticker(q.symbol))
        rows["date"].append(d)
        rows["open"].append(float(o))
        rows["high"].append(float(hi))
        rows["low"].append(float(lo))
        rows["close"].append(float(close))
        rows["per_change"].append(float(q.percentage_change) if q.percentage_change is not None else None)
        rows["volume"].append(int(q.volume) if q.volume is not None else 0)
        rows["turnover"].append(float(q.turnover) if q.turnover is not None else 0.0)
        rows["status"].append(1)
        rows["ingested_at"].append(started_at)
        rows["source"].append(_SOURCE_NAME)
        rows["source_tier"].append(_SOURCE_TIER)
        rows["source_file"].append(None)

    table = pa.table(rows, schema=_SCHEMA)
    io = DeltaIO(settings)
    if table.num_rows:
        # Append the day's snapshot; Silver dedups on (scrip, date) by tier.
        io.write(_TABLE, table, mode="append" if io.exists(_TABLE) else "overwrite",
                 schema_mode=None if io.exists(_TABLE) else "overwrite")

    return IngestionReport(
        table=_TABLE,
        rows_read=read,
        rows_written=table.num_rows,
        source_files=0,
        delta_version=io.version(_TABLE) if io.exists(_TABLE) else 0,
        started_at=started_at,
    )
