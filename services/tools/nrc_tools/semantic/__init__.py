"""Governed query layer — lets the copilot answer arbitrary questions over the
serving tables without a hand-coded tool per metric.

  * catalog.py   — introspects the Postgres serving schema (the allow-list +
                   the descriptions the LLM uses to write correct SQL).
  * sql_guard.py — sqlglot AST validation: single read-only SELECT, only
                   allow-listed tables, row cap. Defense-in-depth with a
                   READ ONLY transaction at execution time.
"""
from __future__ import annotations

from .catalog import SchemaCatalog, get_catalog
from .sql_guard import SqlGuardError, guard_select_sql

__all__ = ["SchemaCatalog", "get_catalog", "guard_select_sql", "SqlGuardError"]
