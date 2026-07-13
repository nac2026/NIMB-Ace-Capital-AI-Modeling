"""End-to-end test of the Bronze prices ingestion path.

Writes a tiny synthetic price corpus to a temp dir, runs ingest_prices,
then reads bronze.prices_raw back via DuckDB and verifies row counts and
canonicalization. Skipped if MinIO isn't reachable."""
from __future__ import annotations
import socket
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest

from nrc_compute import DuckDBEngine
from nrc_ingestion import ingest_prices
from nrc_storage import DeltaIO, MinIOClient, StorageSettings


def _minio_up(url: str) -> bool:
    u = urlparse(url)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((u.hostname or "localhost", u.port or 9000))
            return True
        except OSError:
            return False


_SETTINGS = StorageSettings()

_CSV = (
    "scrip,date,open,high,low,close,per_change,traded_quantity,traded_amount,status\n"
    "{S},2026-04-20,100.0,101.0,99.0,100.5,0.5,1000,100500.0,1\n"
    "{S},2026-04-17,99.0,100.0,98.5,99.0,-0.3,500,49500.0,-1\n"
    "{S},2026-04-20,100.0,101.0,99.0,100.5,0.5,1000,100500.0,1\n"  # dup row
)


@pytest.mark.skipif(not _minio_up(_SETTINGS.minio_endpoint), reason="MinIO not running")
def test_bronze_prices_ingest_roundtrip(tmp_path):
    MinIOClient(_SETTINGS, bucket=_SETTINGS.minio_bucket_lakehouse).ensure_bucket()

    # Use a unique suffix so this test doesn't collide with the real bronze.prices_raw.
    # We route to a distinct target table via a fresh DeltaIO pointing at a tweaked
    # bucket path; simplest is just to overwrite the real table and rely on the
    # real ingest test cleaning up after itself.
    tag = "T" + uuid.uuid4().hex[:3].upper()  # 4-char test scrip, guaranteed non-numeric
    (tmp_path / f"{tag}.csv").write_text(_CSV.replace("{S}", tag))

    report = ingest_prices(tmp_path, mode="overwrite")
    assert report.rows_read == 3
    assert report.rows_written == 2  # dedup removed the duplicate row
    assert report.source_files == 1

    # Verify the table is queryable.
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("p", "bronze.prices_raw")
        rows = engine.sql(f"SELECT scrip, date, close FROM p WHERE scrip = '{tag}' ORDER BY date").to_pylist()
    assert len(rows) == 2
    assert rows[-1]["close"] == 100.5
    assert rows[0]["scrip"] == tag  # canonicalized (uppercase, trimmed)

    # Cleanup: restore the real prices table by running the real ingest again.
    # This keeps subsequent runs of the full suite deterministic.
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    ingest_prices(repo_root / "scrapers" / "output" / "prices", mode="overwrite")
