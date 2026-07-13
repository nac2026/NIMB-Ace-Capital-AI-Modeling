"""Unit tests for the LLM layer — no live Vertex calls."""
from __future__ import annotations
import pytest

from nrc_llm import (
    CompletionResult,
    LLMClient,
    LLMSettings,
    Message,
    MockLLMClient,
    Role,
    ToolCallRequest,
)
from nrc_llm.vertex_gemini import _sanitize_schema_for_gemini


# ------------------------------------------------------------------ settings
def test_settings_require_api_key_raises_when_missing():
    s = LLMSettings(gcp_vertex_api_key="")
    with pytest.raises(RuntimeError, match="GCP_VERTEX_API_KEY"):
        s.require_api_key()


def test_settings_require_api_key_returns_when_set():
    s = LLMSettings(gcp_vertex_api_key="fake-key-for-test")
    assert s.require_api_key() == "fake-key-for-test"


def test_settings_defaults():
    s = LLMSettings()
    assert s.llm_intent_model == "gemini-2.5-flash-lite"
    assert s.llm_synthesizer_model == "gemini-2.5-flash"
    assert s.llm_retries == 3
    assert s.gcp_region == "global"


# --------------------------------------------------------- mock client
def test_mock_client_satisfies_protocol():
    m = MockLLMClient([CompletionResult(content="hello", stop_reason="end_turn")])
    assert isinstance(m, LLMClient)


def test_mock_client_returns_scripted_responses():
    m = MockLLMClient([
        CompletionResult(content="first", stop_reason="end_turn"),
        CompletionResult(content="second", stop_reason="end_turn"),
    ])
    assert m.complete([Message(role=Role.USER, content="q1")]).content == "first"
    assert m.complete([Message(role=Role.USER, content="q2")]).content == "second"
    assert m.calls_made == 2


def test_mock_client_exhausted_raises():
    m = MockLLMClient([CompletionResult(content="only", stop_reason="end_turn")])
    m.complete([])
    with pytest.raises(RuntimeError, match="exhausted"):
        m.complete([])


def test_mock_client_requires_non_empty_script():
    with pytest.raises(ValueError):
        MockLLMClient([])


# ------------------------------------------------- gemini schema sanitizer
def test_sanitize_strips_defs_and_ref():
    raw = {
        "type": "object",
        "$defs": {"X": {"type": "string"}},
        "properties": {"a": {"$ref": "#/$defs/X"}},
        "additionalProperties": False,
    }
    clean = _sanitize_schema_for_gemini(raw)
    assert "$defs" not in clean
    assert "additionalProperties" not in clean


def test_sanitize_collapses_optional_anyof():
    """Pydantic emits `anyOf: [{type: string}, {type: null}]` for Optional[str].
    Gemini rejects unions — collapse to the non-null branch."""
    raw = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    clean = _sanitize_schema_for_gemini(raw)
    assert clean == {"type": "string"}


def test_sanitize_recurses_into_properties():
    raw = {
        "type": "object",
        "properties": {
            "nested": {"type": "object", "$defs": {"X": {"type": "string"}}},
        },
    }
    clean = _sanitize_schema_for_gemini(raw)
    assert "$defs" not in clean["properties"]["nested"]


def test_sanitize_keeps_all_tool_specs_valid():
    from nrc_tools import tool_specs
    for spec in tool_specs():
        clean = _sanitize_schema_for_gemini(spec["input_schema"])
        assert isinstance(clean, dict)
        assert "properties" in clean or clean.get("type") == "object"


# ---------------------------------------------------------- types round-trip
def test_completion_result_roundtrip():
    r = CompletionResult(
        content="NABIL closed at 528.",
        tool_calls=[ToolCallRequest(id="c1", name="get_quote", args={"scrip": "NABIL"})],
        stop_reason="tool_use",
    )
    dumped = r.model_dump_json()
    restored = CompletionResult.model_validate_json(dumped)
    assert restored == r
