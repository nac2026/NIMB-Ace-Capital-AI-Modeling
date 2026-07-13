"""describe_schema(tables?) → the serving-layer schema the copilot can query.

With no arguments: returns every queryable table name (grouped) so the model can
see what exists. With `tables`: returns full column lists for those tables so the
model can write correct SQL for query_database. Introspected live from Postgres,
so new pipeline tables appear automatically."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import _timed, build_response
from .semantic import get_catalog

TOOL_NAME = "describe_schema"


class DescribeSchemaInput(BaseModel):
    tables: list[str] | None = Field(
        default=None,
        description="Specific tables to get full column lists for. Omit to list all queryable tables.",
    )


def describe_schema(
    tables: list[str] | None = None,
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[dict]:
    pg = pg or PostgresClient()
    with _timed() as t:
        cat = get_catalog(pg)
        if tables:
            wanted = [tb.strip() for tb in tables if tb and tb.strip()]
            schema_text = cat.describe(only=wanted)
            payload = {"schema": schema_text, "tables": wanted}
        else:
            payload = {
                "tables": sorted(cat.tables),
                "n_tables": len(cat.tables),
                "hint": "Call describe_schema(tables=[...]) for columns, then query_database(sql).",
            }
    return build_response(
        tool=TOOL_NAME, data=payload, sources=["postgres.information_schema"],
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Discover the queryable serving schema. No args → all table names. "
        "With tables=[...] → full column lists (name + type) for those tables. "
        "Use this to plan a query_database call when no dedicated tool covers "
        "the question."
    ),
    "input_schema": DescribeSchemaInput.model_json_schema(),
}
