"""Bronze ingestion for the scrip master — the 'who's who' of the universe.

Input : scrapers/output/company_info/scrip_master.csv — one row per scrip,
        rich metadata (sector, listed_shares, paid_up_capital, registered_date,
        contact info, company_id from Sharesansar's internal indexing).
Output: bronze.scrip_master_raw — same shape, minimally cleaned.

`sector` values of 'Merged' mark banks that were absorbed in the 2019-2023
consolidation wave; Silver derives `is_active` from this."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import IngestionReport

_TABLE = "bronze.scrip_master_raw"


def ingest_scrip_master(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest scrip_master.csv into bronze.scrip_master_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    file = input_dir / "scrip_master.csv"
    if not file.exists():
        raise FileNotFoundError(f"{file} not found")

    path = str(file).replace("'", "''")
    iso_ts = started_at.isoformat()

    conn = duckdb.connect(":memory:")
    try:
        raw_count = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{path}', all_varchar=true)").fetchone()[0]

        table = conn.execute(f"""
            SELECT
                UPPER(TRIM(scrip))                                           AS scrip,
                TRIM(company_name)                                           AS company_name,
                TRIM(sector)                                                 AS sector,
                NULLIF(TRIM(sub_sector), '')                                 AS sub_sector,
                TRY_CAST(REPLACE(listed_shares, ',', '')     AS DOUBLE)      AS listed_shares,
                TRY_CAST(REPLACE(paid_up_value, ',', '')     AS DOUBLE)      AS paid_up_value,
                TRY_CAST(REPLACE(paid_up_capital, ',', '')   AS DOUBLE)      AS paid_up_capital,
                TRY_CAST(REPLACE(market_cap, ',', '')        AS DOUBLE)      AS market_cap,
                TRY_CAST(NULLIF(TRIM(registered_date), '')   AS DATE)        AS registered_date,
                NULLIF(TRIM(phone), '')                                      AS phone,
                NULLIF(TRIM(email), '')                                      AS email,
                NULLIF(TRIM(address), '')                                    AS address,
                NULLIF(TRIM(website), '')                                    AS website,
                TRY_CAST(latest_close          AS DOUBLE)                    AS latest_close,
                TRY_CAST(NULLIF(TRIM(last_close_date), '')   AS DATE)        AS last_close_date,
                TRY_CAST(latest_bonus_pct      AS DOUBLE)                    AS latest_bonus_pct,
                TRY_CAST(latest_cash_div_pct   AS DOUBLE)                    AS latest_cash_div_pct,
                TRY_CAST(NULLIF(TRIM(latest_bookclose_date), '') AS DATE)    AS latest_bookclose_date,
                TRY_CAST(company_id            AS INTEGER)                   AS company_id,
                TIMESTAMPTZ '{iso_ts}'                                       AS ingested_at,
                'sharesansar'                                                AS source,
                'scraped'                                                    AS source_tier
            FROM read_csv_auto('{path}', all_varchar=true)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(scrip)) ORDER BY company_id) = 1
        """).to_arrow_table()
    finally:
        conn.close()

    io = DeltaIO(settings)
    io.write(_TABLE, table, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)

    return IngestionReport(
        table=_TABLE,
        rows_read=raw_count,
        rows_written=table.num_rows,
        source_files=1,
        delta_version=io.version(_TABLE),
        started_at=started_at,
    )
