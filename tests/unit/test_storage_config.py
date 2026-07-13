"""Unit tests for nrc_storage.config — no live services required."""
from __future__ import annotations
import pytest

from nrc_storage import StorageSettings, get_settings
from nrc_storage.delta_io import DeltaIO


def test_settings_defaults():
    """Defaults are sensible dev-stack values."""
    s = StorageSettings()
    assert s.minio_bucket_lakehouse == "nepse-lakehouse"
    assert s.minio_bucket_snapshots == "raw-snapshots"
    assert s.postgres_url.startswith("postgresql://")
    assert s.redis_url.startswith("redis://")


def test_lakehouse_uri():
    s = StorageSettings(minio_bucket_lakehouse="test-bucket")
    assert s.lakehouse_uri == "s3://test-bucket/"


def test_delta_storage_options_keys():
    """Storage options expose the four fields delta-rs needs for MinIO."""
    opts = StorageSettings().delta_storage_options()
    assert "AWS_ENDPOINT_URL" in opts
    assert "AWS_ACCESS_KEY_ID" in opts
    assert "AWS_SECRET_ACCESS_KEY" in opts
    assert opts["AWS_ALLOW_HTTP"] == "true"
    assert opts["AWS_S3_ALLOW_UNSAFE_RENAME"] == "true"


def test_get_settings_is_cached():
    """Singleton — same instance on repeat calls until cache_clear()."""
    a = get_settings()
    b = get_settings()
    assert a is b
    get_settings.cache_clear()


def test_delta_table_uri_parses_layer():
    """'silver.prices' -> s3://.../silver/prices."""
    io = DeltaIO(StorageSettings(minio_bucket_lakehouse="lakehouse"))
    assert io.table_uri("bronze.prices_raw") == "s3://lakehouse/bronze/prices_raw"
    assert io.table_uri("silver.prices") == "s3://lakehouse/silver/prices"
    assert io.table_uri("gold.indicators_daily") == "s3://lakehouse/gold/indicators_daily"


def test_delta_table_uri_rejects_bad_layer():
    io = DeltaIO(StorageSettings())
    with pytest.raises(ValueError, match="layer must be"):
        io.table_uri("platinum.prices")


def test_delta_table_uri_requires_dot():
    io = DeltaIO(StorageSettings())
    with pytest.raises(ValueError, match="layer.name"):
        io.table_uri("prices")
