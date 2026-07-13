"""Terminal CLI for the research agent — `nrc-ask "question"`.

Good for local demos + pipeline shakedown without standing up FastAPI.
Writes the trace to Postgres same as the HTTP path."""
from __future__ import annotations
import sys

import typer

from nrc_llm import get_router

from .agent import Agent
from .conversation import ConversationStore
from .trace_writer import write_trace

app = typer.Typer(add_completion=False, help="Ask the NEPSE Research Copilot a question from the terminal.")


@app.command()
def ask(
    query: str = typer.Argument(..., help="Question to ask, e.g. 'How is NABIL doing this quarter?'"),
    show_tools: bool = typer.Option(True, "--show-tools/--no-show-tools", help="Print the tool-use audit trail."),
    session_id: str | None = typer.Option(None, "--session-id", help="Session id for trace correlation."),
) -> None:
    router = get_router()
    convo = ConversationStore() if session_id else None
    history = convo.load(session_id) if convo and session_id else []

    agent = Agent(llm=router.synthesizer(), intent_llm=router.intent())
    result = agent.ask(query, history=history)

    if convo and session_id:
        convo.append(session_id, user=query, assistant=result.answer)

    trace = result.to_query_trace(session_id=session_id)
    write_trace(trace)

    if show_tools:
        intent = f"intent={result.intent_category}"
        typer.echo(f"[trace={result.trace_id[:8]}]  {intent}  {len(result.tool_calls)} tool call(s)  {result.total_latency_ms}ms")
        for tc in result.tool_calls:
            status = f"err={tc.error}" if tc.error else f"ok ({tc.latency_ms}ms)"
            typer.echo(f"  → {tc.tool_name}({tc.input}) — {status}")
        typer.echo("")

    typer.echo(result.answer)
    sys.exit(0 if result.stop_reason == "end_turn" else 1)


if __name__ == "__main__":
    app()
