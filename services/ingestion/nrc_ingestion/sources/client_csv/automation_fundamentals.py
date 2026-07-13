"""Multi-sector "Data for Automation" fundamentals ingest.

Input: per-sector tidy CSV trios under `<OneDrive>/Data for Automation/`:

  * `<SECTOR> BS.csv`  — balance sheet
  * `<SECTOR> IS.csv`  — income statement
  * `<SECTOR> KS.csv`  — key stats (per-share, returns, multiples, sector ratios)

where `<SECTOR>` ∈ {CB, DB, Finance, Hotels, Hydro, Investment, Life Ins,
NLI, MFG, MF}. Every file is in the same TIDY layout as the Shreyas dump —
header `"Ticker","Year","Quarter","DataSource",<metrics…>`, one row per
ticker. `Year` is AD short form ('2025/26' → BS 2082) and `Quarter` is 1..4.
Monetary values are in NPR thousands, ratios as decimals, per-share in raw NPR.

Unlike Shreyas (Commercial-Bank only), this dump spans 10 sectors but with
heterogeneous, sector-specific line items. We capture the CROSS-SECTOR key
metrics only (revenue, net/operating profit, total assets, equity, EPS, BVPS,
ROE, ROA, P/E, MVPS, DPS + bank ratios) — see `_metric_map.py` (`auto_*`
sections). Line items with no canonical home stay in Bronze and are dropped
at Silver.

Three companion files in the same folder are NOT in tidy layout and are
skipped here (transposed single-company / empty stubs): `NTC`, `NRM`, `REINS`.

Output: `bronze.fundamentals_raw` (long), tagged source='client_csv_automation',
source_tier='client_authoritative'. Silver treats `client_authoritative` as the
top tier — these fresh published-quarter rows win over Shreyas/Format-B/scraper
rows on any overlapping (scrip, fy, quarter, metric) key."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker, parse_ad_fiscal_year_short
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_FUNDAMENTALS_TABLE = "bronze.fundamentals_raw"
_SOURCE_NAME = "client_csv_automation"
_SOURCE_TIER = SourceTier.CLIENT_AUTHORITATIVE.value

# Columns common to every tidy file that identify the row, not a metric.
_KEY_COLS = ("Ticker", "Year", "Quarter", "DataSource")

# Filename-suffix → Bronze `section` tag. The section keys the (section, metric)
# lookup in _metric_map.py.
_SECTION_BY_SUFFIX: dict[str, str] = {
    "BS": "auto_bs",
    "IS": "auto_is",
    "KS": "auto_ks",
}

# Filename prefixes (before the " BS/IS/KS" suffix) that are NOT in the tidy
# layout — transposed single-company exports (NTC, NRM) or empty 2-ticker
# stubs (REINS). Skipped until/if a dedicated parser is written.
_SKIP_PREFIXES: frozenset[str] = frozenset({"NTC", "NRM", "REINS"})


def _register_udfs(conn: duckdb.DuckDBPyConnection) -> None:
    """Register the ticker/fiscal-year normalizer UDFs (vectorized over the CSV)."""
    conn.create_function("canonical_ticker", canonical_ticker, ["VARCHAR"], "VARCHAR")
    conn.create_function("parse_ad_fy_short", parse_ad_fiscal_year_short, ["VARCHAR"], "INTEGER")


def _discover_files(input_dir: Path) -> list[tuple[Path, str]]:
    """Return (path, section) for every ingestible tidy CSV in `input_dir`.

    Matches `* BS.csv` / `* IS.csv` / `* KS.csv`, skipping the non-tidy
    NTC/NRM/REINS files."""
    found: list[tuple[Path, str]] = []
    for suffix, section in _SECTION_BY_SUFFIX.items():
        for path in sorted(input_dir.glob(f"* {suffix}.csv")):
            prefix = path.name[: -len(f" {suffix}.csv")]
            if prefix in _SKIP_PREFIXES:
                continue
            found.append((path, section))
    return found


def _unpivot_long(
    conn: duckdb.DuckDBPyConnection,
    csv_path: Path,
    section: str,
    iso_ts: str,
) -> "duckdb.DuckDBPyRelation":
    """Read one tidy CSV and unpivot to the bronze.fundamentals_raw long shape.

    Read with `all_varchar=true` so the section-divider columns (textual
    headers like 'KEY FINANCIALS'/'FINANCIAL SECTOR') and duplicate column
    names co-exist with numeric metrics in a single UNPIVOT; `TRY_CAST` then
    drops anything non-numeric."""
    csv_path_sql = str(csv_path).replace("'", "''")
    exclude_sql = ", ".join(f'"{c}"' for c in _KEY_COLS)
    return conn.sql(f"""
        WITH raw AS (
            SELECT * FROM read_csv_auto('{csv_path_sql}', header=true, all_varchar=true)
        ),
        unpivoted AS (
            UNPIVOT raw
            ON * EXCLUDE ({exclude_sql})
            INTO NAME metric VALUE value_str
        )
        SELECT
            canonical_ticker(u.Ticker)      AS scrip,
            '{section}'                     AS section,
            u.metric                        AS metric,
            NULL                            AS period_raw,
            parse_ad_fy_short(u.Year)       AS fiscal_year_bs,
            CAST(u.Quarter AS BIGINT)       AS quarter,
            u.value_str                     AS value_raw,
            TRY_CAST(u.value_str AS DOUBLE) AS value_num,
            TIMESTAMPTZ '{iso_ts}'          AS ingested_at,
            '{_SOURCE_NAME}'                AS source,
            '{_SOURCE_TIER}'                AS source_tier,
            '{csv_path.name}'               AS source_file
        FROM unpivoted u
        WHERE TRY_CAST(u.value_str AS DOUBLE) IS NOT NULL
    """)


def ingest_client_csv_automation(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest the multi-sector 'Data for Automation' CSVs into bronze.fundamentals_raw.

    `mode='overwrite'` uses a partition-aware upsert so re-drops only replace
    this source's rows (Shreyas/Format-B/scraper rows are untouched)."""
    started_at = datetime.now(timezone.utc)
    iso_ts = started_at.isoformat()
    settings = settings or get_settings()

    files = _discover_files(input_dir)
    if not files:
        raise FileNotFoundError(f"no '* BS/IS/KS.csv' tidy files under {input_dir}")

    conn = duckdb.connect(":memory:")
    try:
        _register_udfs(conn)
        rels = [_unpivot_long(conn, path, section, iso_ts) for path, section in files]
        for i, rel in enumerate(rels):
            conn.register(f"auto_{i}", rel)
        union_sql = " UNION ALL ".join(f"SELECT * FROM auto_{i}" for i in range(len(rels)))
        long_table = conn.execute(f"""
            {union_sql}
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY scrip, fiscal_year_bs, quarter, section, metric
                ORDER BY ingested_at DESC
            ) = 1
        """).to_arrow_table()
    finally:
        conn.close()

    io = DeltaIO(settings)
    if mode == "overwrite":
        io.upsert_source_partition(_FUNDAMENTALS_TABLE, long_table, source=_SOURCE_NAME)
    else:
        io.write(_FUNDAMENTALS_TABLE, long_table, mode=mode)

    return IngestionReport(
        table=_FUNDAMENTALS_TABLE,
        rows_read=long_table.num_rows,
        rows_written=long_table.num_rows,
        source_files=len(files),
        delta_version=io.version(_FUNDAMENTALS_TABLE),
        started_at=started_at,
    )
