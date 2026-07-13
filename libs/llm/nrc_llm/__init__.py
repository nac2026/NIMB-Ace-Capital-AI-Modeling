"""LLM provider abstraction — Vertex Gemini today, Claude-on-Vertex later."""
from __future__ import annotations

__version__ = "0.1.0"

from .base import LLMClient
from .config import LLMSettings, get_llm_settings
from .mock import MockLLMClient
from .router import LLMRouter, get_router
from .types import CompletionResult, Message, Role, StreamChunk, TokenUsage, ToolCallRequest
from .vertex_gemini import VertexGeminiClient

__all__ = [
    "LLMClient",
    "LLMSettings",
    "get_llm_settings",
    "LLMRouter",
    "get_router",
    "MockLLMClient",
    "VertexGeminiClient",
    "CompletionResult",
    "Message",
    "Role",
    "StreamChunk",
    "TokenUsage",
    "ToolCallRequest",
]
