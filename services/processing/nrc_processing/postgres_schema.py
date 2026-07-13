"""Tiny migration runner for `infra/postgres/schema/*.sql`.

We deliberately skip Alembic for the prototype — every migration file in
`infra/postgres/schema/` is pure SQL, applied in filename order, recorded
in a `schema_migrations` table. Simple, versioned, idempotent. When we
actually need autogenerate / downgrade / branching, swap in Alembic (the
file layout translates directly)."""
from __future__ import annotations
from pathlib import Path

from nrc_storage import PostgresClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_DIR = _REPO_ROOT / "infra" / "postgres" / "schema"

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version      TEXT PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def apply_migrations(
    *,
    pg: PostgresClient | None = None,
    schema_dir: Path = _SCHEMA_DIR,
) -> list[str]:
    """Apply every SQL file in `schema_dir` in name order, skipping ones already
    recorded in schema_migrations. Returns the list of newly-applied versions."""
    pg = pg or PostgresClient()
    applied: list[str] = []
    try:
        pg.execute(_BOOTSTRAP)
        rows = pg.fetch_all("SELECT version FROM schema_migrations")
        already = {r["version"] for r in rows}

        for sql_file in sorted(schema_dir.glob("*.sql")):
            version = sql_file.name
            if version in already:
                continue
            sql = sql_file.read_text()
            with pg.transaction() as conn:
                conn.execute(sql)  # type: ignore[arg-type]
                conn.execute(
                    "INSERT INTO schema_migrations(version) VALUES (%s)",
                    (version,),
                )
            applied.append(version)
    finally:
        pg.close()
    return applied
