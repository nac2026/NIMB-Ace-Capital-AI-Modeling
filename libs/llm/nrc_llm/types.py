"""Shared message/response types used by every LLM client.

Kept provider-neutral — Gemini, Claude, whatever — so LLMClient has the same
shape everywhere and the orchestrator never has to care which provider ran."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    """One turn in a chat. `tool_calls` populated when assistant requests tools.
    `tool_name`/`tool_result` populated when role=tool returning results."""
    model_config = ConfigDict(extra="forbid")

    role: Role
    content: str = ""
    tool_calls: list["ToolCallRequest"] = Field(default_factory=list)
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_result: dict[str, Any] | None = None


class ToolCallRequest(BaseModel):
    """LLM's request to invoke a tool. `args` is the parsed JSON argument dict."""
    model_config = ConfigDict(extra="forbid")

    id: str                                     # provider-supplied call id
    name: str
    args: dict[str, Any]


class TokenUsage(BaseModel):
    """Token counts reported by the provider. Zero if unknown."""
    input_tokens: int = 0
    output_tokens: int = 0


class CompletionResult(BaseModel):
    """Outcome of one LLM call. `stop_reason` mirrors the provider signal —
    `end_turn` (just text), `tool_use` (requested one or more tool calls),
    `max_tokens` (truncated), `safety` (provider blocked)."""
    model_config = ConfigDict(extra="forbid")

    content: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "safety", "error"] = "end_turn"
    usage: TokenUsage = Field(default_factory=TokenUsage)
    model: str = ""
    latency_ms: int = 0


Message.model_rebuild()


@dataclass
class StreamChunk:
    """One chunk from a streaming LLM call.

    Text chunks arrive mid-stream (done=False, result=None).
    The final sentinel has done=True and result populated with the full
    CompletionResult (including accumulated tool_calls and usage)."""
    text: str = ""
    done: bool = False
    result: "CompletionResult | None" = field(default=None)
