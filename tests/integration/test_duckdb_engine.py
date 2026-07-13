"""Integration test — DuckDB reads a Delta table on MinIO via delta_scan()."""
from __future__ import annotations
import socket
import uuid
from datetime import date
from urllib.parse import urlparse

import pyarrow as pa
import pytest

from nrc_compute import DuckDBEngine
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


@pytest.mark.skipif(not _minio_up(_SETTINGS.minio_endpoint), reason="MinIO not running")
def test_duckdb_reads_delta_on_minio():
    """Write a Delta table via delta-rs, then SELECT it via DuckDB.

    This is the load-bearing test for the whole compute+storage split:
    it proves the same physical file can be written by one tool and
    queried by another, which is the entire premise of the lakehouse."""
    MinIOClient(_SETTINGS, bucket=_SETTINGS.minio_bucket_lakehouse).ensure_bucket()

    io = DeltaIO(_SETTINGS)
    table = f"bronze._compute_test_{uuid.uuid4().hex[:8]}"
    data = pa.table({
        "scrip": ["NABIL", "ADBL", "NABIL"],
        "date": [date(2026, 4, 20), date(2026, 4, 20), date(2026, 4, 18)],
        "close": [528.0, 412.5, 530.1],
    })
    io.write(table, data, mode="overwrite")

    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("prices", table)
        result = engine.sql("SELECT scrip, AVG(close) AS avg_close FROM prices GROUP BY scrip ORDER BY scrip")

    rows = result.to_pylist()
    assert rows == [
        {"scrip": "ADBL", "avg_close": 412.5},
        {"scrip": "NABIL", "avg_close": pytest.approx(529.05)},
    ]
