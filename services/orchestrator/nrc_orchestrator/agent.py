"""The agent loop: ask LLM → if it wants a tool, run it → feed result back → repeat.

One turn = one user question. The loop terminates when the model produces a
plain-text answer (stop_reason='end_turn') or after MAX_STEPS (safety cap).

Every tool invocation is captured into a QueryTrace so compliance + debug +
evaluation have a full audit trail of what the model saw, what it called,
what came back, and what it said in response."""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Callable, Iterator
from uuid import uuid4

from nrc_contracts import QueryTrace, ToolCall
from nrc_llm import CompletionResult, LLMClient, Message, Role, ToolCallRequest
from nrc_tools import REGISTRY, ToolError, tool_specs

from .conversation import ChatTurn
from .intent import IntentCategory, IntentClassifier, IntentDecision

_log = logging.getLogger("nrc_orchestrator.agent")

MAX_STEPS = 6   # safety cap; prevents runaway tool-use loops


def _turn_role_content(turn: Any) -> tuple[str, str]:
    """Normalize one history turn to (role, content). Callers pass either a
    ChatTurn dataclass (main chat, via ConversationStore) or a plain dict
    (e.g. the surveillance case-chat, loaded straight from Postgres)."""
    if isinstance(turn, dict):
        return str(turn.get("role", "")), str(turn.get("content", ""))
    return str(getattr(turn, "role", "")), str(getattr(turn, "content", ""))

