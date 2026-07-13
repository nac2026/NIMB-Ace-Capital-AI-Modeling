"""LLM-layer settings. Reads Vertex AI credentials from env / .env.

The NRC stack fixes one provider (Vertex AI) and two tiers of models:
  * INTENT tier   — Gemini Flash-Lite: cheap, fast, for classifying which
                    tools to call and with what arguments.
  * SYNTHESIS tier — Gemini 2.5 Pro: capable, longer-context, for the
                    natural-language answer.

Swapping synthesis to Claude-on-Vertex later is a config change, not a code
change — just introduce a ClaudeVertexClient that implements LLMClient and
wire it in LLMRouter."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class LLMSettings(BaseSettings):
    """Vertex AI connection + model tier settings."""
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Vertex AI auth. API-key mode (via GCP Console → Vertex AI Studio → API Keys).
    gcp_vertex_api_key: str = Field(default="")
    gcp_project_id: str = Field(default="")
    gcp_region: str = Field(default="global")

    # Model tiers.
    # Flash (not Pro) is the default synthesizer: with thinking disabled and
    # factual tool-grounded prompts, Flash matches Pro on accuracy and responds
    # in ~3-8s vs 20-30s. Override via LLM_SYNTHESIZER_MODEL env var for queries
    # that genuinely benefit from deeper reasoning (comparative analysis, etc.).
    llm_intent_model: str = Field(default="gemini-2.5-flash-lite")
    llm_synthesizer_model: str = Field(default="gemini-2.5-flash")

    # Budget + reliability guardrails.
    llm_max_input_tokens: int = Field(default=32_000, ge=1)
    llm_max_output_tokens: int = Field(default=4_096, ge=1)
    llm_retries: int = Field(default=3, ge=0, le=10)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)

    def require_api_key(self) -> str:
        """Return the API key or raise a helpful error. Call this just before
        the first real Vertex call so unconfigured envs fail loudly."""
        if not self.gcp_vertex_api_key:
            raise RuntimeError(
                "GCP_VERTEX_API_KEY is not set. Add it to .env at the repo root "
                "(copy from .env.example). Get a key from GCP Console → "
                "Vertex AI → Vertex AI Studio → API Keys."
            )
        return self.gcp_vertex_api_key


@lru_cache(maxsize=1)
def get_llm_settings() -> LLMSettings:
    return LLMSettings()
