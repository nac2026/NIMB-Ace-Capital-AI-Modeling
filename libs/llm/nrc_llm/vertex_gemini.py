"""Vertex AI Gemini client using the unified google-genai SDK.

Works with Vertex API keys (project-scoped, region-agnostic). The same SDK
can target the Generative Language API (AI Studio) or Vertex AI — we select
Vertex mode explicitly so we're always billed through the customer's GCP
project.

Retries: tenacity-driven exponential backoff with jitter for transient
errors (5xx, 429, connection errors). Permanent errors (4xx auth/validation)
bubble immediately so we don't waste budget retrying a misconfigured call.

Tool-use: Gemini function-calling mapped into the provider-neutral
ToolCallRequest shape defined in nrc_llm.types."""
from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Iterator

from google import genai
from google.genai import types as gt
from google.genai import errors as genai_errors
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .config import LLMSettings, get_llm_settings
from .types import CompletionResult, Message, Role, StreamChunk, TokenUsage, ToolCallRequest

_log = logging.getLogger("nrc_llm.vertex_gemini")

# Transient errors worth retrying. genai raises ClientError (4xx) and
# ServerError (5xx / unavailable). Retry only the server side.
_RETRYABLE = (
    genai_errors.ServerError,
    ConnectionError,
    TimeoutError,
)


