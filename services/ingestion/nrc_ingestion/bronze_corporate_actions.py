"""Bronze ingestion for corporate actions (bonuses, cash dividends, rights).

Input : scrapers/output/dividends/<SCRIP>_dividends.csv  — one dividend row can
        contain BOTH a bonus and a cash component; we unfold into separate events.
        scrapers/output/dividends/<SCRIP>_rights.csv     — ratio field is a string
        ('2:1', '10:4', '10:2.5'), preserved verbatim.
Output: bronze.corporate_actions_raw — one row per distinct action event.

Design notes:
  * fiscal_year_bs is kept as raw '2081/2082' at Bronze; Silver parses to int.
  * ratio_pct (DOUBLE) carries bonus/cash percent; ratio_raw (VARCHAR) carries
    rights ratio. Exactly one of the two is populated per row.
  * Zero-valued bonus/cash components are filtered out (sharesansar emits 0.00
    as a placeholder when that component didn't apply in a given fiscal year)."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import IngestionReport

_TABLE = "bronze.corporate_actions_raw"


def ingest_corporate_actions(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest dividend + rights CSVs into bronze.corporate_actions_raw."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    div_files = sorted(input_dir.glob("*_dividends.csv"))
    rts_files = sorted(input_dir.glob("*_rights.csv"))
    if not div_files and not rts_files:
        raise FileNotFoundError(f"No *_dividends.csv or *_rights.csv under {input_dir}")

    div_glob = str(input_dir / "*_dividends.csv").replace("'", "''")
    rts_glob = str(input_dir / "*_rights.csv").replace("'", "''")
    iso_ts = started_at.isoformat()

    conn = duckdb.connect(":memory:")
    try:
        # Materialize unfolded events to a temp table so we can measure both
        # pre-dedup count (rows_read) and post-dedup count (rows_written).
        # all_varchar=true lets us parse empty strings as NULL cleanly and avoid
        # DuckDB's type inference choking on mixed empty/string cells.
        conn.execute(f"""
            CREATE TEMP TABLE events_unfolded AS
            WITH divs AS (
                SELECT
                    UPPER(TRIM(scrip))                                AS scrip,
                    NULLIF(TRIM(fiscal_year_bs), '')                  AS fiscal_year_bs_raw,
                    TRY_CAST(NULLIF(TRIM(announcement_date), '') AS DATE) AS announcement_date,
                    TRY_CAST(NULLIF(TRIM(bookclose_date), '')    AS DATE) AS bookclose_date,
                    TRY_CAST(NULLIF(TRIM(distribution_date), '') AS DATE) AS distribution_date,
                    TRY_CAST(NULLIF(TRIM(bonus_share_pct), '')   AS DOUBLE) AS bonus_share_pct,
                    TRY_CAST(NULLIF(TRIM(cash_dividend_pct), '') AS DOUBLE) AS cash_dividend_pct,
                    TRY_CAST(NULLIF(TRIM(status), '')            AS INTEGER) AS status,
                    regexp_extract(filename, '[^/]+$')                AS source_file
                FROM read_csv_auto('{div_glob}', filename=true, all_varchar=true)
            ),
            rts AS (
                SELECT
                    UPPER(TRIM(scrip))                                AS scrip,
                    NULLIF(TRIM(fiscal_year_bs), '')                  AS fiscal_year_bs_raw,
                    TRY_CAST(NULLIF(TRIM(announcement_date), '') AS DATE) AS announcement_date,
                    TRY_CAST(NULLIF(TRIM(opening_date), '')      AS DATE) AS opening_date,
                    TRY_CAST(NULLIF(TRIM(closing_date), '')      AS DATE) AS closing_date,
                    NULLIF(TRIM(ratio), '')                           AS ratio_raw,
                    TRY_CAST(NULLIF(TRIM(issue_price), '')       AS DOUBLE) AS issue_price,
                    TRY_CAST(NULLIF(TRIM(total_units), '')       AS DOUBLE) AS total_units,
                    regexp_extract(filename, '[^/]+$')                AS source_file
                FROM read_csv_auto('{rts_glob}', filename=true, all_varchar=true)
            ),
            events AS (
                -- Bonus component of a dividend row (only if > 0)
                SELECT
                    scrip, 'BONUS' AS action_type, fiscal_year_bs_raw,
                    announcement_date, bookclose_date, distribution_date,
                    CAST(NULL AS DATE) AS opening_date, CAST(NULL AS DATE) AS closing_date,
                    bonus_share_pct AS ratio_pct, CAST(NULL AS VARCHAR) AS ratio_raw,
                    CAST(NULL AS DOUBLE) AS issue_price, CAST(NULL AS DOUBLE) AS total_units,
                    status, source_file
                FROM divs
                WHERE bonus_share_pct IS NOT NULL AND bonus_share_pct > 0

                UNION ALL

                -- Cash-dividend component of a dividend row (only if > 0)
                SELECT
                    scrip, 'CASH_DIVIDEND', fiscal_year_bs_raw,
                    announcement_date, bookclose_date, distribution_date,
                    NULL, NULL,
                    cash_dividend_pct, NULL,
                    NULL, NULL,
                    status, source_file
                FROM divs
                WHERE cash_dividend_pct IS NOT NULL AND cash_dividend_pct > 0

                UNION ALL

                -- Rights issues
                SELECT
                    scrip, 'RIGHTS', fiscal_year_bs_raw,
                    announcement_date, NULL, NULL,
                    opening_date, closing_date,
                    NULL, ratio_raw,
                    issue_price, total_units,
                    NULL, source_file
                FROM rts
                WHERE ratio_raw IS NOT NULL
            )
            SELECT * FROM events
        """)

        unfolded_rows_before_dedup = conn.execute(
            "SELECT COUNT(*) FROM events_unfolded"
        ).fetchone()[0]

        table = conn.execute(f"""
            SELECT
                *,
                TIMESTAMPTZ '{iso_ts}' AS ingested_at,
                'sharesansar'          AS source,
                'scraped'              AS source_tier
            FROM events_unfolded
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY scrip, action_type, fiscal_year_bs_raw, announcement_date, ratio_pct, ratio_raw
                ORDER BY source_file
            ) = 1
        """).to_arrow_table()
    finally:
        conn.close()

    io = DeltaIO(settings)
    io.write(_TABLE, table, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)

    return IngestionReport(
        table=_TABLE,
        rows_read=unfolded_rows_before_dedup,
        rows_written=table.num_rows,
        source_files=len(div_files) + len(rts_files),
        delta_version=io.version(_TABLE),
        started_at=started_at,
    )
