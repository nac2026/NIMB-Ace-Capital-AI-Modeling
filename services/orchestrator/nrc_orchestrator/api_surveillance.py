"""Internal-trade surveillance API (prefix /api/surveillance).

Serves the CEO surveillance board — the firm's own fills, scored for how
suspicious they look (bad fills vs day VWAP, trades into manipulated names).
Reads the postgres.internal_trade_surveillance serving table populated by the
Gold sync. A flag for review, not a verdict.

Endpoints:
  GET  /api/surveillance/cases          — flagged fills grouped into investigation
                                          cases (fill cluster + markout curve +
                                          cached LLM explanation)
  POST /api/surveillance/explain        — generate missing LLM case explanations
  GET  /api/surveillance/trades         — raw fills (filter by tier/client/scrip/min_score)
  GET  /api/surveillance/summary        — triage-strip stats (tiers, notional, funds)
  GET  /api/surveillance/counterparties — repeat-counterparty patterns
  GET  /api/surveillance/clients        — distinct funds/portfolios in the trade book
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nrc_llm.types import Message, Role

from .agent import Agent
from .surveillance_cases import build_cases, case_context_block, generate_explanations
from .trace_writer import write_trace

_log = logging.getLogger("nrc_orchestrator.api_surveillance")

router = APIRouter(prefix="/api/surveillance", tags=["surveillance"])


def _valid_date(value: str | None, name: str) -> str | None:
    """Validate an optional YYYY-MM-DD query param (422 on garbage)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise HTTPException(422, f"{name} must be YYYY-MM-DD") from None