class VertexGeminiClient:
    """Gemini via Vertex AI, API-key authenticated.

    Safe to construct once at process start and reuse — the underlying
    httpx client in google-genai handles connection pooling."""

    def __init__(self, model: str | None = None, settings: LLMSettings | None = None):
        self._settings = settings or get_llm_settings()
        self.model = model or self._settings.llm_synthesizer_model
        # vertexai=True routes to aiplatform.googleapis.com, billed via GCP project.
        self._client = genai.Client(
            vertexai=True,
            api_key=self._settings.require_api_key(),
        )

    # --------------------------------------------------------- LLMClient API
    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> CompletionResult:
        t0 = time.perf_counter()
        contents = self._messages_to_contents(messages)
        config = self._build_config(
            system=system,
            tools=tools,
            max_output_tokens=max_output_tokens or self._settings.llm_max_output_tokens,
            temperature=temperature,
        )

        try:
            response = self._call_with_retry(contents=contents, config=config)
        except RetryError as e:
            _log.exception("gemini call exhausted retries")
            return CompletionResult(
                stop_reason="error",
                content=f"LLM call failed after retries: {e.last_attempt.exception()}",
                model=self.model,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        except genai_errors.ClientError as e:
            # 4xx — auth error, malformed request, safety block. Don't retry.
            _log.error("gemini client error (no retry): %s", e)
            return CompletionResult(
                stop_reason="error",
                content=f"LLM client error: {e}",
                model=self.model,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        return self._parse_response(response, started_at=t0)

    def complete_stream(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> Iterator[StreamChunk]:
        """Streaming variant of complete(). Yields text tokens as they arrive.

        Yields StreamChunk(text=..., done=False) for each text fragment, then
        a final StreamChunk(done=True, result=<full CompletionResult>).
        Tool calls are accumulated silently — no text is yielded for them."""
        t0 = time.perf_counter()
        contents = self._messages_to_contents(messages)
        config = self._build_config(
            system=system,
            tools=tools,
            max_output_tokens=max_output_tokens or self._settings.llm_max_output_tokens,
            temperature=temperature,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        usage = TokenUsage()

        try:
            for chunk in self._client.models.generate_content_stream(
                model=self.model, contents=contents, config=config
            ):
                candidates = getattr(chunk, "candidates", None) or []
                if candidates:
                    cand = candidates[0]
                    for part in getattr(cand.content, "parts", []) or []:
                        if getattr(part, "text", None):
                            text_parts.append(part.text)
                            yield StreamChunk(text=part.text)
                        if getattr(part, "function_call", None):
                            fc = part.function_call
                            name = fc.name.split(".", 1)[-1] if fc.name else ""
                            tool_calls.append(ToolCallRequest(
                                id=fc.id or f"call_{uuid.uuid4().hex[:12]}",
                                name=name,
                                args=_to_plain_dict(fc.args) if fc.args else {},
                            ))
                usage_meta = getattr(chunk, "usage_metadata", None)
                if usage_meta:
                    usage = TokenUsage(
                        input_tokens=getattr(usage_meta, "prompt_token_count", 0) or 0,
                        output_tokens=getattr(usage_meta, "candidates_token_count", 0) or 0,
                    )
        except Exception as e:
            _log.exception("gemini stream error")
            yield StreamChunk(
                done=True,
                result=CompletionResult(
                    stop_reason="error",
                    content=f"stream error: {e}",
                    model=self.model,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                ),
            )
            return

        stop = "tool_use" if tool_calls else "end_turn"
        yield StreamChunk(
            done=True,
            result=CompletionResult(
                content="".join(text_parts),
                tool_calls=tool_calls,
                stop_reason=stop,
                usage=usage,
                model=self.model,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            ),
        )

    async def complete_stream_async(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator["StreamChunk"]:
        """Async streaming variant — uses client.aio to avoid thread pools entirely.

        KEY: pass tools=None on synthesis calls to bypass the SDK's AFC buffering.
        AFC (Automatic Function Calling) holds back all tokens when tools are
        present so it can inspect for function_call parts — even when you handle
        tool calls manually.  Synthesis calls have tool results already in context
        and don't need the schema, so passing tools=None gives true token streaming."""
        t0 = time.perf_counter()
        contents = self._messages_to_contents(messages)
        config = self._build_config(
            system=system,
            tools=tools,
            max_output_tokens=max_output_tokens or self._settings.llm_max_output_tokens,
            temperature=temperature,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        usage = TokenUsage()

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self.model, contents=contents, config=config
            )
            async for chunk in stream:
                candidates = getattr(chunk, "candidates", None) or []
                if candidates:
                    cand = candidates[0]
                    for part in getattr(cand.content, "parts", []) or []:
                        if getattr(part, "text", None):
                            text_parts.append(part.text)
                            yield StreamChunk(text=part.text)
                        if getattr(part, "function_call", None):
                            fc = part.function_call
                            name = fc.name.split(".", 1)[-1] if fc.name else ""
                            tool_calls.append(ToolCallRequest(
                                id=fc.id or f"call_{uuid.uuid4().hex[:12]}",
                                name=name,
                                args=_to_plain_dict(fc.args) if fc.args else {},
                            ))
                usage_meta = getattr(chunk, "usage_metadata", None)
                if usage_meta:
                    usage = TokenUsage(
                        input_tokens=getattr(usage_meta, "prompt_token_count", 0) or 0,
                        output_tokens=getattr(usage_meta, "candidates_token_count", 0) or 0,
                    )
        except Exception as e:
            _log.exception("gemini async stream error")
            yield StreamChunk(
                done=True,
                result=CompletionResult(
                    stop_reason="error",
                    content=f"async stream error: {e}",
                    model=self.model,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                ),
            )
            return

        stop = "tool_use" if tool_calls else "end_turn"
        yield StreamChunk(
            done=True,
            result=CompletionResult(
                content="".join(text_parts),
                tool_calls=tool_calls,
                stop_reason=stop,
                usage=usage,
                model=self.model,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            ),
        )

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=wait_random_exponential(multiplier=0.5, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _call_with_retry(self, *, contents, config):
        return self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

    # ------------------------------------------ translate provider response
    def _parse_response(self, response, *, started_at: float) -> CompletionResult:
        """Extract text + function-call requests + token usage from a Gemini response."""
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        content_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        # Safety / RECITATION etc block — stop with the finish_reason as signal.
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return CompletionResult(
                stop_reason="safety",
                content="",
                model=self.model,
                latency_ms=latency_ms,
            )

        cand = candidates[0]
        for part in getattr(cand.content, "parts", []) or []:
            if getattr(part, "text", None):
                content_parts.append(part.text)
            if getattr(part, "function_call", None):
                fc = part.function_call
                # Gemini namespaces tools as 'default_api.<name>'; strip that.
                name = fc.name.split(".", 1)[-1] if fc.name else ""
                tool_calls.append(ToolCallRequest(
                    id=fc.id or f"call_{uuid.uuid4().hex[:12]}",
                    name=name,
                    args=_to_plain_dict(fc.args) if fc.args else {},
                ))

        finish = getattr(cand, "finish_reason", None)
        finish_str = getattr(finish, "name", str(finish)) if finish is not None else ""
        if tool_calls:
            stop = "tool_use"
        elif finish_str in {"MAX_TOKENS", "LENGTH"}:
            stop = "max_tokens"
        elif finish_str in {"SAFETY", "RECITATION", "BLOCKED"}:
            stop = "safety"
        else:
            stop = "end_turn"

        usage_meta = getattr(response, "usage_metadata", None)
        usage = TokenUsage(
            input_tokens=getattr(usage_meta, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage_meta, "candidates_token_count", 0) or 0,
        )
        return CompletionResult(
            content="".join(content_parts),
            tool_calls=tool_calls,
            stop_reason=stop,
            usage=usage,
            model=self.model,
            latency_ms=latency_ms,
        )

    # ------------------------------------------ build Gemini `contents` list
    def _messages_to_contents(self, messages: list[Message]) -> list[gt.Content]:
        """Map neutral Message[] → Gemini Content[].

        Gemini uses 'user' / 'model' roles (no 'system' in contents — we pass
        system as `system_instruction` in the config). Tool results map to
        function_response parts under role='user'.

        Critical: Gemini requires that when the model issues N function calls
        in one turn, the following user turn must carry exactly N function
        response parts — one per call. We coalesce consecutive Role.TOOL
        messages into a single Content so the count matches."""
        out: list[gt.Content] = []
        pending_tool_parts: list[gt.Part] = []

        def flush_tool_parts() -> None:
            if pending_tool_parts:
                out.append(gt.Content(role="user", parts=list(pending_tool_parts)))
                pending_tool_parts.clear()

        for m in messages:
            if m.role == Role.SYSTEM:
                continue  # passed via config.system_instruction
            if m.role == Role.TOOL:
                pending_tool_parts.append(gt.Part.from_function_response(
                    name=m.tool_name or "",
                    response=m.tool_result or {},
                ))
                continue
            flush_tool_parts()  # tool batch ends when a non-tool message arrives
            parts: list[gt.Part] = []
            if m.content:
                parts.append(gt.Part.from_text(text=m.content))
            for tc in m.tool_calls:
                parts.append(gt.Part.from_function_call(name=tc.name, args=tc.args))
            if not parts:
                continue
            gemini_role = "model" if m.role == Role.ASSISTANT else "user"
            out.append(gt.Content(role=gemini_role, parts=parts))

        flush_tool_parts()
        return out

    def _build_config(
        self,
        *,
        system: str | None,
        tools: list[dict] | None,
        max_output_tokens: int,
        temperature: float,
    ) -> gt.GenerateContentConfig:
        tool_decls: list[gt.Tool] | None = None
        if tools:
            # Each tool dict has {name, description, input_schema}. Gemini wants
            # a FunctionDeclaration with `parameters` = JSON schema (minus $defs
            # that Gemini doesn't support; we sanitize).
            decls = [
                gt.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=_sanitize_schema_for_gemini(t["input_schema"]),
                )
                for t in tools
            ]
            tool_decls = [gt.Tool(function_declarations=decls)]

        # Disable internal "thinking" on Gemini 2.5 models. We're doing factual
        # tool-grounded Q&A — thinking adds 5-15s for marginal quality gain on
        # this workload. Biggest single latency win available.
        thinking_config = None
        if self.model.startswith(("gemini-2.5", "gemini-3")):
            thinking_config = gt.ThinkingConfig(thinking_budget=0, include_thoughts=False)

        return gt.GenerateContentConfig(
            system_instruction=system,
            tools=tool_decls,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            thinking_config=thinking_config,
        )


# ------------------------------------------------------------------ helpers
def _to_plain_dict(args: Any) -> dict[str, Any]:
    """Gemini may return args as a proto map; normalize to plain dict."""
    if isinstance(args, dict):
        return args
    try:
        return dict(args)
    except Exception:
        return json.loads(json.dumps(args, default=str))


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    """Strip JSON-schema fields Gemini rejects ($defs, $ref, additionalProperties).

    Pydantic emits nested $defs blocks that Gemini's function-calling parser
    trips on. For the shallow tool-input schemas we produce, inlining / dropping
    these is safe — our inputs are flat (scrip, fiscal_year_bs, ...)."""
    if not isinstance(schema, dict):
        return schema
    cleaned = {k: v for k, v in schema.items() if k not in {"$defs", "$ref", "additionalProperties", "definitions"}}
    if "properties" in cleaned:
        cleaned["properties"] = {
            k: _sanitize_schema_for_gemini(v) for k, v in cleaned["properties"].items()
        }
    # anyOf often encodes Optional[X] — collapse to the non-null branch.
    if "anyOf" in cleaned:
        non_null = [b for b in cleaned["anyOf"] if b.get("type") != "null"]
        if len(non_null) == 1:
            collapsed = _sanitize_schema_for_gemini(non_null[0])
            cleaned.pop("anyOf")
            cleaned.update(collapsed)
    return cleaned
