"""Intent classifier — the cheap first-pass gate before the agent loop.

Three jobs:
  1. Reject obviously off-topic queries (weather, recipes, politics) with a
     polite canned response — saves 10-50× the tokens the synthesizer would
     have burnt on refusal reasoning.
  2. Ask for clarification when the query is ambiguous (e.g. 'how is it
     doing?' with no scrip named).
  3. Pass NEPSE research questions straight through to the full tool-use
     agent.

Runs on the INTENT tier (gemini-2.5-flash-lite) — cheap, fast. Roughly 10-20×
cheaper than the synthesizer per call."""
from __future__ import annotations
import json
import logging
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from nrc_llm import LLMClient, Message, Role

from .conversation import ChatTurn

_log = logging.getLogger("nrc_orchestrator.intent")


class IntentCategory(str, Enum):
    NEPSE_RESEARCH = "nepse_research"
    OFF_TOPIC = "off_topic"
    AMBIGUOUS = "ambiguous"


class IntentDecision(BaseModel):
    """Structured classifier output. The LLM returns JSON matching this."""
    category: IntentCategory
    reason: str = Field(
        ...,
        description="One-line justification for the category choice.",
    )
    canned_response: str | None = Field(
        default=None,
        description="For OFF_TOPIC/AMBIGUOUS: the user-facing response. Null for NEPSE_RESEARCH.",
    )


_SYSTEM = """You are the intent gate for the NEPSE Research Copilot — an internal tool \
for the investment team at a Nepali bank. Classify each user query and respond \
ONLY with a JSON object (no prose around it).

Schema:
{
  "category": "nepse_research" | "off_topic" | "ambiguous",
  "reason": "<one-line justification>",
  "canned_response": "<text shown to user>" or null
}

Rules:

- `nepse_research`: Query is about NEPSE-listed Commercial Banks (e.g. NABIL, \
SCB, EBL, KBL, SBI, HBL, NICA, etc.) — prices, fundamentals (ROE, NPL, CAR, \
EPS, dividends), technical indicators, peer screens, valuations, or news. \
Set canned_response to null — the full agent will handle it.

- `off_topic`: Query is not about NEPSE research (weather, general chat, other \
markets, non-Commercial-Bank scrips like hydropower/insurance, coding help, \
etc.). Set canned_response to a polite one-sentence refusal that redirects \
the user, e.g. "I only cover NEPSE Commercial Banks — try asking about NABIL, \
SCB, EBL, etc."

- `ambiguous`: Query is NEPSE-related but missing required specifics (e.g. \
"how is it doing?" with no scrip, or "compare them" without naming scrips). \
Set canned_response to a one-sentence clarifying question.

Output MUST be valid JSON. No markdown fences, no prose."""


class IntentClassifier:
    """Run the intent tier on a query."""

    def __init__(self, llm: LLMClient):
        self._llm = llm

    def classify(
        self,
        query: str,
        *,
        history: list[ChatTurn] | None = None,
    ) -> IntentDecision:
        """Always returns a decision; on any parsing error, defaults to
        NEPSE_RESEARCH so we err toward answering rather than refusing.

        History is passed so short follow-ups ('why so?', 'and KBL?') stay in
        the NEPSE context instead of being flagged ambiguous."""
        messages: list[Message] = []
        # Only pass the last 2 turns — enough context for classification but
        # minimal token spend. The synthesizer gets full history separately.
        tail = (history or [])[-4:]
        for t in tail:
            role = Role.USER if t.role == "user" else Role.ASSISTANT
            messages.append(Message(role=role, content=t.content))
        messages.append(Message(role=Role.USER, content=query))

        response = self._llm.complete(
            messages,
            system=_SYSTEM,
            max_output_tokens=256,
            temperature=0.0,
        )
        raw = response.content.strip()
        # Strip a fenced ```json ... ``` wrapper if the model still emits one.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        try:
            return IntentDecision.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError):
            _log.warning("intent classifier returned un-parseable output, defaulting to nepse_research: %r", raw)
            return IntentDecision(
                category=IntentCategory.NEPSE_RESEARCH,
                reason="classifier_parse_failed_fallback",
            )
