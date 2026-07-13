"""Postgres connection pool + small helpers.

Backed by psycopg3's built-in pool. Every query funnels through one of three
entry points: `execute`, `fetch_one`, `fetch_all`. Transactions are explicit
via the `transaction()` context manager."""
from __future__ import annotations
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import StorageSettings, get_settings


class PostgresClient:
    """Thin pooled psycopg client. Safe to share across threads."""

    def __init__(self, settings: StorageSettings | None = None):
        self._settings = settings or get_settings()
        self._pool = ConnectionPool(
            conninfo=self._settings.postgres_url,
            min_size=self._settings.postgres_pool_min,
            max_size=self._settings.postgres_pool_max,
            open=False,
        )

    def open(self) -> None:
        """Open the pool. Call once at startup — or let connection() lazy-open."""
        self._pool.open()
        self._pool.wait()

    def close(self) -> None:
        """Close the pool. Call on shutdown."""
        self._pool.close()

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Check out a connection from the pool. Autocommit per-statement."""
        if self._pool.closed:
            self._pool.open()
        with self._pool.connection() as conn:
            yield conn

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Explicit transaction block. Rolls back on exception."""
        with self.connection() as conn, conn.transaction():
            yield conn

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> int:
        """Run a statement with no result set. Returns affected row count."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def fetch_one(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetch_all(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def ping(self) -> bool:
        """True if the DB is reachable. Used in health checks."""
        try:
            row = self.fetch_one("SELECT 1 AS ok")
            return row is not None and row["ok"] == 1
        except Exception:
            return False
