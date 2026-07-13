"""Ingest Aabishkar2/nepse-data company-wise CSVs → bronze.prices_raw.

The repo CSV header is::

    published_date,open,high,low,close,per_change,traded_quantity,traded_amount,status

which maps almost 1:1 onto bronze.prices_raw (the same schema the SMTM EOD
adapter writes): traded_quantity→volume, traded_amount→turnover, filename→scrip.

Two modes:
  * `input_dir` given  → ingest local *.csv (offline / reproducible).
  * `input_dir` None   → download the repo's data/company-wise/*.csv first
                         (default for the scheduled fallback asset).
"""
from __future__ import annotations
import json
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_TABLE = "bronze.prices_raw"
_SOURCE_NAME = "github_nepse_data"
_SOURCE_TIER = SourceTier.SCRAPED.value  # lowest tier — SMTM live_api always wins on overlap

_CONTENTS_API = "https://api.github.com/repos/Aabishkar2/nepse-data/contents/data/company-wise"
_USER_AGENT = "nrc-ingestion (+https://github.com/Aabishkar2/nepse-data backfill)"


def _http_get(url: str, *, accept: str = "*/*", timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        return resp.read()


def _download_repo(dest_dir: Path) -> int:
    """Download every data/company-wise/*.csv into `dest_dir`. Returns file count."""
    listing = json.loads(
        _http_get(_CONTENTS_API, accept="application/vnd.github+json").decode("utf-8")
    )
    targets = [
        (item["name"], item["download_url"])
        for item in listing
        if item.get("type") == "file" and item["name"].endswith(".csv") and item.get("download_url")
    ]
    if not targets:
        raise RuntimeError("GitHub listing returned no company-wise CSVs (rate-limited?)")

    def _fetch(name_url: tuple[str, str]) -> None:
        name, url = name_url
        (dest_dir / name).write_bytes(_http_get(url))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_fetch, targets))
    return len(targets)


def _ingest_dir(input_dir: Path, *, settings: StorageSettings, mode: str) -> IngestionReport:
    started_at = datetime.now(timezone.utc)
    iso_ts = started_at.isoformat()
    glob = str(input_dir / "*.csv").replace("'", "''")

    conn = duckdb.connect(":memory:")
    try:
        conn.create_function("canonical_ticker", canonical_ticker, ["VARCHAR"], "VARCHAR")
        raw_count = conn.execute(
            f"SELECT COUNT(*) FROM read_csv_auto('{glob}', filename=true)"
        ).fetchone()[0]
        table = conn.execute(f"""
            SELECT
                canonical_ticker(regexp_extract(filename, '([^/]+)\\.csv$', 1)) AS scrip,
                published_date::DATE                                  AS date,
                TRY_CAST(open AS DOUBLE)                              AS open,
                TRY_CAST(high AS DOUBLE)                              AS high,
                TRY_CAST(low AS DOUBLE)                               AS low,
                TRY_CAST(close AS DOUBLE)                             AS close,
                TRY_CAST(NULLIF(per_change, 'nan') AS DOUBLE)         AS per_change,
                CAST(TRY_CAST(traded_quantity AS DOUBLE) AS BIGINT)   AS volume,
                TRY_CAST(traded_amount AS DOUBLE)                     AS turnover,
                CAST(TRY_CAST(status AS DOUBLE) AS INTEGER)           AS status,
                TIMESTAMPTZ '{iso_ts}'                               AS ingested_at,
                '{_SOURCE_NAME}'                                     AS source,
                '{_SOURCE_TIER}'                                     AS source_tier,
                regexp_extract(filename, '[^/]+$')                   AS source_file
            FROM read_csv_auto('{glob}', filename=true, header=true)
            WHERE TRY_CAST(close AS DOUBLE) > 0
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY canonical_ticker(regexp_extract(filename, '([^/]+)\\.csv$', 1)),
                             published_date::DATE
                ORDER BY published_date
            ) = 1
        """).fetch_arrow_table()
    finally:
        conn.close()

    io = DeltaIO(settings)
    # Partition-aware upsert: re-runs replace only our rows, leaving SMTM/scraper
    # rows in the shared bronze.prices_raw table untouched.
    if mode == "overwrite":
        io.upsert_source_partition(_TABLE, table, source=_SOURCE_NAME)
    else:
        io.write(_TABLE, table, mode=mode)

    return IngestionReport(
        table=_TABLE,
        rows_read=raw_count,
        rows_written=table.num_rows,
        source_files=len(list(input_dir.glob("*.csv"))),
        delta_version=io.version(_TABLE),
        started_at=started_at,
    )


def ingest_github_nepse_prices(
    input_dir: Path | None = None,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Backfill bronze.prices_raw from the Aabishkar2/nepse-data repo.

    If `input_dir` is given, ingest the local CSVs there. Otherwise download the
    repo's company-wise CSVs into a temp dir first, then ingest."""
    settings = settings or get_settings()
    if input_dir is not None:
        return _ingest_dir(input_dir, settings=settings, mode=mode)
    with tempfile.TemporaryDirectory(prefix="nepse_data_") as tmp:
        tmp_dir = Path(tmp)
        _download_repo(tmp_dir)
        return _ingest_dir(tmp_dir, settings=settings, mode=mode)
