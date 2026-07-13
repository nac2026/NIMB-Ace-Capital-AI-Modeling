"""query_database(sql) → run a guarded, read-only SELECT over the serving layer.

The escape hatch that makes the copilot non-restrictive: when no dedicated tool
covers a question, the model writes SQL against the introspected serving schema
(see describe_schema) and this tool runs it safely.

Safety (layered):
  1. sqlglot AST guard — single read-only SELECT, only allow-listed tables, no
     DML/DDL/Command nodes (semantic.sql_guard).
  2. hard row cap wrapped around the query.
  3. execution inside a READ ONLY transaction with a statement timeout.

Every executed query (and rejection) is visible in the tool trace, so the audit
log shows exactly what ran."""
from __future__ import annotations

from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response
from .semantic import get_catalog, guard_select_sql
from .semantic.sql_guard import SqlGuardError

TOOL_NAME = "query_database"
_MAX_ROWS = 1000
_TIMEOUT_MS = 8000


class QueryDatabaseInput(BaseModel):
    sql: str = Field(..., description="A single read-only SELECT over the serving tables (Postgres dialect).")
    max_rows: int = Field(_MAX_ROWS, ge=1, le=5000, description="Row cap (default 1000).")


def query_database(
    sql: str,
    *,
    max_rows: int = _MAX_ROWS,
    pg: PostgresClient | None = None,
) -> ToolResponse[dict]:
    pg = pg or PostgresClient()
    cat = get_catalog(pg)

    try:
        safe_sql = guard_select_sql(sql, cat.allowed_tables, max_rows=max_rows)
    except SqlGuardError as e:
        # Surface as a ToolError so the agent learns the constraint and retries.
        raise ToolError(str(e), tool=TOOL_NAME, reason="rejected_sql") from e

    with _timed() as t:
        try:
            with pg.transaction() as conn, conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(f"SET LOCAL statement_timeout = '{_TIMEOUT_MS}'")
                cur.execute(safe_sql)
                rows = cur.fetchall()
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"query failed: {e}", tool=TOOL_NAME, reason="db_error") from e

    payload = {
        "sql": safe_sql,
        "row_count": len(rows),
        "rows": rows,
        "truncated": len(rows) >= max_rows,
    }
    return build_response(
        tool=TOOL_NAME, data=payload, sources=["postgres (read-only)"],
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Run a single read-only SELECT over the NEPSE serving tables and return "
        "the rows. Use ONLY when no dedicated tool answers the question — first "
        "call describe_schema to learn table/column names. Postgres dialect; "
        "joins/aggregates/CTEs allowed; results are row-capped. Never attempt "
        "INSERT/UPDATE/DELETE/DDL — they are rejected."
    ),
    "input_schema": QueryDatabaseInput.model_json_schema(),
}
