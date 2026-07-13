"""Company-list ingest from the SMTM live API → bronze.scrip_master_smtm_raw.

This is now the PRIMARY universe source — all sectors, ~349 active scrips —
replacing the banks-only Sharesansar scrape as the spine. Sector labels are
normalized to the canonical `SECTORS` set here at the edge. `status` ('A'/'D')
drives is_active; instrument/sector flags mark non-equities (bonds, mutual
funds) so the Silver transform can scope the equity universe.

Overwrites its own source partition each run (idempotent — the universe is a
full snapshot, not an append stream)."""
from __future__ import annotations

from datetime import datetime, timezone

import pyarrow as pa

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker
from nrc_smtm import SMTMClient, is_equity_sector, normalize_sector
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_TABLE = "bronze.scrip_master_smtm_raw"
_SOURCE_NAME = "smtm"
_SOURCE_TIER = SourceTier.LIVE_API.value

_SCHEMA = pa.schema([
    ("scrip", pa.string()),
    ("company_name", pa.string()),
    ("security_name", pa.string()),
    ("sector_raw", pa.string()),
    ("sector", pa.string()),                    # canonical SECTORS member
    ("status", pa.string()),                    # "A" active, "D" delisted/inactive
    ("is_active", pa.bool_()),
    ("is_equity", pa.bool_()),                  # excludes bonds, mutual funds, preferred
    ("instrument_type", pa.string()),
    ("regulatory_body", pa.string()),
    ("email", pa.string()),
    ("website", pa.string()),
    ("company_id", pa.int32()),
    ("ingested_at", pa.timestamp("us", tz="UTC")),
    ("source", pa.string()),
    ("source_tier", pa.string()),
])


def ingest_smtm_company_list(
    *,
    client: SMTMClient | None = None,
    settings: StorageSettings | None = None,
) -> IngestionReport:
    """Pull the full company list from SMTM into bronze.scrip_master_smtm_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    own_client = client is None
    smtm = client or SMTMClient()
    if own_client:
        smtm.login()
    try:
        companies = smtm.company_list()
    finally:
        if own_client:
            smtm.close()

    rows = {k: [] for k in _SCHEMA.names}
    seen: set[str] = set()
    for c in companies:
        if not c.symbol:
            continue
        scrip = canonical_ticker(c.symbol)
        if scrip in seen:           # canonical collisions (rare) — first wins
            continue
        seen.add(scrip)
        sector = normalize_sector(c.sector)
        rows["scrip"].append(scrip)
        rows["company_name"].append(c.company_name)
        rows["security_name"].append(c.security_name)
        rows["sector_raw"].append(c.sector)
        rows["sector"].append(sector)
        rows["status"].append(c.status)
        rows["is_active"].append(c.status == "A")
        rows["is_equity"].append(is_equity_sector(sector))
        rows["instrument_type"].append(c.instrument_type)
        rows["regulatory_body"].append(c.regulatory_body)
        rows["email"].append(c.company_email)
        rows["website"].append(c.website)
        rows["company_id"].append(int(c.company_id) if c.company_id is not None else None)
        rows["ingested_at"].append(started_at)
        rows["source"].append(_SOURCE_NAME)
        rows["source_tier"].append(_SOURCE_TIER)

    table = pa.table(rows, schema=_SCHEMA)

    io = DeltaIO(settings)
    io.upsert_source_partition(_TABLE, table, source=_SOURCE_NAME)

    return IngestionReport(
        table=_TABLE,
        rows_read=len(companies),
        rows_written=table.num_rows,
        source_files=0,
        delta_version=io.version(_TABLE),
        started_at=started_at,
    )
