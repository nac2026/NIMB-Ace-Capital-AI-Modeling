"""Two-tier router: INTENT vs SYNTHESIS.

The orchestrator calls `router.intent()` for classifying what tools to invoke
(cheap model) and `router.synthesizer()` for composing the final answer
(more capable model). Construction is memoized so we don't re-init clients
on every turn."""
from __future__ import annotations
from functools import lru_cache

from .base import LLMClient
from .config import LLMSettings, get_llm_settings
from .vertex_gemini import VertexGeminiClient


class LLMRouter:
    """Returns the right client per task tier. Single provider (Vertex) today;
    abstraction in place for a later Claude-on-Vertex tier swap."""

    def __init__(self, settings: LLMSettings | None = None):
        self._settings = settings or get_llm_settings()
        self._intent: LLMClient | None = None
        self._synth: LLMClient | None = None

    def intent(self) -> LLMClient:
        if self._intent is None:
            self._intent = VertexGeminiClient(
                model=self._settings.llm_intent_model,
                settings=self._settings,
            )
        return self._intent

    def synthesizer(self) -> LLMClient:
        if self._synth is None:
            self._synth = VertexGeminiClient(
                model=self._settings.llm_synthesizer_model,
                settings=self._settings,
            )
        return self._synth


@lru_cache(maxsize=1)
def get_router() -> LLMRouter:
    return LLMRouter()
