"""Bronze ingestion for NEPSE + sector index daily history.

Input : scrapers/output/index/NEPSE_history.csv, BANKING_history.csv, ...
        Columns: index_name, index_id, open, high, low, current, per_change,
                 change_, turnover, published_date, DT_Row_Index
        ('current' is Sharesansar's name for close; DT_Row_Index is the
        DataTables server-side row id, dropped as noise.)
Output: bronze.index_history_raw — long-form, one row per (index_name, date)."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import IngestionReport

_TABLE = "bronze.index_history_raw"


def ingest_index_history(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest every *_history.csv into bronze.index_history_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    files = sorted(input_dir.glob("*_history.csv"))
    if not files:
        raise FileNotFoundError(f"No *_history.csv under {input_dir}")

    glob = str(input_dir / "*_history.csv").replace("'", "''")
    iso_ts = started_at.isoformat()

    conn = duckdb.connect(":memory:")
    try:
        raw_count = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{glob}')").fetchone()[0]

        table = conn.execute(f"""
            SELECT
                UPPER(TRIM(index_name))            AS index_name,
                TRY_CAST(index_id AS INTEGER)      AS index_id,
                open::DOUBLE                       AS open,
                high::DOUBLE                       AS high,
                low::DOUBLE                        AS low,
                current::DOUBLE                    AS close,
                per_change::DOUBLE                 AS percent_change,
                change_::DOUBLE                    AS change,
                turnover::DOUBLE                   AS turnover,
                published_date::DATE               AS date,
                TIMESTAMPTZ '{iso_ts}'             AS ingested_at,
                'sharesansar'                      AS source,
                'scraped'                          AS source_tier,
                regexp_extract(filename, '[^/]+$') AS source_file
            FROM read_csv_auto('{glob}', filename=true)
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(index_name)), published_date::DATE
                ORDER BY filename
            ) = 1
        """).to_arrow_table()
    finally:
        conn.close()

    io = DeltaIO(settings)
    io.write(_TABLE, table, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)

    return IngestionReport(
        table=_TABLE,
        rows_read=raw_count,
        rows_written=table.num_rows,
        source_files=len(files),
        delta_version=io.version(_TABLE),
        started_at=started_at,
    )