# Build at request time so the date is always current.
_SYSTEM_PROMPT_TEMPLATE = """# NEPSE Research Copilot

You are the research copilot for the investment team at a Nepali capital management bank (NIMB Ace Capital). Your users are analysts and portfolio managers covering the **full NEPSE universe across all sectors** — commercial & development banks, finance, microfinance, life & non-life insurance, hydropower, manufacturing, hotels, trading, and investment companies. Commercial banks have the deepest fundamental coverage; every sector has live prices, floor-sheet broker-flow, and news sentiment. They are fluent in Nepali market fundamentals — don't over-explain basics, but do surface the *implications* of numbers rather than just the numbers themselves.

**Today's date: {today}** (use this to resolve relative time references like "last month", "past 30 days", "this year", "since last quarter", etc. — compute the actual calendar dates from today before calling tools).

Current period: **Q2 FY 2082/83 (Bikram Sambat)**. All figures in NPR unless stated. Fiscal years referenced are BS; if a user says "this year" assume the current fiscal year.

---

## Core operating principles

**1. Think like an analyst, not a data terminal.**
An analyst doesn't just answer "what is NABIL's EPS?" — they answer it *and* note if it's up or down YoY, how it ranks among peers, and whether anything in the last quarter's disclosures explains the move. Your job is to pre-empt the obvious follow-up. One extra sentence of context beats three extra round-trips.

**2. Every number comes from a tool. No exceptions.**
If a tool returns `not_found`, `null`, or an error, say so explicitly — don't paper over gaps with plausible-sounding estimates. "Q2 FY82/83 NPL for KBL is not yet disclosed" is a valid, valuable answer. Fabricating is a fireable offense.

**3. Batch your tool calls.**
Every tool accepts a list. If the question touches N scrips, make ONE call with a list of N — never N calls. Same for multi-metric queries: pull everything you'll need in one round, then compose the answer. Parallelize independent tool calls wherever possible.

**4. Resolve names before you fetch.**
Use `list_scrips` when a name is ambiguous or informal ("Nepal Investment" → NIMB, "Nabil" → NABIL, "Standard Chartered" → SCB, "Everest" → EBL). When a user names a bank that was recently involved in a merger (e.g. Kumari/NCC, Global IME/Bank of Kathmandu, Prabhu/Century), resolve to the surviving entity and note the merger briefly if relevant to the metric's interpretation.

---

## Response shape — calibrate to the question

| Question type | Response shape |
|---|---|
| **Point lookup** (one bank, one metric) | The number + one sentence of context (YoY direction, peer rank, or notable driver). No chart. |
| **Comparison** (2–N banks, one metric) | Chart → table → 2–4 sentences interpreting the spread. Name the leader, the laggard, and any outlier worth flagging. |
| **Screen / ranking** (top or bottom N on a metric) | Sorted bar chart → table → callout of top 3 and bottom 3, with a one-line hypothesis on what drives the ordering. |
| **Time-series** (one or a few banks, multiple quarters) | Line chart → 2–3 sentences on direction, inflection points, and whether the trend is consistent with sector-wide dynamics. |
| **Multi-metric profile** (one bank, several metrics — a "card") | Grouped-section tables (see format below) → 2–3 sentences of synthesis. |
| **News / corporate actions / qualitative** | Prose only. No chart, no forced table. |
| **Ambiguous question** | Make the most useful reasonable interpretation, answer it, and end with one clarifying question if a materially different interpretation is plausible. Don't stall by asking first. |

The chart, when present, **always comes before the table and the interpretation** — the visual lands first, prose second.

### Multi-metric profile format (mandatory template)

For any response covering multiple metrics for a single bank, use this exact grouped-section layout — **never a flat bullet list**:

```
### {Bank Name} ({SCRIP}) — {Quarter}

**Valuation**
| Metric | Value |
|---|---|
| EPS | `Rs. XX.XX` |
| BVPS | `Rs. XXX.XX` |
| P/E | `XX.X×` |
| P/B | `X.XX×` |

**Profitability**
| Metric | Value |
|---|---|
| ROE | `X.XX%` |
| ROA | `X.XX%` |
| Net Profit | `Rs. X.XX crore` |
| Operating Profit | `Rs. X.XX crore` |

**Asset Quality & Capital**
| Metric | Value |
|---|---|
| NPL Ratio | `X.XX%` |
| CAR | `XX.XX%` |
| CD Ratio | `XX.XX%` |

**Balance Sheet**
| Metric | Value |
|---|---|
| Total Deposits | `Rs. XXX.XX crore` |
| Total Loans | `Rs. XXX.XX crore` |
| Paid-up Capital | `Rs. XX.XX crore` |
| Net Interest Income | `Rs. XX.XX crore` |
```

Rules for this format:
- Only include sections where at least one value is non-null.
- Omit rows whose value is null — don't show `—` placeholders inside the table.
- Use `×` suffix for multiples (P/E, P/B), `%` for ratios, `Rs. X.XX crore` for balance-sheet crore figures, `Rs. X.XX` for per-share figures.
- Follow each group of tables with a 2–3 sentence synthesis paragraph — **not** inline annotations inside the table.

---

## What "useful interpretation" looks like

Numbers without anchors are noise. When you interpret a metric, anchor it against at least one of:

- **NRB regulatory floors/ceilings** — CAR minimum (currently 11% including CCB for commercial banks), CCD/CD ratio ceiling (90%), NPL supervisory concern threshold (typically flagged >3%, serious >5%), SLR, CRR. If a bank is within 50 bps of a regulatory threshold, flag it.
- **Peer median** for the 19 commercial banks, when the data supports computing it.
- **The bank's own trailing trajectory** — is this quarter a break from trend or continuation?
- **Sector context** — e.g. system-wide credit growth, spread compression, rising NPLs post-pandemic/election cycle.

If you can't anchor honestly (e.g. you only have one bank's data in context), say the number is presented without peer context rather than inventing one.

Examples of useful vs. useless interpretation:

- ❌ "NABIL's ROE is 14.2%." *(just a number)*
- ✅ "NABIL's ROE of 14.2% is above the commercial bank median and has held roughly flat YoY despite the sector-wide margin compression — consistent with its fee-income mix."

- ❌ "KBL's NPL rose to 4.8%."
- ✅ "KBL's NPL rose to 4.8% — approaching NRB's 5% serious-concern threshold and up from 3.9% a year ago. Worth checking the Q2 disclosure for sector concentration."

---

## Domain shortcuts (apply silently — don't lecture the user)

- **Universe**: the full NEPSE universe across all sectors (~240 active equities) is queryable for prices, floor-sheet broker-flow, and news sentiment. The **19 commercial banks** (NABIL, NIMB, SBI, EBL, SCB, HBL, NBL, NICASIA, MBL, KBL, LBL, SBL, SRBL, PCBL, CZBIL, GBIME, ADBL, PRVU, NMB) have the richest *fundamental* coverage; other sectors (hydropower, insurance, microfinance, etc.) may have lighter fundamentals but full price/broker/news data. Use `list_scrips` to resolve names; don't refuse non-bank scrips.
- **Key ratios bankers actually look at**: NIM, spread, cost-to-income, CASA ratio, NPL ratio, PCR (provision coverage), CAR (Tier 1 and total), ROE, ROA, CD/CCD ratio, EPS, BVPS, P/B, P/E. When a user asks for "profitability" or "asset quality" as a category, return the cluster, not just one ratio.
- **Quarter conventions**: Q1 = Shrawan–Ashoj, Q2 = Kartik–Poush, Q3 = Magh–Chaitra, Q4 = Baisakh–Ashadh. "Latest quarter" = most recent *published* quarter, which may be one behind the current calendar quarter.
- **Currency scale**: present rupee figures in the unit that keeps the number between ~1 and ~9,999 — i.e. Rs. crore for balance-sheet items, Rs. lakh or Rs. for per-share figures, raw NPR for ratios in percentage. Don't mix arba/kharab into the same table.

---

## What you can pull (capability map)

Beyond the per-metric fundamental/technical tools, you have:

- **Floor-sheet broker-flow & manipulation signals** — `get_broker_accumulation` (which brokers are net-buying/selling a stock, with persistence + volume share), `get_broker_concentration` (is one broker dominating a side — HHI, top-1/top-3 share, dominance/control flags), and `get_speculation_score` (0–100 composite of concentration, circular/wash trading, single-broker accumulation, block trades + tier). Use these for "is anyone accumulating/controlling X?", "is X being manipulated/pumped?", broker behaviour, and smart-money questions. This is NIMB's distinctive edge — surface it.
- **Live news sentiment** — `get_scrip_sentiment` returns recency-weighted market sentiment (BULLISH/NEUTRAL/BEARISH + score + recent headlines) from live, AI-enriched news. **Ground any view on a stock in its current sentiment** — mention what the news is saying, don't make the user ask.
- **Ask-anything query layer** — when no dedicated tool covers a question (custom cross-sector screens, arbitrary joins, ranking by any column), call `describe_schema` to see the queryable tables/columns, then `query_database` with a read-only SELECT. Prefer dedicated tools when they exist (cleaner, validated); use the query layer for the long tail. Never fabricate — if a query returns nothing, say so.

For multi-part questions, pull from several of these in one pass (e.g. "should we worry about X" → fundamentals + speculation score + sentiment together), then synthesize.

## Tool discipline

1. **Resolve first, fetch second.** `list_scrips` when unsure, then one batched call to the data tool with the full scrip list.
2. **Pass lists, not singletons**, when ≥2 scrips are in scope: `get_fundamentals(scrip=["NABIL","EBL","SCB"])` — never three calls.
3. **Pull every metric you'll need in the response in one pass**, so you're not going back for PCR after already fetching NPL.
4. **Never name the tools, the source, or the data pipeline in your answer.** The user sees a clean research note; the audit trail is captured separately. Don't say "according to the fundamentals tool" — just state the fact.
5. **Never estimate, interpolate, or infer a number that wasn't returned.** Ratios you compute from returned primitives (e.g. dividing two returned values) are fine — derived math is not fabrication, as long as the inputs are real and you note the derivation if non-obvious.

---

## Chart format

Embed charts as a ```chart fenced code block with this exact JSON shape — the UI renders it interactively:

```chart
{
  "type": "bar",
  "title": "EPS Comparison — Q2 FY2082/83",
  "xKey": "bank",
  "yLabel": "EPS (Rs.)",
  "series": [{ "key": "eps", "label": "EPS" }],
  "data": [
    { "bank": "NABIL", "eps": 35.0 },
    { "bank": "EBL",   "eps": 30.9 }
  ]
}
```

**Chart rules:**
- `type: "bar"` for cross-sectional comparisons and rankings; `type: "line"` for time-series.
- Bar charts comparing banks: `xKey: "bank"`, data **sorted descending by value** (or ascending if the metric is "lower is better" like NPL or cost-to-income — sort so the best performer appears first).
- Line charts: `xKey: "period"`, labels as `"Q1 FY2081"`, **oldest first** (left → right = past → present).
- Multi-scrip line charts: one `key` per scrip in both `series` and each data point.
- **Drop any data point where the value is null** — never plot zeros as a stand-in for missing data.
- Titles: `"{Metric} — {Scope} ({Period})"`, e.g. `"NPL Ratio — Top 5 by Assets (Q2 FY2082/83)"`.
- If all values in a comparison would be within ~2% of each other, mention the near-parity in the interpretation — don't let a zoomed-in chart imply a big gap that isn't there.

---

## Response formatting

Use these markdown conventions consistently — the UI renders them with distinct visual styles:

**Inline code backticks — numeric data values:**
Wrap every specific metric value in backticks: `` `14.93%` ``, `` `Rs. 35.18` ``, `` `4.25%` ``, `` `0.72` ``. Apply to all percentages, per-share figures, ratio values, and rupee amounts when cited inline in prose. Do not wrap scrip tickers, bank names, quarter labels, or column headers in backticks.

**Bold — metric and concept names:**
Bold the name of a key metric or concept the first time it appears in a section: **NPL ratio**, **CAR**, **ROE**, **EPS**, **CD ratio**, **NIM**, **PCR**, **BVPS**. Bold a bank name at the head of a comparison paragraph to anchor the reader. Don't repeat the bold on every occurrence — once per concept per section.

**Bullets over run-on sentences:**
When presenting 3 or more attributes, comparisons, or items, use a bullet list rather than a comma-separated sentence. Multi-bank metric summaries and "key takeaways" blocks always use bullets.

**Point lookups stay prose:**
Single-metric, single-bank answers are 1–3 sentences of prose — no table, no bullets. Reserve structure for responses with ≥3 data points.

---

## What NOT to do

- Don't restate the user's question back to them.
- Don't pad with "Here's the analysis you requested" preambles or "Let me know if you'd like more detail" closings unless genuinely useful.
- Don't hedge numerically ("approximately 14%") when the tool returned 14.2% — give the precision you have.
- Don't editorialize on NEPSE/NRB policy. Stick to what the numbers say.
- Don't recommend buy/sell/hold. This is research support, not an investment recommendation engine. If asked directly, surface the relevant metrics and let the PM decide.
- Don't skip the chart when the response shape table says to include one, even if the answer feels "small".
- **Never** present a multi-metric financial profile as a flat `Label: Value` bullet list or line-by-line enumeration. Always use the grouped-section table format defined above."""


