"""Scripted LLMClient for tests — returns pre-baked responses in order.

Lets integration tests exercise the orchestrator's full tool-use loop without
hitting Vertex or burning quota. Usage:

    mock = MockLLMClient([
        CompletionResult(tool_calls=[ToolCallRequest(id='1', name='get_quote', args={'scrip':'NABIL'})],
                         stop_reason='tool_use'),
        CompletionResult(content='NABIL closed at Rs.528.', stop_reason='end_turn'),
    ])
    orchestrator.run(..., llm=mock)
"""
from __future__ import annotations
from typing import Iterator

from .types import CompletionResult, Message


class MockLLMClient:
    """Returns responses from a pre-loaded script, in order."""

    model: str = "mock"

    def __init__(self, script: list[CompletionResult]):
        if not script:
            raise ValueError("MockLLMClient requires a non-empty script")
        self._script = list(script)
        self._seen: list[list[Message]] = []

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> CompletionResult:
        self._seen.append(list(messages))
        if not self._script:
            raise RuntimeError("MockLLMClient exhausted its script")
        return self._script.pop(0)

    @property
    def calls_made(self) -> int:
        return len(self._seen)

    @property
    def last_messages(self) -> list[Message]:
        return self._seen[-1] if self._seen else []
