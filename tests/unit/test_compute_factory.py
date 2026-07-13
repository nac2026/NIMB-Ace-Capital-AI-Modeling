"""Unit tests for the compute engine factory + protocol conformance."""
from __future__ import annotations
import pytest

from nrc_compute import ComputeEngine, DuckDBEngine, SparkEngine, make_engine


def test_factory_unknown_engine_raises():
    with pytest.raises(ValueError, match="Unknown COMPUTE_ENGINE"):
        make_engine("timescale")  # type: ignore[arg-type]


def test_spark_engine_stubbed():
    with pytest.raises(NotImplementedError, match="stubbed"):
        SparkEngine()


def test_duckdb_engine_implements_protocol():
    """Runtime Protocol check — DuckDBEngine must satisfy ComputeEngine."""
    engine = DuckDBEngine()
    try:
        assert isinstance(engine, ComputeEngine)
    finally:
        engine.close()


def test_factory_default_is_duckdb(monkeypatch):
    """With no env var set, default engine is DuckDB."""
    monkeypatch.delenv("COMPUTE_ENGINE", raising=False)
    engine = make_engine()
    try:
        assert isinstance(engine, DuckDBEngine)
    finally:
        engine.close()