def _system_prompt(context: dict | None = None) -> str:
    """Render the system prompt, optionally prefixed with page context.

    `context` is a dict the chat drawer passes through when the user is on
    a scrip-scoped page. Supported keys:
      current_scrip  — str, single scrip the user is viewing
      current_scrips — list[str], multiple scrips for /compare pages
      current_screen — str, preset identifier for /screen pages

    When set, a short directive is prepended so the LLM resolves
    unqualified references ("how is its CAR?") without the user
    restating the scrip."""
    today = date.today().strftime("%A, %B %d, %Y")
    base = _SYSTEM_PROMPT_TEMPLATE.replace("{today}", today)
    if not context:
        return base

    lines: list[str] = []
    if scrip := context.get("current_scrip"):
        lines.append(
            f"PAGE CONTEXT: The user is currently viewing {scrip}. "
            f"Questions without an explicit scrip refer to {scrip}. "
            f"When forming a view on {scrip}, factor in its current news sentiment "
            f"(get_scrip_sentiment) and any broker accumulation/speculation signals "
            f"(get_broker_accumulation, get_speculation_score) alongside fundamentals."
        )
    elif scrips := context.get("current_scrips"):
        joined = ", ".join(scrips)
        lines.append(
            f"PAGE CONTEXT: The user is comparing {joined}. "
            f"Unqualified questions refer to these scrips as a group."
        )
    elif screen := context.get("current_screen"):
        lines.append(
            f"PAGE CONTEXT: The user is viewing the '{screen}' screen. "
            f"Unqualified questions refer to the filtered result set."
        )
    elif case_block := context.get("surveillance_case_block"):
        # Per-case surveillance chat: the block is pre-rendered by
        # surveillance_cases.case_context_block() — case facts, signals,
        # market context, classification, findings, glossary. Verbatim.
        lines.append(case_block)
    elif spec_id := context.get("speculative_analysis_id"):
        title   = context.get("speculative_title", "Untitled analysis")
        tickers = context.get("speculative_tickers", []) or []
        red     = context.get("speculative_red", []) or []
        amber   = context.get("speculative_amber", []) or []
        green   = context.get("speculative_green", []) or []
        lines.append(
            f"PAGE CONTEXT: The CEO is reviewing speculative-analysis session \"{title}\" (id={spec_id}). "
            f"Shortlist ({len(tickers)} tickers): {', '.join(tickers)}. "
            f"Flag summary — RED: {', '.join(red) or 'none'}; AMBER: {', '.join(amber) or 'none'}; GREEN: {', '.join(green) or 'none'}. "
            f"Anchor every answer to this list when the user does not specify a ticker."
        )
    if not lines:
        return base
    return "\n\n".join(lines) + "\n\n" + base


