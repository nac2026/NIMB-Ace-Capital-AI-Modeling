"""Query traces — one row per chat query in Postgres `query_traces`.
Compliance + debug + eval infrastructure in one."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    """One tool invocation inside an agent turn."""
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_version: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int = Field(ge=0)
    started_at: datetime


class QueryTrace(BaseModel):
    """Full trace of one chat query through the orchestrator."""
    model_config = ConfigDict(extra="forbid")

    trace_id: UUID = Field(default_factory=uuid4)
    user_id: str | None = None
    session_id: str | None = None
    query_text: str

    intent_classification: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    final_response: str | None = None

    total_latency_ms: int = Field(ge=0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_used: str | None = None
    cache_hit: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
