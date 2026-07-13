"""NEPSE Research Copilot — Streamlit demo UI.

Run with:
    uv run streamlit run services/ui/nrc_ui/app.py

Expects the orchestrator to be running on NRC_BACKEND_URL
(default http://localhost:8080). Works against any environment — local dev,
staging, or the Cloud Run URL — by setting that one env var."""
from __future__ import annotations
import os
import uuid

import httpx
import streamlit as st

BACKEND_URL = os.getenv("NRC_BACKEND_URL", "http://localhost:8080")
REQUEST_TIMEOUT = float(os.getenv("NRC_REQUEST_TIMEOUT", "120"))


# ---------------------------------------------------------------- helpers
def render_meta(meta: dict) -> None:
    """Show the tool audit + tokens collapsed under an assistant message."""
    with st.expander(
        f"📊 trace {meta['trace_id'][:8]}  ·  {meta['model_used']}  ·  "
        f"{meta['total_latency_ms']} ms  ·  "
        f"{meta['input_tokens']} in / {meta['output_tokens']} out tokens  ·  "
        f"intent={meta['intent_category']}",
        expanded=False,
    ):
        if not meta["tool_calls"]:
            st.write("_No tools called._")
        for i, tc in enumerate(meta["tool_calls"], 1):
            status = "❌" if tc["error"] else "✅"
            st.write(f"{status} **{i}. `{tc['tool']}`**  ({tc['latency_ms']} ms)")
            st.json(tc["input"], expanded=False)
            if tc["error"]:
                st.error(tc["error"])


# ---------------------------------------------------------------- page setup
st.set_page_config(
    page_title="NEPSE Research Copilot",
    page_icon=":bank:",
    layout="wide",
)
st.title("NEPSE Research Copilot")
st.caption(
    "Internal research tool for the investment team. Ask about Commercial Banks "
    "on NEPSE — quotes, fundamentals, technicals, peer rankings, screens, news. "
    "Every answer is grounded in the underlying database with a full audit trail."
)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.subheader("Session")
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"ui-{uuid.uuid4().hex[:8]}"
    st.code(st.session_state.session_id, language="text")

    st.subheader("Connected backend")
    st.code(BACKEND_URL, language="text")
    try:
        r = httpx.get(f"{BACKEND_URL}/ready", timeout=3)
        if r.status_code == 200 and r.json().get("status") == "ok":
            st.success("backend healthy ✓")
        else:
            st.warning(f"backend degraded: {r.text[:120]}")
    except httpx.HTTPError as e:
        st.error(f"backend unreachable: {e}")

    st.divider()
    st.subheader("Try these")
    examples = [
        "What's the latest close of NABIL?",
        "Which bank has the highest ROE this quarter?",
        "Is KBL fairly valued compared to peers?",
        "Show me all flagged banks with CD_HIGH or NPL_HIGH.",
        "Compare NABIL and SCB on CAR and NPL.",
        "What's the latest news about interest rates?",
        "List all active commercial banks by paid-up capital.",
    ]
    for q in examples:
        if st.button(q, use_container_width=True, key=f"ex_{hash(q)}"):
            st.session_state._pending_query = q

    st.divider()
    if st.button("🗑 Clear conversation", use_container_width=True):
        st.session_state.history = []
        st.rerun()


# ---------------------------------------------------------------- chat history
if "history" not in st.session_state:
    st.session_state.history = []  # list[{role, content, meta?}]

for turn in st.session_state.history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("meta"):
            render_meta(turn["meta"])


# ---------------------------------------------------------------- input box
query = st.chat_input("Ask about NEPSE commercial banks…")
if "_pending_query" in st.session_state:
    query = st.session_state._pending_query
    del st.session_state._pending_query

if query:
    st.session_state.history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                r = httpx.post(
                    f"{BACKEND_URL}/chat",
                    json={"query": query, "session_id": st.session_state.session_id},
                    timeout=REQUEST_TIMEOUT,
                )
                r.raise_for_status()
                payload = r.json()
            except httpx.HTTPError as e:
                st.error(f"Request failed: {e}")
                st.stop()

        st.markdown(payload["answer"])
        render_meta(payload)
        st.session_state.history.append({
            "role": "assistant",
            "content": payload["answer"],
            "meta": payload,
        })
