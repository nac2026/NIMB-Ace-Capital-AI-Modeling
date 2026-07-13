"""LLMClient protocol — every provider client implements this interface."""
from __future__ import annotations
from typing import Protocol, runtime_checkable

from .types import CompletionResult, Message


@runtime_checkable
class LLMClient(Protocol):
    """The only contract the orchestrator knows about.

    Implementations: VertexGeminiClient (prod), MockLLMClient (tests).
    Future: ClaudeVertexClient (when service-account auth is added)."""

    model: str

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> CompletionResult:
        """One synchronous turn. Returns text + tool_calls (if any) + usage."""
        ...
