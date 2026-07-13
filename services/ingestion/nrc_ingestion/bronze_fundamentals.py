"""Bronze ingestion for quarterly fundamentals.

Input : scrapers/output/fundamentals/<SCRIP>_fundamentals_long.csv
        Columns: scrip, section, metric, period, value_raw, value_num.
        `section` ∈ {balance, profitloss, keymetrics} — the three Sharesansar
        tabs combined by the scraper. `period` is free-text like
        '2nd Quarter 2082/2083' — preserved verbatim at Bronze; Silver parses
        to (fiscal_year_bs: int, quarter: Q1..Q4).
Output: bronze.fundamentals_raw — long-format, one row per (scrip, section,
        metric, period)."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_nepal import canonical_ticker
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import IngestionReport

_TABLE = "bronze.fundamentals_raw"


def ingest_fundamentals(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest per-scrip fundamentals_long CSVs into bronze.fundamentals_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    files = sorted(input_dir.glob("*_fundamentals_long.csv"))
    if not files:
        raise FileNotFoundError(f"No *_fundamentals_long.csv under {input_dir}")

    glob = str(input_dir / "*_fundamentals_long.csv").replace("'", "''")
    iso_ts = started_at.isoformat()

    conn = duckdb.connect(":memory:")
    try:
        conn.create_function("canonical_ticker", canonical_ticker, ["VARCHAR"], "VARCHAR")
        raw_count = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{glob}')").fetchone()[0]

        table = conn.execute(f"""
            SELECT
                canonical_ticker(scrip)            AS scrip,
                LOWER(TRIM(section))               AS section,
                TRIM(metric)                       AS metric,
                TRIM(period)                       AS period_raw,
                value_raw                          AS value_raw,
                TRY_CAST(value_num AS DOUBLE)      AS value_num,
                CAST(NULL AS INTEGER)              AS fiscal_year_bs,
                CAST(NULL AS INTEGER)              AS quarter,
                TIMESTAMPTZ '{iso_ts}'             AS ingested_at,
                'sharesansar'                      AS source,
                'scraped'                          AS source_tier,
                regexp_extract(filename, '[^/]+$') AS source_file
            FROM read_csv_auto('{glob}', filename=true)
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY canonical_ticker(scrip), LOWER(TRIM(section)), TRIM(metric), TRIM(period)
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
