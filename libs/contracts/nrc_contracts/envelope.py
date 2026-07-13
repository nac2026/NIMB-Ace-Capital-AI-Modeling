"""Generic tool response envelope. Every tool in services/tools wraps its payload in this."""
from __future__ import annotations
from datetime import datetime
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

TData = TypeVar("TData")


class ToolMetadata(BaseModel):
    """Non-data context attached to every tool response. Recorded into query traces."""
    model_config = ConfigDict(extra="forbid")

    tool: str
    tool_version: str
    data_as_of: datetime                             # freshness of underlying data
    sources: list[str]                               # e.g. ["silver.prices","gold.indicators_daily"]
    latency_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class ToolResponse(BaseModel, Generic[TData]):
    """Envelope: `{ data, metadata }`. LLM sees data; metadata recorded in trace."""
    data: TData
    metadata: ToolMetadata
