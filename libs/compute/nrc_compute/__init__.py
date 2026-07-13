"""ComputeEngine abstraction — DuckDB (local) / Spark (prod)."""
from __future__ import annotations

__version__ = "0.1.0"

from .duckdb_engine import DuckDBEngine
from .engine import ComputeEngine
from .factory import EngineName, make_engine
from .spark_engine import SparkEngine

__all__ = [
    "ComputeEngine",
    "DuckDBEngine",
    "SparkEngine",
    "EngineName",
    "make_engine",
]
