"""Tests for the agent loop — uses MockLLMClient (no live Vertex calls)."""
from __future__ import annotations
import socket
import uuid
from urllib.parse import urlparse

import pytest

from nrc_llm import CompletionResult, MockLLMClient, ToolCallRequest
from nrc_orchestrator import Agent
from nrc_orchestrator.conversation import ChatTurn, ConversationStore
from nrc_storage import RedisClient, StorageSettings


def _pg_up() -> bool:
    u = urlparse(StorageSettings().postgres_url)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((u.hostname or "localhost", u.port or 5432))
            return True
        except OSError:
            return False


pytestmark = pytest.mark.skipif(not _pg_up(), reason="Postgres not running — agent needs live tool data")


def test_agent_runs_tool_and_synthesizes():
    """Two-step conversation: model requests tool → gets result → gives final answer."""
    script = [
        CompletionResult(
            tool_calls=[ToolCallRequest(id="c1", name="get_quote", args={"scrip": "NABIL"})],
            stop_reason="tool_use",
        ),
        CompletionResult(
            content="NABIL closed at Rs.528 today.",
            stop_reason="end_turn",
        ),
    ]
    agent = Agent(llm=MockLLMClient(script))
    result = agent.ask("What is NABIL's close?")
    assert result.stop_reason == "end_turn"
    assert "528" in result.answer
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "get_quote"
    assert result.tool_calls[0].output is not None
    assert result.tool_calls[0].error is None


def test_agent_handles_tool_error():
    """Unknown scrip → ToolError → still wraps into tool_call record."""
    script = [
        CompletionResult(
            tool_calls=[ToolCallRequest(id="c1", name="get_quote", args={"scrip": "NOTASCRIP"})],
            stop_reason="tool_use",
        ),
        CompletionResult(
            content="I couldn't find that scrip.",
            stop_reason="end_turn",
        ),
    ]
    agent = Agent(llm=MockLLMClient(script))
    result = agent.ask("Get price for NOTASCRIP")
    tc = result.tool_calls[0]
    assert tc.error is not None
    assert "not_found" in tc.error


def test_agent_unknown_tool_does_not_crash():
    script = [
        CompletionResult(
            tool_calls=[ToolCallRequest(id="c1", name="non_existent_tool", args={})],
            stop_reason="tool_use",
        ),
        CompletionResult(content="I can't do that.", stop_reason="end_turn"),
    ]
    agent = Agent(llm=MockLLMClient(script))
    result = agent.ask("do a weird thing")
    tc = result.tool_calls[0]
    assert tc.error == "Unknown tool: 'non_existent_tool'"


def test_agent_parallel_tool_calls():
    """Model requests 2 tools in one turn; agent runs both and feeds both back."""
    script = [
        CompletionResult(
            tool_calls=[
                ToolCallRequest(id="c1", name="get_quote", args={"scrip": "NABIL"}),
                ToolCallRequest(id="c2", name="get_fundamentals", args={"scrip": "NABIL"}),
            ],
            stop_reason="tool_use",
        ),
        CompletionResult(content="Here is NABIL's snapshot.", stop_reason="end_turn"),
    ]
    agent = Agent(llm=MockLLMClient(script))
    result = agent.ask("Summarize NABIL")
    assert len(result.tool_calls) == 2
    assert {tc.tool_name for tc in result.tool_calls} == {"get_quote", "get_fundamentals"}


def test_agent_respects_max_steps():
    """Infinite tool-use script is capped at max_steps."""
    looping = CompletionResult(
        tool_calls=[ToolCallRequest(id="loop", name="get_quote", args={"scrip": "NABIL"})],
        stop_reason="tool_use",
    )
    # Script longer than max_steps so the agent runs out before end_turn.
    mock = MockLLMClient([looping] * 10)
    agent = Agent(llm=mock, max_steps=3)
    result = agent.ask("loop")
    assert mock.calls_made <= 3
    assert len(result.tool_calls) == 3


def test_agent_result_to_query_trace():
    """AgentResult converts cleanly into QueryTrace for persistence."""
    script = [CompletionResult(content="fine", stop_reason="end_turn")]
    agent = Agent(llm=MockLLMClient(script))
    result = agent.ask("hi")
    trace = result.to_query_trace(user_id="u1", session_id="s1")
    assert trace.query_text == "hi"
    assert trace.user_id == "u1"
    assert trace.session_id == "s1"
    assert trace.final_response == "fine"


def test_agent_with_history_passes_prior_turns_to_llm():
    """Follow-up query gets prior turns as context so 'why so?' has meaning."""
    script = [CompletionResult(content="Because of peer-low P/E.", stop_reason="end_turn")]
    mock = MockLLMClient(script)
    agent = Agent(llm=mock)
    history = [
        ChatTurn(role="user", content="Is KBL fairly valued?"),
        ChatTurn(role="assistant", content="KBL is undervalued — P/E 8.63 vs peer median 16.60."),
    ]
    agent.ask("why so?", history=history)
    # The mock captured the message list — the prior turns must be present.
    msgs = mock.last_messages
    assert len(msgs) == 3
    assert msgs[0].content == "Is KBL fairly valued?"
    assert "undervalued" in msgs[1].content
    assert msgs[-1].content == "why so?"


def test_conversation_store_round_trip():
    """Redis conversation store appends, caps, and clears correctly."""
    if not _redis_up():
        pytest.skip("Redis not running")
    store = ConversationStore()
    sid = f"test-{uuid.uuid4().hex[:8]}"
    try:
        assert store.load(sid) == []
        store.append(sid, user="Q1?", assistant="A1.")
        store.append(sid, user="Q2?", assistant="A2.")
        hist = store.load(sid)
        assert [t.content for t in hist] == ["Q1?", "A1.", "Q2?", "A2."]
    finally:
        store.clear(sid)
        assert store.load(sid) == []


def _redis_up() -> bool:
    try:
        return RedisClient().ping()
    except Exception:
        return False
