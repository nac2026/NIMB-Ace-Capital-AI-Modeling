"""Delta Lake I/O wrapper. Reads + writes tables on MinIO via delta-rs.

The whole lakehouse is three layers of tables (bronze/silver/gold) under one
S3 bucket. A `table_name` like 'silver.prices' maps to
's3://nepse-lakehouse/silver/prices/'. Passing the mapping through one module
means the Spark migration later touches only this file."""
from __future__ import annotations
from typing import Any, Literal

import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from .config import StorageSettings, get_settings

WriteMode = Literal["append", "overwrite", "error", "ignore"]
SchemaMode = Literal["merge", "overwrite"]


class DeltaIO:
    """Façade over delta-rs. One instance reads/writes any table in the lakehouse."""

    def __init__(self, settings: StorageSettings | None = None):
        self._settings = settings or get_settings()
        self._storage_options = self._settings.delta_storage_options()
        self._lakehouse = self._settings.lakehouse_uri.rstrip("/")

    def table_uri(self, table_name: str) -> str:
        """`'silver.prices'` -> `'s3://nepse-lakehouse/silver/prices'`.

        The single dot convention separates layer from table name; downstream
        code refers to tables symbolically rather than hard-coding paths."""
        if "." not in table_name:
            raise ValueError(f"table_name must be 'layer.name' (e.g. 'silver.prices'), got {table_name!r}")
        layer, name = table_name.split(".", 1)
        if layer not in {"bronze", "silver", "gold"}:
            raise ValueError(f"layer must be bronze|silver|gold, got {layer!r}")
        return f"{self._lakehouse}/{layer}/{name}"

    def exists(self, table_name: str) -> bool:
        """True if the Delta table has been created (at least one commit)."""
        try:
            DeltaTable(self.table_uri(table_name), storage_options=self._storage_options)
            return True
        except Exception:
            return False

    def read(self, table_name: str, *, columns: list[str] | None = None) -> pa.Table:
        """Read a Delta table into pyarrow. Columns arg prunes at the Parquet level."""
        dt = DeltaTable(self.table_uri(table_name), storage_options=self._storage_options)
        return dt.to_pyarrow_table(columns=columns)

    def read_parquet(self, table_name: str, *, columns: list[str] | None = None) -> pa.Table:
        """Read a plain Parquet file into pyarrow.

        dbt-duckdb materializes Gold models as Parquet (the delta-write plugin
        is unsupported in dbt-duckdb 1.9.x), while our Bronze+Silver writes
        stay on Delta. This method is the second-format reader for
        `sync_postgres` and anywhere else Gold data is needed.

        The incoming `table_name` follows the same `layer.name` convention
        (e.g. `gold.peer_rankings_quarterly`); we append `.parquet` to match
        the `gold_external_location()` macro in dbt/.

        Uses pyarrow's S3FileSystem with MinIO endpoint config explicitly —
        pyarrow's native `from_uri` path talks to real AWS S3 and can't be
        redirected to a local MinIO. The filesystem + key-path form
        bypasses URI resolution."""
        import pyarrow.parquet as pq
        from pyarrow.fs import S3FileSystem
        from urllib.parse import urlparse

        endpoint = urlparse(self._settings.minio_endpoint)
        fs = S3FileSystem(
            access_key=self._settings.minio_root_user,
            secret_key=self._settings.minio_root_password,
            endpoint_override=endpoint.netloc or endpoint.path,
            region=self._settings.minio_region,
            scheme=endpoint.scheme or "http",
            allow_bucket_creation=False,
            allow_bucket_deletion=False,
        )
        # S3FileSystem takes bucket-relative keys, not full s3:// URIs.
        uri = self.table_uri(table_name) + ".parquet"
        # Strip s3:// prefix: `s3://nepse-lakehouse/gold/foo.parquet` → `nepse-lakehouse/gold/foo.parquet`
        key = uri.replace("s3://", "", 1)
        return pq.read_table(key, columns=columns, filesystem=fs)

    def write(
        self,
        table_name: str,
        data: pa.Table | pa.RecordBatchReader,
        *,
        mode: WriteMode = "append",
        partition_by: list[str] | None = None,
        schema_mode: SchemaMode | None = None,
        predicate: str | None = None,
    ) -> None:
        """Write (or append/overwrite) a Delta table.

        `partition_by` only applies at table-creation time; subsequent writes
        inherit the existing partition scheme. Keep partition cardinality low
        (e.g. by fiscal_year_bs or date year) — high-cardinality partitions
        create thousands of tiny files and wreck query latency.

        `schema_mode` controls schema evolution. `None` (default) errors on
        any schema drift. `'merge'` adds new nullable columns present in the
        incoming batch. `'overwrite'` (only valid with mode='overwrite')
        replaces the stored schema with the incoming one — use when widening
        a Bronze table to carry new source columns like `source_tier`.

        `predicate` (only valid with mode='overwrite') limits the overwrite
        to rows matching the SQL expression — enables per-source partition
        overwrite without touching rows from other sources. Example:
        `predicate=\"source = 'client_csv_shreyas'\"` lets the Shreyas
        adapter refresh its rows without wiping Format B or scraper rows."""
        kwargs: dict[str, Any] = {
            "mode": mode,
            "partition_by": partition_by,
            "storage_options": self._storage_options,
        }
        if schema_mode is not None:
            kwargs["schema_mode"] = schema_mode
        if predicate is not None:
            kwargs["predicate"] = predicate
        write_deltalake(self.table_uri(table_name), data, **kwargs)

    def upsert_source_partition(
        self,
        table_name: str,
        data: pa.Table | pa.RecordBatchReader,
        *,
        source: str,
        partition_col: str = "source",
    ) -> None:
        """Replace all rows where `partition_col = source` with the incoming batch.

        On first write (table doesn't exist yet) this creates the table with
        full-overwrite semantics. On subsequent writes it uses delta-rs's
        predicate overwrite to touch only the rows belonging to this source —
        other sources' rows are left intact. Essential for Bronze tables
        shared between multiple ingesters (e.g. Shreyas + Format B +
        scraper all land in bronze.fundamentals_raw)."""
        if self.exists(table_name):
            self.write(
                table_name, data,
                mode="overwrite",
                predicate=f"{partition_col} = '{source}'",
            )
        else:
            self.write(
                table_name, data,
                mode="overwrite",
                schema_mode="overwrite",
            )

    def version(self, table_name: str) -> int:
        """Current version number of the table (monotonically increasing)."""
        dt = DeltaTable(self.table_uri(table_name), storage_options=self._storage_options)
        return dt.version()

    def history(self, table_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Recent commit history — useful for debugging pipeline runs."""
        dt = DeltaTable(self.table_uri(table_name), storage_options=self._storage_options)
        return dt.history(limit=limit)

    def vacuum(self, table_name: str, retention_hours: int = 168) -> list[str]:
        """Remove data files no longer referenced by any version >= retention threshold."""
        dt = DeltaTable(self.table_uri(table_name), storage_options=self._storage_options)
        return dt.vacuum(retention_hours=retention_hours, dry_run=False)
