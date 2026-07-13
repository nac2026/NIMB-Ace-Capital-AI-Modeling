"""Shreyas-format fundamentals ingest.

Input: three CSVs under `<OneDrive>/CB Data by Shreyas/`:

  * cbbalancesheet2_*.csv   — balance sheet, ~45 columns
  * cbincomestatement_*.csv — P&L, ~30 columns
  * cbadditionalinfo_*.csv  — ratios + capital + per-share, ~19 columns

Each row is keyed on (Ticker, Year, Quarter) where Year is AD short form
('2020/21') and Quarter is 1..4. Monetary values are in NPR thousands,
ratios as decimals, per-share in raw NPR — units verified against NABIL
Q4 FY2023-24 published interim report.

Output:

  * bronze.fundamentals_raw  — long (unpivoted BS + IS), tagged
    source='client_csv_shreyas', source_tier='client_authoritative'.
  * bronze.additional_info_raw — wide (one row per scrip/fy/quarter),
    same tags.

Silver treats `client_authoritative` as the top tier — these rows win over
any scraped or Format-B row covering the same key."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker, parse_ad_fiscal_year_short
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_FUNDAMENTALS_TABLE = "bronze.fundamentals_raw"
_ADDITIONAL_INFO_TABLE = "bronze.additional_info_raw"
_SOURCE_NAME = "client_csv_shreyas"
_SOURCE_TIER = SourceTier.CLIENT_AUTHORITATIVE.value

# Columns in each CSV that are *not* metrics — they identify the row or label
# the file, not the data. Everything else is treated as a numeric metric.
_BS_KEY_COLS = ("idcbbalancesheet2", "Ticker", "Year", "Quarter", "DataSource", "Statement", "BalanceSheet")
_IS_KEY_COLS = ("idcbincomestatement", "Ticker", "Year", "Quarter", "DataSource", "Statement", "ProfitAndLossAccount")
_AI_KEY_COLS = ("idcbadditionalinfo", "Ticker", "Year", "Quarter", "DataSource", "Statement", "AdditionalInformation")


def _register_udfs(conn: duckdb.DuckDBPyConnection) -> None:
    """Register the two string-normalizer UDFs used by every CTE below.

    Registering them on the connection lets DuckDB vectorize the call across
    the whole CSV in one pass — much faster than round-tripping through
    pyarrow for each row."""
    conn.create_function("canonical_ticker", canonical_ticker, ["VARCHAR"], "VARCHAR")
    conn.create_function("parse_ad_fy_short", parse_ad_fiscal_year_short, ["VARCHAR"], "INTEGER")


def _find_csv(input_dir: Path, prefix: str) -> Path:
    """Locate the one CSV in `input_dir` whose filename starts with `prefix`.

    Shreyas exports include a timestamp suffix (e.g.
    `cbbalancesheet2_202604231844.csv`), so we glob by prefix. Multiple
    matches means the export was re-dropped without cleanup — refuse loudly
    rather than picking one arbitrarily."""
    matches = sorted(input_dir.glob(f"{prefix}*.csv"))
    if not matches:
        raise FileNotFoundError(f"no {prefix}*.csv under {input_dir}")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise ValueError(f"multiple {prefix}* exports in {input_dir}: {names}. Keep only one.")
    return matches[0]


def _unpivot_long(
    conn: duckdb.DuckDBPyConnection,
    csv_path: Path,
    key_cols: tuple[str, ...],
    section: str,
    iso_ts: str,
) -> "duckdb.DuckDBPyRelation":
    """Read a Shreyas wide CSV and unpivot to (scrip, fy, quarter, section, metric, value)."""
    csv_path_sql = str(csv_path).replace("'", "''")
    # Exclude both the key cols (identifiers) and the literal "Year"/"Quarter" so
    # UNPIVOT doesn't try to treat them as metrics. EXCLUDE keeps new upstream
    # columns flowing through automatically — defensible for a prototype.
    exclude_sql = ", ".join(f'"{c}"' for c in key_cols)
    return conn.sql(f"""
        WITH raw AS (
            SELECT * FROM read_csv_auto('{csv_path_sql}', header=true)
        ),
        unpivoted AS (
            UNPIVOT raw
            ON * EXCLUDE ({exclude_sql})
            INTO NAME metric VALUE value_num
        )
        SELECT
            canonical_ticker(u.Ticker)      AS scrip,
            '{section}'                     AS section,
            u.metric                        AS metric,
            NULL                            AS period_raw,
            parse_ad_fy_short(u.Year)       AS fiscal_year_bs,
            u.Quarter                       AS quarter,
            CAST(u.value_num AS VARCHAR)    AS value_raw,
            TRY_CAST(u.value_num AS DOUBLE) AS value_num,
            TIMESTAMPTZ '{iso_ts}'          AS ingested_at,
            '{_SOURCE_NAME}'                AS source,
            '{_SOURCE_TIER}'                AS source_tier,
            '{csv_path.name}'               AS source_file
        FROM unpivoted u
        WHERE u.value_num IS NOT NULL
    """)


def ingest_client_csv_shreyas(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> list[IngestionReport]:
    """Ingest the three Shreyas CSVs into Bronze.

    Returns two IngestionReports: one for bronze.fundamentals_raw (long
    BS+IS) and one for bronze.additional_info_raw (wide ratio block)."""
    started_at = datetime.now(timezone.utc)
    iso_ts = started_at.isoformat()
    settings = settings or get_settings()

    bs_path = _find_csv(input_dir, "cbbalancesheet2_")
    is_path = _find_csv(input_dir, "cbincomestatement_")
    ai_path = _find_csv(input_dir, "cbadditionalinfo_")

    conn = duckdb.connect(":memory:")
    try:
        _register_udfs(conn)

        # --- Long-format: BS + IS unpivoted, unioned, dedup on key -----------
        bs_rel = _unpivot_long(conn, bs_path, _BS_KEY_COLS, "shreyas_bs", iso_ts)
        is_rel = _unpivot_long(conn, is_path, _IS_KEY_COLS, "shreyas_is", iso_ts)
        conn.register("bs_long", bs_rel)
        conn.register("is_long", is_rel)
        fundamentals_long = conn.execute("""
            SELECT * FROM bs_long
            UNION ALL
            SELECT * FROM is_long
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY scrip, fiscal_year_bs, quarter, section, metric
                ORDER BY ingested_at DESC
            ) = 1
        """).to_arrow_table()

        # --- Wide-format additional info (ratios, capital, per-share) --------
        ai_csv_sql = str(ai_path).replace("'", "''")
        ai_exclude_sql = ", ".join(f'"{c}"' for c in _AI_KEY_COLS)
        additional_info_wide = conn.execute(f"""
            SELECT
                canonical_ticker(Ticker)    AS scrip,
                parse_ad_fy_short(Year)     AS fiscal_year_bs,
                Quarter                     AS quarter,
                * EXCLUDE ({ai_exclude_sql}),
                TIMESTAMPTZ '{iso_ts}'      AS ingested_at,
                '{_SOURCE_NAME}'            AS source,
                '{_SOURCE_TIER}'            AS source_tier,
                '{ai_path.name}'            AS source_file
            FROM read_csv_auto('{ai_csv_sql}', header=true)
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY canonical_ticker(Ticker), parse_ad_fy_short(Year), Quarter
                ORDER BY idcbadditionalinfo DESC
            ) = 1
        """).to_arrow_table()

        bs_rows = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{str(bs_path).replace(chr(39), chr(39)*2)}')").fetchone()[0]
        is_rows = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{str(is_path).replace(chr(39), chr(39)*2)}')").fetchone()[0]
        ai_rows = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{str(ai_path).replace(chr(39), chr(39)*2)}')").fetchone()[0]
    finally:
        conn.close()

    io = DeltaIO(settings)
    # fundamentals_raw is shared with Format B + scraper — use partition-aware
    # upsert so we only replace *our* (Shreyas) rows. additional_info_raw is
    # Shreyas-only so a plain overwrite is fine and widens schema on first write.
    if mode == "overwrite":
        io.upsert_source_partition(_FUNDAMENTALS_TABLE, fundamentals_long, source=_SOURCE_NAME)
        io.write(
            _ADDITIONAL_INFO_TABLE, additional_info_wide,
            mode="overwrite", schema_mode="overwrite",
        )
    else:
        io.write(_FUNDAMENTALS_TABLE, fundamentals_long, mode=mode)
        io.write(_ADDITIONAL_INFO_TABLE, additional_info_wide, mode=mode)

    return [
        IngestionReport(
            table=_FUNDAMENTALS_TABLE,
            rows_read=bs_rows + is_rows,
            rows_written=fundamentals_long.num_rows,
            source_files=2,
            delta_version=io.version(_FUNDAMENTALS_TABLE),
            started_at=started_at,
        ),
        IngestionReport(
            table=_ADDITIONAL_INFO_TABLE,
            rows_read=ai_rows,
            rows_written=additional_info_wide.num_rows,
            source_files=1,
            delta_version=io.version(_ADDITIONAL_INFO_TABLE),
            started_at=started_at,
        ),
    ]
