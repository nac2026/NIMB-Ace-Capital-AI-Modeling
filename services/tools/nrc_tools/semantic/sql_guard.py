"""SQL guard — validate that an LLM-generated query is a safe, read-only SELECT
over allow-listed tables, then cap its row count.

Uses sqlglot AST parsing (NOT regex) for robustness:
  * exactly one statement
  * the statement is a SELECT / WITH-SELECT / set-operation — never DML or DDL
  * no `Command` nodes (SET, COPY, CALL, VACUUM, etc.)
  * every referenced table is in the allow-list (CTE names exempted)
  * a hard LIMIT is wrapped around the whole query

This is the primary guard; execution additionally runs in a READ ONLY
transaction with a statement timeout (defense in depth)."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

# Expression types that must never appear in a read-only query.
_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge,
    exp.Drop, exp.Create, exp.Alter, exp.TruncateTable,
    exp.Grant, exp.Command,   # Command catches SET/COPY/CALL/VACUUM/etc.
)


class SqlGuardError(Exception):
    """Raised when a query fails validation. Message is safe to show the model."""


def guard_select_sql(sql: str, allowed_tables: frozenset[str], *, max_rows: int = 1000) -> str:
    """Validate `sql` and return an execution-safe, row-capped query string.

    Raises SqlGuardError with an explanatory message on any violation."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise SqlGuardError("empty query")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception as e:  # noqa: BLE001
        raise SqlGuardError(f"could not parse SQL: {e}") from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SqlGuardError("exactly one statement is allowed")
    stmt = statements[0]

    # Top-level must be a query (Select, Union/Intersect/Except, or a WITH wrapper).
    if not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery, exp.With)):
        raise SqlGuardError("only SELECT queries are permitted")

    # No write/DDL/command nodes anywhere in the tree.
    for node in stmt.walk():
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, _FORBIDDEN):
            raise SqlGuardError(f"statement type not permitted: {type(node).__name__}")

    # Collect CTE names (these are valid table references that aren't real tables).
    cte_names = {c.alias_or_name.lower() for c in stmt.find_all(exp.CTE)}

    allowed_lower = {t.lower() for t in allowed_tables}
    for table in stmt.find_all(exp.Table):
        name = (table.name or "").lower()
        schema = (table.db or "").lower()
        if name in cte_names and not schema:
            continue
        if schema and schema not in ("public", ""):
            raise SqlGuardError(f"schema not permitted: {schema}")
        if name not in allowed_lower:
            raise SqlGuardError(f"table not permitted: {table.name}")

    # Wrap to enforce a hard row cap regardless of inner structure.
    inner = stmt.sql(dialect="postgres")
    return f"SELECT * FROM (\n{inner}\n) AS _guarded LIMIT {int(max_rows)}"
