"""Format-B prices ingest (close-only daily history).

Input: per-scrip CSVs under `<OneDrive>/Commercial bank/Commercial bank Price 5 years/`
One file per ticker (filename = ticker, e.g. `NABIL.csv`, `NEPAL SBI.csv`).
Each file is headerless with two columns: ISO date and close price.
Coverage extends back to 2011-07-17 — ~14 years of close-only daily data.

Output: `bronze.closes_raw` (new table — distinct from `bronze.prices_raw`
because this source has no OHLCV, only Close). Tagged source_tier=
client_historical so scraper OHLCV rows still win for overlapping dates in
Silver when the DailyBar path runs.

Why a separate Bronze table: OHLCV rows and close-only rows have genuinely
different schemas. Mixing them under one Bronze schema with nullable OHLV
columns would push `Optional` handling into every downstream query. Keeping
them split means Gold indicator computation (which only needs close) unions
silver.prices + silver.closes cleanly, while candlestick-drawing tools
consume silver.prices with strict non-null OHLCV guarantees."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_TABLE = "bronze.closes_raw"
_SOURCE_NAME = "client_csv_format_b"
_SOURCE_TIER = SourceTier.CLIENT_HISTORICAL.value


def ingest_client_csv_format_b_prices(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest every close-only CSV under `input_dir` into bronze.closes_raw.

    Filename (minus extension) becomes the ticker, then normalized through
    `canonical_ticker` so `NEPAL SBI.csv` lands under scrip='SBI'."""
    started_at = datetime.now(timezone.utc)
    iso_ts = started_at.isoformat()
    settings = settings or get_settings()

    files = sorted(input_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no *.csv under {input_dir}")

    conn = duckdb.connect(":memory:")
    try:
        conn.create_function("canonical_ticker", canonical_ticker, ["VARCHAR"], "VARCHAR")

        glob_sql = str(input_dir / "*.csv").replace("'", "''")
        # `filename=true` injects the source path per row. We strip to the
        # basename and drop `.csv` to recover the ticker.
        # Files are header-less: columns are [date, close]. Force names.
        raw_count = conn.execute(f"""
            SELECT COUNT(*)
            FROM read_csv_auto('{glob_sql}', header=false,
                               columns={{'date': 'DATE', 'close': 'DOUBLE'}})
        """).fetchone()[0]

        table = conn.execute(f"""
            SELECT
                canonical_ticker(
                    regexp_replace(regexp_extract(filename, '[^/]+$'), '\\.csv$', '')
                )                               AS scrip,
                date                            AS date,
                close                           AS close,
                TIMESTAMPTZ '{iso_ts}'          AS ingested_at,
                '{_SOURCE_NAME}'                AS source,
                '{_SOURCE_TIER}'                AS source_tier,
                regexp_extract(filename, '[^/]+$') AS source_file
            FROM read_csv_auto('{glob_sql}', header=false,
                               columns={{'date': 'DATE', 'close': 'DOUBLE'}},
                               filename=true)
            WHERE close > 0
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY canonical_ticker(
                    regexp_replace(regexp_extract(filename, '[^/]+$'), '\\.csv$', '')
                ), date
                ORDER BY filename
            ) = 1
        """).to_arrow_table()
    finally:
        conn.close()

    io = DeltaIO(settings)
    # bronze.closes_raw is Format-B-only today but using source partition
    # keeps it friendly for future sources writing close-only series.
    if mode == "overwrite":
        io.upsert_source_partition(_TABLE, table, source=_SOURCE_NAME)
    else:
        io.write(_TABLE, table, mode=mode)

    return IngestionReport(
        table=_TABLE,
        rows_read=raw_count,
        rows_written=table.num_rows,
        source_files=len(files),
        delta_version=io.version(_TABLE),
        started_at=started_at,
    )
