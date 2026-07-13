"""Persist query traces to postgres.query_traces.

Every AgentResult → one row. Safe to call synchronously on the request path;
the insert is ~2ms and the table is append-only with no triggers."""
from __future__ import annotations
import json
import logging

from nrc_contracts import QueryTrace
from nrc_storage import PostgresClient

_log = logging.getLogger("nrc_orchestrator.trace_writer")


def write_trace(trace: QueryTrace, *, pg: PostgresClient | None = None) -> None:
    """Insert a QueryTrace row. Errors are logged, never raised — trace
    logging failures must never break the user-facing request."""
    pg = pg or PostgresClient()
    try:
        pg.execute(
            """
            INSERT INTO query_traces (
                trace_id, user_id, session_id, query_text,
                intent_classification, tool_calls, final_response,
                total_latency_ms, input_tokens, output_tokens,
                model_used, cache_hit, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(trace.trace_id),
                trace.user_id,
                trace.session_id,
                trace.query_text,
                json.dumps(trace.intent_classification) if trace.intent_classification else None,
                json.dumps([tc.model_dump(mode="json") for tc in trace.tool_calls]),
                trace.final_response,
                trace.total_latency_ms,
                trace.input_tokens,
                trace.output_tokens,
                trace.model_used,
                trace.cache_hit,
                trace.created_at,
            ),
        )
    except Exception:
        _log.exception("failed to persist query_trace %s", trace.trace_id)
