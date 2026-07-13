"""Factory for ComputeEngine. Reads COMPUTE_ENGINE env var to pick an impl."""
from __future__ import annotations
import os
from typing import Literal

from .duckdb_engine import DuckDBEngine
from .engine import ComputeEngine
from .spark_engine import SparkEngine

EngineName = Literal["duckdb", "spark"]


def make_engine(name: EngineName | None = None) -> ComputeEngine:
    """Construct the configured engine.

    Precedence: explicit `name` > `COMPUTE_ENGINE` env > 'duckdb'."""
    chosen = name or os.getenv("COMPUTE_ENGINE", "duckdb").lower()
    if chosen == "duckdb":
        return DuckDBEngine()
    if chosen == "spark":
        return SparkEngine()
    raise ValueError(f"Unknown COMPUTE_ENGINE {chosen!r}; expected 'duckdb' or 'spark'")