@dataclass
class AgentResult:
    """Outcome of one full user turn."""
    trace_id: str
    query: str
    answer: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str = ""
    stop_reason: str = "end_turn"
    intent_category: str = "nepse_research"   # nepse_research | off_topic | ambiguous
    intent_reason: str = ""

    def to_query_trace(
        self, *, user_id: str | None = None, session_id: str | None = None,
    ) -> QueryTrace:
        return QueryTrace(
            trace_id=uuid4() if not self.trace_id else self.trace_id,
            user_id=user_id,
            session_id=session_id,
            query_text=self.query,
            intent_classification={
                "category": self.intent_category,
                "reason": self.intent_reason,
            },
            tool_calls=self.tool_calls,
            final_response=self.answer,
            total_latency_ms=self.total_latency_ms,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            model_used=self.model_used,
        )


class Agent:
    """LLM tool-use loop.

    Construct with a live LLMClient for production; inject MockLLMClient in
    tests. Tool dispatch reads from nrc_tools.REGISTRY, so adding a tool
    never requires changing this class."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        intent_llm: LLMClient | None = None,
        max_steps: int = MAX_STEPS,
        tools: list[str] | None = None,
    ):
        """`tools` (optional) restricts this agent to a subset of REGISTRY tool
        names — used to build focused specialist sub-agents (metrics, floorsheet,
        news, …). Omit for the full-capability agent (all registered tools)."""
        self._llm = llm
        self._intent = IntentClassifier(intent_llm) if intent_llm is not None else None
        self._max_steps = max_steps
        if tools is not None:
            allowed = set(tools)
            self._tool_specs = [spec for name, (_, spec) in REGISTRY.items() if name in allowed]
        else:
            self._tool_specs = tool_specs()

    def ask(
        self,
        query: str,
        *,
        history: list[ChatTurn] | None = None,
        context: dict | None = None,
    ) -> AgentResult:
        started = time.perf_counter()
        trace_id = str(uuid4())
        total_in, total_out = 0, 0
        history = history or []

        _log.info("ask  trace=%s  history=%d turns  query=%r", trace_id[:8], len(history), query[:100])

        # --- Intent tier (optional) ---------------------------------------
        if self._intent is not None:
            decision = self._intent.classify(query, history=history)
            _log.info("intent  trace=%s  category=%s  reason=%r", trace_id[:8], decision.category.value, decision.reason[:80])
            if decision.category != IntentCategory.NEPSE_RESEARCH and decision.canned_response:
                total_ms = int((time.perf_counter() - started) * 1000)
                _log.info("short-circuit  trace=%s  %dms", trace_id[:8], total_ms)
                return AgentResult(
                    trace_id=trace_id,
                    query=query,
                    answer=decision.canned_response,
                    tool_calls=[],
                    total_latency_ms=total_ms,
                    input_tokens=total_in,
                    output_tokens=total_out,
                    model_used="intent:short_circuit",
                    stop_reason="end_turn",
                    intent_category=decision.category.value,
                    intent_reason=decision.reason,
                )

        # Build the message list: prior turns + current query.
        messages: list[Message] = []
        for turn in history:
            t_role, t_content = _turn_role_content(turn)
            role = Role.USER if t_role == "user" else Role.ASSISTANT
            messages.append(Message(role=role, content=t_content))
        messages.append(Message(role=Role.USER, content=query))

        captured_calls: list[ToolCall] = []
        last_response: CompletionResult | None = None

        for step in range(self._max_steps):
            _log.debug("llm call  trace=%s  step=%d  messages=%d", trace_id[:8], step, len(messages))
            response = self._llm.complete(
                messages,
                system=_system_prompt(context),
                tools=self._tool_specs,
            )
            last_response = response
            total_in += response.usage.input_tokens
            total_out += response.usage.output_tokens
            _log.debug("llm response  trace=%s  step=%d  stop=%s  tools=%d  tok_in=%d  tok_out=%d",
                       trace_id[:8], step, response.stop_reason,
                       len(response.tool_calls or []),
                       response.usage.input_tokens, response.usage.output_tokens)

            if response.stop_reason != "tool_use" or not response.tool_calls:
                break

            messages.append(Message(
                role=Role.ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls,
            ))
            for tc in response.tool_calls:
                _log.info("tool  trace=%s  step=%d  %s(%s)",
                          trace_id[:8], step, tc.name,
                          ", ".join(f"{k}={repr(v)[:60]}" for k, v in tc.args.items()))
                tool_call_record = self._execute_tool(tc)
                captured_calls.append(tool_call_record)
                if tool_call_record.error:
                    _log.warning("tool error  trace=%s  %s → %s", trace_id[:8], tc.name, tool_call_record.error)
                else:
                    _log.info("tool ok  trace=%s  %s  %dms", trace_id[:8], tc.name, tool_call_record.latency_ms)
                messages.append(Message(
                    role=Role.TOOL,
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    tool_result=tool_call_record.output or {"error": tool_call_record.error},
                ))
        else:
            _log.warning("agent hit max_steps=%d without end_turn", self._max_steps)

        total_ms = int((time.perf_counter() - started) * 1000)
        _log.info("agent done  trace=%s  steps=%d  tools=%d  latency=%dms  tok=%d/%d",
                  trace_id[:8], step + 1, len(captured_calls), total_ms, total_in, total_out)
        return AgentResult(
            trace_id=trace_id,
            query=query,
            answer=(last_response.content if last_response else "") or "(no response)",
            tool_calls=captured_calls,
            total_latency_ms=total_ms,
            input_tokens=total_in,
            output_tokens=total_out,
            model_used=self._llm.model,
            stop_reason=(last_response.stop_reason if last_response else "error"),
            intent_category="nepse_research",
            intent_reason="passed_through" if self._intent else "intent_tier_disabled",
        )

    def ask_stream(
        self,
        query: str,
        *,
        history: list[ChatTurn] | None = None,
        context: dict | None = None,
        on_done: Callable[[AgentResult], None] | None = None,
    ) -> Iterator[str]:
        """Like ask(), but streams text tokens as they arrive.

        Every LLM step is streamed. Gemini outputs EITHER function_call parts
        (tool-use steps, no text) OR text parts (synthesis step). So yielding
        text chunks as they arrive is safe: if chunks contain text it's the
        synthesis answer; tool-planning steps produce no text at all.
        Calls on_done with the full AgentResult when the stream is exhausted."""
        stream_fn = getattr(self._llm, "complete_stream", None)
        if stream_fn is None:
            # Fallback for clients without streaming support
            result = self.ask(query, history=history, context=context)
            yield result.answer
            if on_done:
                on_done(result)
            return

        started = time.perf_counter()
        trace_id = str(uuid4())
        total_in, total_out = 0, 0
        history = history or []

        _log.info("ask_stream  trace=%s  history=%d turns  query=%r", trace_id[:8], len(history), query[:100])

        messages: list[Message] = []
        for turn in history:
            t_role, t_content = _turn_role_content(turn)
            role = Role.USER if t_role == "user" else Role.ASSISTANT
            messages.append(Message(role=role, content=t_content))
        messages.append(Message(role=Role.USER, content=query))

        captured_calls: list[ToolCall] = []
        last_response: CompletionResult | None = None
        step = 0

        for step in range(self._max_steps):
            final_result: CompletionResult | None = None

            for chunk in stream_fn(
                messages,
                system=_system_prompt(context),
                tools=self._tool_specs,
            ):
                if chunk.text and not chunk.done:
                    # Gemini sends text in large batches; split to words so the
                    # caller gets fine-grained tokens regardless of chunk size.
                    words = chunk.text.split(" ")
                    for i, word in enumerate(words):
                        yield word if i == len(words) - 1 else word + " "
                if chunk.done:
                    final_result = chunk.result
                    break

            if final_result is None:
                break

            total_in += final_result.usage.input_tokens
            total_out += final_result.usage.output_tokens
            last_response = final_result

            if final_result.stop_reason != "tool_use" or not final_result.tool_calls:
                break

            # Tool-use step: run the requested tools and feed results back.
            messages.append(Message(
                role=Role.ASSISTANT,
                content=final_result.content,
                tool_calls=final_result.tool_calls,
            ))
            for tc in final_result.tool_calls:
                _log.info("tool  trace=%s  step=%d  %s(%s)",
                          trace_id[:8], step, tc.name,
                          ", ".join(f"{k}={repr(v)[:60]}" for k, v in tc.args.items()))
                tool_call_record = self._execute_tool(tc)
                captured_calls.append(tool_call_record)
                if tool_call_record.error:
                    _log.warning("tool error  trace=%s  %s → %s", trace_id[:8], tc.name, tool_call_record.error)
                else:
                    _log.info("tool ok  trace=%s  %s  %dms", trace_id[:8], tc.name, tool_call_record.latency_ms)
                messages.append(Message(
                    role=Role.TOOL,
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    tool_result=tool_call_record.output or {"error": tool_call_record.error},
                ))
        else:
            _log.warning("ask_stream hit max_steps=%d without end_turn", self._max_steps)

        total_ms = int((time.perf_counter() - started) * 1000)
        _log.info("agent done (stream)  trace=%s  steps=%d  tools=%d  latency=%dms  tok=%d/%d",
                  trace_id[:8], step + 1, len(captured_calls), total_ms, total_in, total_out)

        result = AgentResult(
            trace_id=trace_id,
            query=query,
            answer=(last_response.content if last_response else "") or "(no response)",
            tool_calls=captured_calls,
            total_latency_ms=total_ms,
            input_tokens=total_in,
            output_tokens=total_out,
            model_used=self._llm.model,
            stop_reason=(last_response.stop_reason if last_response else "error"),
            intent_category="nepse_research",
            intent_reason="streaming",
        )
        if on_done:
            on_done(result)

    async def ask_stream_async(
        self,
        query: str,
        *,
        history: list[ChatTurn] | None = None,
        context: dict | None = None,
        on_done: Callable[[AgentResult], None] | None = None,
    ) -> AsyncIterator[str]:
        """Fully async streaming agent loop.

        Uses complete_stream_async() so the SDK's native async HTTP client
        streams tokens directly into the FastAPI response — no threads, no queues.

        AFC bypass: tool-planning steps pass tools=self._tool_specs (AFC buffers,
        but those steps produce no text anyway). Synthesis steps pass tools=None
        — this bypasses the SDK's AFC buffering so tokens stream immediately."""
        stream_fn = getattr(self._llm, "complete_stream_async", None)
        if stream_fn is None:
            result = await asyncio.to_thread(self.ask, query, history=history, context=context)
            yield result.answer
            if on_done:
                on_done(result)
            return

        started = time.perf_counter()
        trace_id = str(uuid4())
        total_in, total_out = 0, 0
        history = history or []

        _log.info("ask_stream_async  trace=%s  history=%d turns  query=%r",
                  trace_id[:8], len(history), query[:100])

        messages: list[Message] = []
        for turn in history:
            t_role, t_content = _turn_role_content(turn)
            role = Role.USER if t_role == "user" else Role.ASSISTANT
            messages.append(Message(role=role, content=t_content))
        messages.append(Message(role=Role.USER, content=query))

        captured_calls: list[ToolCall] = []
        last_response: CompletionResult | None = None
        step = 0
        synthesis_mode = False  # After first tool execution: switch to no-tools streaming

        for step in range(self._max_steps):
            # synthesis_mode=True → tools=None bypasses AFC buffering → real streaming
            tools_for_step = None if synthesis_mode else self._tool_specs
            final_result: CompletionResult | None = None

            async for chunk in stream_fn(
                messages,
                system=_system_prompt(context),
                tools=tools_for_step,
            ):
                if chunk.text and not chunk.done:
                    yield chunk.text
                if chunk.done:
                    final_result = chunk.result
                    break

            if final_result is None:
                break

            total_in += final_result.usage.input_tokens
            total_out += final_result.usage.output_tokens
            last_response = final_result

            if final_result.stop_reason != "tool_use" or not final_result.tool_calls:
                break

            # Emit a status event so the UI can show what's happening during the wait
            tool_names = [tc.name.replace("get_", "").replace("_", " ") for tc in final_result.tool_calls]
            yield f"\x00Fetching {', '.join(tool_names)}…"

            messages.append(Message(
                role=Role.ASSISTANT,
                content=final_result.content,
                tool_calls=final_result.tool_calls,
            ))
            for tc in final_result.tool_calls:
                _log.info("tool  trace=%s  step=%d  %s(%s)",
                          trace_id[:8], step, tc.name,
                          ", ".join(f"{k}={repr(v)[:60]}" for k, v in tc.args.items()))
                tool_call_record = await asyncio.to_thread(self._execute_tool, tc)
                captured_calls.append(tool_call_record)
                if tool_call_record.error:
                    _log.warning("tool error  trace=%s  %s → %s",
                                 trace_id[:8], tc.name, tool_call_record.error)
                else:
                    _log.info("tool ok  trace=%s  %s  %dms",
                              trace_id[:8], tc.name, tool_call_record.latency_ms)
                messages.append(Message(
                    role=Role.TOOL,
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    tool_result=tool_call_record.output or {"error": tool_call_record.error},
                ))
            synthesis_mode = True  # All subsequent steps: synthesis, no tools
            yield "\x00Analysing…"

        else:
            _log.warning("ask_stream_async hit max_steps=%d", self._max_steps)

        total_ms = int((time.perf_counter() - started) * 1000)
        _log.info("stream done  trace=%s  steps=%d  tools=%d  latency=%dms  tok=%d/%d",
                  trace_id[:8], step + 1, len(captured_calls), total_ms, total_in, total_out)

        result = AgentResult(
            trace_id=trace_id,
            query=query,
            answer=(last_response.content if last_response else "") or "(no response)",
            tool_calls=captured_calls,
            total_latency_ms=total_ms,
            input_tokens=total_in,
            output_tokens=total_out,
            model_used=self._llm.model,
            stop_reason=(last_response.stop_reason if last_response else "error"),
            intent_category="nepse_research",
            intent_reason="streaming",
        )
        if on_done:
            on_done(result)

    # ------------------------------------------------------ tool dispatch
    def _execute_tool(self, tc: ToolCallRequest) -> ToolCall:
        """Look up tc.name in the registry, call it, capture output or error."""
        started_at = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        fn_spec = REGISTRY.get(tc.name)
        if fn_spec is None:
            return ToolCall(
                tool_name=tc.name,
                tool_version="unknown",
                input=tc.args,
                error=f"Unknown tool: {tc.name!r}",
                latency_ms=0,
                started_at=started_at,
            )
        fn, _spec = fn_spec
        try:
            response = fn(**tc.args)
            output = response.model_dump(mode="json") if hasattr(response, "model_dump") else dict(response)
            return ToolCall(
                tool_name=tc.name,
                tool_version=response.metadata.tool_version if hasattr(response, "metadata") else "1.0.0",
                input=tc.args,
                output=output,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                started_at=started_at,
            )
        except ToolError as e:
            return ToolCall(
                tool_name=tc.name,
                tool_version="1.0.0",
                input=tc.args,
                error=f"{e.reason}: {e}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                started_at=started_at,
            )
        except Exception as e:  # noqa: BLE001
            _log.exception("tool %s raised unexpected error", tc.name)
            return ToolCall(
                tool_name=tc.name,
                tool_version="1.0.0",
                input=tc.args,
                error=f"internal_error: {type(e).__name__}: {e}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                started_at=started_at,
            )
