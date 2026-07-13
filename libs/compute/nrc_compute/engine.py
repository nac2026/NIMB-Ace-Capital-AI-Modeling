"""ComputeEngine protocol — the contract every query engine must satisfy.

Bronze/Silver/Gold transforms take a `ComputeEngine` as a dependency and call
`.sql(...)`. That's the only coupling. Today the concrete class is DuckDBEngine;
at DGX Spark time we swap in SparkEngine and the transform code is untouched."""
from __future__ import annotations
from typing import Protocol, runtime_checkable

import pyarrow as pa


@runtime_checkable
class ComputeEngine(Protocol):
    """SQL-over-Delta interface. Implementations: DuckDBEngine, SparkEngine."""

    def register_table(self, name: str, table: str) -> None:
        """Expose a Delta table (e.g. 'silver.prices') as a SQL identifier (`name`).

        `table` uses the same 'layer.table' convention as DeltaIO.table_uri,
        which the engine resolves internally to the physical s3:// URI."""
        ...

    def sql(self, query: str) -> pa.Table:
        """Execute a SELECT and return the full result as a pyarrow Table."""
        ...

    def execute(self, statement: str) -> None:
        """Execute a DDL / CTAS / non-returning statement."""
        ...

    def close(self) -> None:
        """Release connections / stop sessions. Safe to call more than once."""
        ...
