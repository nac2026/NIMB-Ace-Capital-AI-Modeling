"""DuckDB-backed ComputeEngine. Reads Delta tables on MinIO via delta_scan().

In-process, embedded — no server, no cluster. Ideal for the prototype and
for single-node on-prem (up to ~100GB hot working set). Swap to SparkEngine
for distributed workloads without touching transform code."""
from __future__ import annotations
from urllib.parse import urlparse

import duckdb
import pyarrow as pa

from nrc_storage import DeltaIO, StorageSettings, get_settings


class DuckDBEngine:
    """ComputeEngine backed by an embedded DuckDB connection.

    Configures S3 credentials once on construction so `delta_scan()` and
    `read_parquet()` against MinIO work without per-query setup."""

    def __init__(self, settings: StorageSettings | None = None, *, database: str = ":memory:"):
        self._settings = settings or get_settings()
        self._delta_io = DeltaIO(self._settings)
        self._conn = duckdb.connect(database)
        self._configure_s3()
        # Load the delta extension once; delta_scan() fails silently without it.
        self._conn.execute("INSTALL delta; LOAD delta;")
        self._conn.execute("INSTALL httpfs; LOAD httpfs;")

    def _configure_s3(self) -> None:
        """Register MinIO as an S3 endpoint via DuckDB's httpfs extension."""
        endpoint = urlparse(self._settings.minio_endpoint)
        # DuckDB wants host[:port] without scheme; use_ssl controls https vs http.
        host_port = endpoint.netloc or endpoint.path
        use_ssl = endpoint.scheme == "https"
        self._conn.execute(f"""
            CREATE OR REPLACE SECRET minio_secret (
                TYPE S3,
                KEY_ID '{self._settings.minio_root_user}',
                SECRET '{self._settings.minio_root_password}',
                REGION '{self._settings.minio_region}',
                ENDPOINT '{host_port}',
                USE_SSL {str(use_ssl).lower()},
                URL_STYLE 'path'
            );
        """)

    # -------------------------------------------------------- ComputeEngine API
    def register_table(self, name: str, table: str) -> None:
        """Create a DuckDB view backed by delta_scan() over the Delta table's URI."""
        uri = self._delta_io.table_uri(table)
        self._conn.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM delta_scan('{uri}')")

    def sql(self, query: str) -> pa.Table:
        # .arrow() returns a streaming RecordBatchReader in DuckDB 1.x,
        # to_arrow_table() explicitly materializes to match the protocol.
        return self._conn.execute(query).to_arrow_table()

    def execute(self, statement: str) -> None:
        self._conn.execute(statement)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    # ------------------------------------------------------------- ergonomics
    def __enter__(self) -> DuckDBEngine:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
