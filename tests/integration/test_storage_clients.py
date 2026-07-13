"""Integration tests — require docker-compose services to be running.

Each test skips gracefully if its backing service is unreachable, so the suite
remains green on a clean machine without docker up."""
from __future__ import annotations
import socket
import uuid
from datetime import date
from urllib.parse import urlparse

import pyarrow as pa
import pytest

from nrc_storage import DeltaIO, MinIOClient, PostgresClient, RedisClient, StorageSettings


def _port_open(url: str) -> bool:
    """True if a TCP connection to the host:port in `url` succeeds within 500ms."""
    u = urlparse(url)
    host = u.hostname or "localhost"
    port = u.port or (5432 if u.scheme.startswith("postgres") else 6379 if u.scheme == "redis" else 9000)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


_SETTINGS = StorageSettings()


# --------------------------------------------------------------------- MinIO
@pytest.mark.skipif(not _port_open(_SETTINGS.minio_endpoint), reason="MinIO not running")
def test_minio_put_get_roundtrip():
    client = MinIOClient(_SETTINGS, bucket=_SETTINGS.minio_bucket_snapshots)
    client.ensure_bucket()
    key = f"_test/{uuid.uuid4().hex}.txt"
    payload = b"hello nrc"
    client.put_bytes(key, payload, content_type="text/plain")
    assert client.exists(key) is True
    assert client.get_bytes(key) == payload
    assert key in list(client.list_keys(prefix="_test/"))
    client.delete(key)
    assert client.exists(key) is False


# --------------------------------------------------------------------- Delta
@pytest.mark.skipif(not _port_open(_SETTINGS.minio_endpoint), reason="MinIO not running")
def test_delta_write_read_roundtrip():
    # Bootstrap: ensure the lakehouse bucket itself exists before writing Delta files.
    MinIOClient(_SETTINGS, bucket=_SETTINGS.minio_bucket_lakehouse).ensure_bucket()

    io = DeltaIO(_SETTINGS)
    table = f"bronze._test_{uuid.uuid4().hex[:8]}"
    data = pa.table({
        "scrip": ["NABIL", "ADBL"],
        "date": [date(2026, 4, 20), date(2026, 4, 20)],
        "close": [528.0, 412.5],
    })
    io.write(table, data, mode="overwrite")
    assert io.exists(table) is True
    read = io.read(table)
    assert read.num_rows == 2
    assert set(read.column("scrip").to_pylist()) == {"NABIL", "ADBL"}


# ------------------------------------------------------------------ Postgres
@pytest.mark.skipif(not _port_open(_SETTINGS.postgres_url), reason="Postgres not running")
def test_postgres_ping_and_query():
    pg = PostgresClient(_SETTINGS)
    try:
        assert pg.ping() is True
        row = pg.fetch_one("SELECT version() AS v")
        assert row is not None
        assert "PostgreSQL" in row["v"]
    finally:
        pg.close()


# --------------------------------------------------------------------- Redis
@pytest.mark.skipif(not _port_open(_SETTINGS.redis_url), reason="Redis not running")
def test_redis_set_get_incr():
    r = RedisClient(_SETTINGS)
    assert r.ping() is True
    key = f"_test:{uuid.uuid4().hex}"
    r.set_json(key, {"x": 1, "y": [1, 2, 3]}, ttl_seconds=30)
    assert r.get_json(key) == {"x": 1, "y": [1, 2, 3]}
    counter_key = f"_test:ctr:{uuid.uuid4().hex}"
    assert r.incr(counter_key, ttl_seconds=30) == 1
    assert r.incr(counter_key) == 2
    r.delete(key, counter_key)
    assert r.get_json(key) is None
