"""SparkEngine — placeholder for production (DGX Spark on-prem).

Intentionally stubbed: we don't want PySpark in the prototype dependency
closure. This exists so the Protocol is concrete enough to catch interface
drift in code review. At migration time, fill it in with a SparkSession
configured against the Delta Lake warehouse on DGX."""
from __future__ import annotations

import pyarrow as pa


class SparkEngine:
    """Production ComputeEngine. Not implemented until DGX migration."""

    def __init__(self, *args: object, **kwargs: object):
        raise NotImplementedError(
            "SparkEngine is stubbed for the prototype. Implement at DGX migration "
            "time using pyspark + delta-spark against the on-prem warehouse."
        )

    def register_table(self, name: str, table: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def sql(self, query: str) -> pa.Table:  # pragma: no cover
        raise NotImplementedError

    def execute(self, statement: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        raise NotImplementedError
