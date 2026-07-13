"""Bronze ingestion for scrip-tagged news headlines.

Input : scrapers/output/news/<SCRIP>_news_index.csv
        Columns: scrip, published_date, title, slug, url.
Output: bronze.news_raw — one row per (scrip, url) pair. A single news article
        reported against N banks contributes N rows; Silver collapses those
        into one article with scrip_tags=[...].

Dedup: same (scrip, url) can appear twice if the scrape was retried; keep
the last-by-source_file."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import IngestionReport

_TABLE = "bronze.news_raw"


def ingest_news(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest per-scrip news index CSVs into bronze.news_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    files = sorted(input_dir.glob("*_news_index.csv"))
    if not files:
        raise FileNotFoundError(f"No *_news_index.csv under {input_dir}")

    glob = str(input_dir / "*_news_index.csv").replace("'", "''")
    iso_ts = started_at.isoformat()

    conn = duckdb.connect(":memory:")
    try:
        raw_count = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{glob}')").fetchone()[0]

        # all_varchar=true keeps the date column string-typed so TRY_CAST can
        # gracefully fail on Sharesansar's '-0001-11-30' sentinel (emitted by
        # PHP when a real publication date is missing from their CMS).
        table = conn.execute(f"""
            SELECT
                UPPER(TRIM(scrip))                 AS scrip,
                TRY_CAST(published_date AS DATE)   AS published_date,
                title                              AS title,
                slug                               AS slug,
                url                                AS url,
                TIMESTAMPTZ '{iso_ts}'             AS ingested_at,
                'sharesansar'                      AS source,
                'scraped'                          AS source_tier,
                regexp_extract(filename, '[^/]+$') AS source_file
            FROM read_csv_auto('{glob}', filename=true, all_varchar=true)
            WHERE TRY_CAST(published_date AS DATE) IS NOT NULL
              AND EXTRACT(year FROM TRY_CAST(published_date AS DATE)) >= 2000
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(scrip)), url
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