@router.get("/cases")
def list_cases(
    request: Request,
    min_score: float = 25,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Flagged fills grouped into investigation cases, worst first.

    Each case = one fund × scrip × day cluster with evidence rolled up:
    score/tier, pattern headline, counterparty concentration (observed vs
    expected), D+0..D+5 markout curve, the fill cluster, and the cached
    LLM explanation (null until POST /explain has run for it).
    from_date/to_date (inclusive) narrow to a session range."""
    return build_cases(
        request.app.state.pg,
        min_score=min_score,
        from_date=_valid_date(from_date, "from_date"),
        to_date=_valid_date(to_date, "to_date"),
    )


class ExplainBody(BaseModel):
    case_keys: list[str] | None = None   # restrict to these cases (visible page)


class ResponseBody(BaseModel):
    body: str
    author: str | None = None


class CaseChatBody(BaseModel):
    query: str


def _find_case(pg, case_key: str) -> dict:
    case = next((c for c in build_cases(pg, min_score=25) if c["case_key"] == case_key), None)
    if case is None:
        raise HTTPException(404, f"No flagged case {case_key}")
    return case


@router.get("/cases/{case_key}/chat")
def case_chat_history(request: Request, case_key: str) -> list[dict]:
    """The persistent chat thread for one case (restored when the panel opens)."""
    rows = request.app.state.pg.fetch_all(
        "SELECT id, role, content, created_at FROM surveillance_case_chat WHERE case_key=%s ORDER BY created_at",
        (case_key,),
    )
    return [
        {"id": r["id"], "role": r["role"], "content": r["content"],
         "created_at": r["created_at"].isoformat() if r["created_at"] else None}
        for r in rows
    ]


@router.post("/cases/{case_key}/chat/stream")
async def case_chat_stream(request: Request, case_key: str, body: CaseChatBody) -> StreamingResponse:
    """SSE chat scoped to one surveillance case.

    The full case dossier (facts, signals, market context, classification,
    note, findings, glossary) is pre-loaded into the agent's system prompt;
    the agent keeps its whole tool set for digging deeper. Every turn
    persists to surveillance_case_chat so the thread survives reopen."""
    pg = request.app.state.pg
    llm_router = request.app.state.router

    case = await run_in_threadpool(_find_case, pg, case_key)

    history_rows = pg.fetch_all(
        "SELECT role, content FROM surveillance_case_chat WHERE case_key=%s ORDER BY created_at",
        (case_key,),
    )
    history = [{"role": r["role"], "content": r["content"]} for r in history_rows]

    pg.execute(
        "INSERT INTO surveillance_case_chat (case_key, role, content) VALUES (%s, 'user', %s)",
        (case_key, body.query),
    )

    context = {"surveillance_case_block": case_context_block(case)}
    result_holder: list[Any] = []

    def on_done(r: Any) -> None:
        result_holder.append(r)

    async def generate():
        try:
            agent = Agent(llm=llm_router.synthesizer())
            async for token in agent.ask_stream_async(
                body.query, history=history, context=context, on_done=on_done,
            ):
                if token.startswith("\x00"):
                    yield f"data: {json.dumps({'type': 'status', 'text': token[1:]})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
        except Exception as e:  # noqa: BLE001
            _log.exception("case chat agent error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if result_holder:
            res = result_holder[0]
            pg.execute(
                "INSERT INTO surveillance_case_chat (case_key, role, content, trace_id) VALUES (%s, 'assistant', %s, %s)",
                (case_key, res.answer, res.trace_id),
            )
            trace = res.to_query_trace(user_id="ceo", session_id=f"surv:{case_key}")
            write_trace(trace, pg=pg)
            yield f"data: {json.dumps({'type': 'done', 'trace_id': res.trace_id})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/cases/{case_key}/chat/save-finding")
async def save_chat_finding(request: Request, case_key: str, payload: ResponseBody | None = Body(None)) -> dict:
    """Distill the case chat into a finding on the case record.

    Summarizes the thread (synthesizer LLM) into 1-3 sentences and stores it
    in surveillance_case_responses — same place manual findings live, so it
    shows on the card and feeds future note regenerations."""
    pg = request.app.state.pg
    llm_router = request.app.state.router
    author = ((payload.author if payload else None) or "CEO").strip()[:80] or "CEO"

    rows = pg.fetch_all(
        "SELECT role, content FROM surveillance_case_chat WHERE case_key=%s ORDER BY created_at",
        (case_key,),
    )
    if not rows:
        return {"ok": False, "error": "no chat to distill"}

    transcript = "\n".join(f"{r['role'].upper()}: {r['content']}" for r in rows[-20:])

    def _distill() -> str:
        client = llm_router.synthesizer()
        result = client.complete(
            messages=[Message(role=Role.USER, content=(
                "Below is an investigation chat about a flagged internal trade. Distill the "
                "reviewer's conclusion / key takeaway into a 1-3 sentence finding for the case "
                "record, written in first person from the reviewer's perspective. Concrete, "
                "factual, no hedging filler. If no conclusion was reached, summarize the open "
                "questions instead.\n\n" + transcript
            ))],
            temperature=0.2,
            max_output_tokens=220,
        )
        return (result.content or "").strip()

    text = await run_in_threadpool(_distill)
    if not text:
        return {"ok": False, "error": "distillation failed"}

    row = pg.fetch_all(
        """INSERT INTO surveillance_case_responses (case_key, author, body)
           VALUES (%s, %s, %s)
           RETURNING id, author, body, created_at""",
        (case_key, author, f"[from case chat] {text}"[:4000]),
    )
    r = row[0]
    return {
        "ok": True,
        "response": {
            "id": r["id"], "author": r["author"], "body": r["body"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        },
    }


@router.post("/cases/{case_key}/responses")
def add_case_response(request: Request, case_key: str, payload: ResponseBody = Body(...)) -> dict:
    """Record a human finding on a case — the CEO/reviewer's reply to the note.

    Stored as a thread under the case and fed back into the LLM prompt as
    analyst context the next time the note regenerates."""
    body = payload.body.strip()
    if not body:
        return {"ok": False, "error": "empty finding"}
    author = (payload.author or "CEO").strip()[:80] or "CEO"
    row = request.app.state.pg.fetch_all(
        """INSERT INTO surveillance_case_responses (case_key, author, body)
           VALUES (%s, %s, %s)
           RETURNING id, case_key, author, body, created_at""",
        (case_key, author, body[:4000]),
    )
    r = row[0]
    return {
        "ok": True,
        "response": {
            "id": r["id"], "author": r["author"], "body": r["body"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        },
    }


@router.post("/explain")
async def explain_cases(
    request: Request,
    body: ExplainBody | None = Body(None),
    min_score: float = 25,
) -> dict:
    """Generate LLM explanations for flagged cases that lack a current one.

    The frontend sends the case_keys VISIBLE on the current page, so only
    those get LLM calls — a flood of MODERATE cases never triggers a flood
    of generations. Hard-capped at 10 per call either way. Runs in a
    threadpool (sequential LLM calls, a few seconds per case)."""
    try:
        written = await run_in_threadpool(
            generate_explanations,
            request.app.state.pg,
            case_keys=(body.case_keys if body else None),
            min_score=min_score,
        )
        return {"ok": True, "generated": written}
    except Exception as e:  # noqa: BLE001
        _log.warning("explain generation failed: %s", e)
        return {"ok": False, "generated": 0, "error": str(e)}


@router.get("/trades")
def list_trades(
    request: Request,
    tier: str | None = None,
    client_code: str | None = None,
    scrip: str | None = None,
    min_score: float = 0,
    limit: int = 200,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Flagged internal fills, worst first. Optional tier/client/scrip/date filters."""
    where = ["surveillance_score >= %s"]
    params: list = [min_score]
    if tier:
        where.append("surveillance_tier = %s")
        params.append(tier.strip().upper())
    if client_code:
        where.append("client_code = %s")
        params.append(client_code.strip())
    if scrip:
        where.append("scrip = %s")
        params.append(scrip.strip().upper())
    if f := _valid_date(from_date, "from_date"):
        where.append("trade_date >= %s::date")
        params.append(f)
    if t := _valid_date(to_date, "to_date"):
        where.append("trade_date <= %s::date")
        params.append(t)
    params.append(min(max(limit, 1), 1000))
    # LEFT JOIN the broker reference dimension so the board can name the broker
    # the fund used and the counterparty instead of showing anonymous codes.
    return request.app.state.pg.fetch_all(
        f"""
        SELECT s.contract_number, s.trade_date, s.scrip, s.client_code, s.client_name, s.side,
               s.our_qty, s.our_value, s.our_price, s.day_vwap, s.interval_vwap,
               s.our_broker, s.counterparty_broker,
               ob.name AS our_broker_name, cb.name AS counterparty_broker_name,
               s.slippage_vs_vwap_pct, s.slippage_npr, s.worse_than_range_flag,
               s.markout_5d_pct, s.cp_surprise_z, s.exit_liquidity_flag,
               s.cross_flag, s.churn_flag, s.bought_near_peak_flag,
               s.scrip_speculation_tier, s.scrip_concentration_flag, s.scrip_pump_flag,
               s.surveillance_score, s.surveillance_tier, s.flag_reasons
        FROM internal_trade_surveillance s
        LEFT JOIN brokers ob ON ob.broker = s.our_broker
        LEFT JOIN brokers cb ON cb.broker = s.counterparty_broker
        WHERE {' AND '.join(where)}
        ORDER BY s.surveillance_score DESC, s.trade_date DESC
        LIMIT %s
        """,
        tuple(params),
    )


@router.get("/summary")
def summary(
    request: Request,
    min_score: float = 25,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Triage-strip stats: tier counts, flagged notional, funds, freshness.

    from_date/to_date narrow every stat to that session window; book_first_date/
    book_last_date always report the UNFILTERED bounds so the UI can bound its
    date pickers and label "viewing N of M sessions"."""
    pg = request.app.state.pg
    where = ["TRUE"]
    params: list = []
    if f := _valid_date(from_date, "from_date"):
        where.append("trade_date >= %s::date")
        params.append(f)
    if t := _valid_date(to_date, "to_date"):
        where.append("trade_date <= %s::date")
        params.append(t)
    window = " AND ".join(where)

    by_tier = pg.fetch_all(
        f"""SELECT surveillance_tier AS tier, COUNT(*) AS n
           FROM internal_trade_surveillance WHERE {window} GROUP BY surveillance_tier""",
        tuple(params),
    )
    by_client = pg.fetch_all(
        f"""SELECT client_code, client_name,
                  COUNT(*) AS n_trades,
                  COUNT(*) FILTER (WHERE surveillance_score >= %s) AS n_flagged
           FROM internal_trade_surveillance
           WHERE {window}
           GROUP BY client_code, client_name
           ORDER BY n_flagged DESC, n_trades DESC""",
        (min_score, *params),
    )
    agg = pg.fetch_all(
        f"""SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE surveillance_score >= %s) AS flagged,
                  COALESCE(SUM(our_value) FILTER (WHERE surveillance_score >= %s), 0) AS flagged_notional,
                  -- distinct fund NAMES: multiple account codes of the same
                  -- scheme (names canonicalized to uppercase in Silver) count once
                  COUNT(DISTINCT COALESCE(client_name, client_code)) AS n_funds,
                  MIN(trade_date) AS first_date,
                  MAX(trade_date) AS last_date,
                  MAX(computed_at) AS computed_at
           FROM internal_trade_surveillance WHERE {window}""",
        (min_score, min_score, *params),
    )
    # Unfiltered book bounds + distinct session list for the date pickers.
    book = pg.fetch_all(
        """SELECT MIN(trade_date) AS first_date, MAX(trade_date) AS last_date,
                  COUNT(DISTINCT trade_date) AS n_sessions
           FROM internal_trade_surveillance"""
    )
    sessions = pg.fetch_all(
        """SELECT DISTINCT trade_date FROM internal_trade_surveillance
           ORDER BY trade_date"""
    )
    b = book[0] if book else {}
    a = agg[0] if agg else {}
    total = int(a.get("total") or 0)
    flagged = int(a.get("flagged") or 0)
    return {
        "total": total,
        "flagged": flagged,
        "clean_rate": round(100 * (total - flagged) / total, 1) if total else None,
        "flagged_notional": float(a.get("flagged_notional") or 0),
        "n_funds": int(a.get("n_funds") or 0),
        "first_date": str(a["first_date"]) if a.get("first_date") else None,
        "last_date": str(a["last_date"]) if a.get("last_date") else None,
        "computed_at": a["computed_at"].isoformat() if a.get("computed_at") else None,
        "book_first_date": str(b["first_date"]) if b.get("first_date") else None,
        "book_last_date": str(b["last_date"]) if b.get("last_date") else None,
        "book_n_sessions": int(b.get("n_sessions") or 0),
        "book_sessions": [str(r["trade_date"]) for r in sessions],
        "by_tier": {r["tier"]: r["n"] for r in by_tier},
        "by_client": by_client,
    }


@router.get("/counterparties")
def counterparties(request: Request, min_trades: int = 2, limit: int = 50) -> list[dict]:
    """Counterparty repeat-trading patterns, most statistically surprising first.

    The collusion-proxy board: which brokers keep ending up on the other side
    of the fund's flow far beyond their market share in that scrip."""
    return request.app.state.pg.fetch_all(
        """
        SELECT e.client_code, e.client_name, e.counterparty_broker,
               b.name AS counterparty_broker_name, e.scrip,
               e.n_trades, e.total_qty, e.total_amount, e.n_days,
               e.first_date, e.last_date,
               e.share_of_fund_qty, e.cp_market_share, e.surprise_z,
               e.cp_is_accumulator, e.cp_is_distributor, e.cp_in_wash_pair, e.cp_flagged
        FROM internal_counterparty_exposure e
        LEFT JOIN brokers b ON b.broker = e.counterparty_broker
        WHERE e.n_trades >= %s
        ORDER BY e.surprise_z DESC NULLS LAST
        LIMIT %s
        """,
        (min_trades, min(max(limit, 1), 500)),
    )


@router.get("/clients")
def clients(request: Request) -> list[dict]:
    """Distinct funds/portfolios present in the surveilled trade book."""
    return request.app.state.pg.fetch_all(
        """SELECT DISTINCT client_code, client_name
           FROM internal_trade_surveillance ORDER BY client_name"""
    )
