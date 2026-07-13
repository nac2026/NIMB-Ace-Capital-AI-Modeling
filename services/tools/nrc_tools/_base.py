"""Shared primitives for all research tools.

Every tool produces a ToolResponse[T] envelope. This module handles the
plumbing — timing, metadata assembly, error wrapping — so each individual
tool (get_quote, get_fundamentals, ...) stays focused on its query."""
from __future__ import annotations
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from nrc_contracts import ToolMetadata, ToolResponse

from ._version import TOOL_VERSION


@contextmanager
def _timed() -> Iterator[dict]:
    """Context manager that yields a dict; on exit it has 'latency_ms' populated."""
    info: dict = {}
    t0 = time.perf_counter()
    try:
        yield info
    finally:
        info["latency_ms"] = int((time.perf_counter() - t0) * 1000)


def build_response(
    *,
    tool: str,
    data,
    sources: list[str],
    data_as_of: datetime | None = None,
    latency_ms: int = 0,
    warnings: list[str] | None = None,
):
    """Assemble a ToolResponse[T] from payload + metadata.

    `data_as_of` defaults to now(UTC) — tools should override with the actual
    timestamp of the underlying data (e.g. last close date for get_quote)
    so the LLM can warn when data is stale."""
    metadata = ToolMetadata(
        tool=tool,
        tool_version=TOOL_VERSION,
        data_as_of=data_as_of or datetime.now(timezone.utc),
        sources=sources,
        latency_ms=latency_ms,
        warnings=warnings or [],
    )
    # Build response via dict keys so the generic TData is inferred from `data`.
    return ToolResponse(data=data, metadata=metadata)


class ToolError(Exception):
    """Raised by a tool when it cannot satisfy the request.

    Examples: unknown scrip, no data for the requested quarter, upstream
    DB unreachable. The orchestrator catches these, logs them to the trace,
    and asks the LLM to explain the gap to the user."""

    def __init__(self, message: str, *, tool: str, reason: str):
        super().__init__(message)
        self.tool = tool
        self.reason = reason  # machine-readable: 'not_found', 'stale', 'db_error', ...


__all__ = ["build_response", "_timed", "ToolError"]
