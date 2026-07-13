"""Serving-schema catalog — introspected from Postgres information_schema.

This is the single source of truth for (a) the table/column allow-list the SQL
guard enforces, and (b) the schema description the LLM reads to write correct
SQL. Introspecting (rather than hand-maintaining) means every new serving table
the pipeline adds is automatically queryable — no per-metric tool needed.

Cached per process; call refresh() after a migration adds tables."""
from __future__ import annotations

from dataclasses import dataclass, field

from nrc_storage import PostgresClient

# Operational / internal tables the copilot must not query.
_EXCLUDED_TABLES: frozenset[str] = frozenset({
    "schema_migrations",
    "query_traces",
    "feed_cursors",
    "tick_history",            # huge append-only audit; use live_quotes instead
    "analysis_sessions",
    "analysis_results",
    "analysis_chat_turns",
    "analysis_claims",
    "analysis_aspects",
    "analysis_debate",
})


@dataclass
class TableInfo:
    name: str
    columns: list[tuple[str, str]] = field(default_factory=list)  # (column, data_type)


@dataclass
class SchemaCatalog:
    tables: dict[str, TableInfo]

    @property
    def allowed_tables(self) -> frozenset[str]:
        return frozenset(self.tables)

    def describe(self, only: list[str] | None = None, max_tables: int | None = None) -> str:
        """Compact text schema for the LLM: `table(col type, col type, ...)`."""
        names = only if only else sorted(self.tables)
        if max_tables:
            names = names[:max_tables]
        lines = []
        for name in names:
            t = self.tables.get(name)
            if not t:
                continue
            cols = ", ".join(f"{c} {ty}" for c, ty in t.columns)
            lines.append(f"{name}({cols})")
        return "\n".join(lines)


_CACHE: SchemaCatalog | None = None


def _introspect(pg: PostgresClient) -> SchemaCatalog:
    rows = pg.fetch_all(
        """
        SELECT table_name, column_name, data_type, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    tables: dict[str, TableInfo] = {}
    for r in rows:
        name = r["table_name"]
        if name in _EXCLUDED_TABLES:
            continue
        tables.setdefault(name, TableInfo(name=name)).columns.append(
            (r["column_name"], r["data_type"])
        )
    return SchemaCatalog(tables=tables)


def get_catalog(pg: PostgresClient | None = None, *, refresh: bool = False) -> SchemaCatalog:
    """Return the cached serving-schema catalog, introspecting on first use."""
    global _CACHE
    if _CACHE is None or refresh:
        pg = pg or PostgresClient()
        _CACHE = _introspect(pg)
    return _CACHE
