"""Speculative Analysis API — CEO-facing upload + analyze + review workflow.

Endpoints:
  POST   /api/speculative/upload                          multipart upload
  POST   /api/speculative/{id}/analyze                    run rules + LLM
  GET    /api/speculative/sessions                         list past analyses
  GET    /api/speculative/sessions/{id}                    full session detail
  DELETE /api/speculative/sessions/{id}                    cascade delete
  POST   /api/speculative/sessions/{id}/chat               persistent chat (non-stream)
  POST   /api/speculative/sessions/{id}/chat/stream        SSE chat endpoint
  GET    /api/speculative/sample-template.csv              static CSV template

Persistence: analysis_sessions + analysis_results + analysis_chat_turns
(all in Postgres — survives restarts and runs separately from the
short-lived Redis chat memory used by the Research drawer).
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Path, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from nrc_storage import PostgresClient

from .agent import Agent
from .conversation import ConversationStore  # noqa: F401 — used via app.state
from .speculative import extract_text, run_review_from_text
from .speculative_pipeline import analyze_tickers, generate_narrative, _build_detail_fallback
from .trace_writer import write_trace

# File extensions that mean "written report" (review mode) vs "ticker list" (screen mode).
_REVIEW_EXTS = (".pdf", ".docx", ".doc", ".txt")

_log = logging.getLogger("nrc_orchestrator.api_speculative")

router = APIRouter(prefix="/api/speculative", tags=["speculative"])


# ─── Pydantic response shapes ───────────────────────────────────────
class UploadResponse(BaseModel):
    session_id: uuid.UUID
    title: str
    mode: str = "screen"                # screen (ticker list) | review (written report)
    n_tickers: int
    tickers: list[str]
    unknown_tickers: list[str]
    status: str


class AnalyzeResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    n_results: int


class SessionListItem(BaseModel):
    session_id: uuid.UUID
    title: str
    notes: str | None = None
    n_tickers: int
    n_green: int
    n_amber: int
    n_red: int
    n_unknown: int
    # Cohort counters
    n_value: int = 0
    n_fundamental: int = 0
    n_out: int = 0
    status: str
    created_at: datetime
    completed_at: datetime | None = None


class RuleOutcome(BaseModel):
    rule: str
    status: Literal["green", "amber", "red"]
    value: Any
    threshold: str


class AnalysisResult(BaseModel):
    scrip: str
    company_name: str | None = None
    sector: str | None = None
    flag: Literal["green", "amber", "red", "unknown"]
    flag_score: float | None = None
    cohort: Literal["value_universe", "fundamental_universe", "out_of_universe", "unknown"] = "unknown"
    cohort_reason: str | None = None
    headline: str | None = None
    # 3-5 sentence LLM-generated descriptive verdict shown in the detail modal.
    # Falls back to a templated rationale when the LLM block fails to parse.
    detail_rationale: str | None = None
    rule_outcomes: list[RuleOutcome] = Field(default_factory=list)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ChatTurn(BaseModel):
    turn_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ReviewClaim(BaseModel):
    scrip: str | None = None
    claim_text: str
    claim_type: str | None = None
    verdict: str | None = None
    actual_value: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class ReviewAspect(BaseModel):
    scrip: str | None = None
    aspect: str
    rating: str | None = None
    score: float | None = None
    assessment: str | None = None


class ReviewDebateTurn(BaseModel):
    role: str
    content: str


class SessionDetail(BaseModel):
    session: SessionListItem
    mode: str = "screen"
    tickers: list[str]
    results: list[AnalysisResult]
    narrative_md: str | None = None
    narrative_model: str | None = None
    chat: list[ChatTurn] = Field(default_factory=list)
    # Review-mode fields
    verdict: str | None = None
    verdict_confidence: float | None = None
    claims: list[ReviewClaim] = Field(default_factory=list)
    aspects: list[ReviewAspect] = Field(default_factory=list)
    debate: list[ReviewDebateTurn] = Field(default_factory=list)


class ChatRequestBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


# ─── Helpers ────────────────────────────────────────────────────────
def _parse_tickers_from_bytes(content: bytes, filename: str) -> list[str]:
    """Read the upload and extract a `scrip` / `ticker` / `symbol` column."""
    name = filename.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        else:
            raise HTTPException(400, f"Unsupported file type: {filename} (use .csv or .xlsx)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {e}") from e

    if df.empty:
        raise HTTPException(400, "Uploaded file has no rows.")

    cols_norm = {str(c).lower().strip(): c for c in df.columns}
    col_key = next((k for k in ("scrip", "ticker", "symbol", "stock") if k in cols_norm), None)
    if col_key is None:
        # Fall back to the first column
        col = df.columns[0]
    else:
        col = cols_norm[col_key]

    tickers: set[str] = set()
    for v in df[col].tolist():
        if pd.isna(v):
            continue
        s = str(v).strip().upper()
        if s:
            tickers.add(s)
    return sorted(tickers)


def _split_known_unknown(pg: PostgresClient, tickers: list[str]) -> tuple[list[str], list[str]]:
    if not tickers:
        return [], []
    rows = pg.fetch_all(
        "SELECT scrip FROM scrips WHERE is_active AND scrip = ANY(%(t)s)",
        {"t": tickers},
    )
    known = {r["scrip"] for r in rows}
    known_list = [t for t in tickers if t in known]
    unknown_list = [t for t in tickers if t not in known]
    return known_list, unknown_list


def _session_to_list_item(row: dict) -> SessionListItem:
    return SessionListItem(
        session_id=row["session_id"],
        title=row["title"],
        notes=row.get("notes"),
        n_tickers=row["n_tickers"],
        n_green=row.get("n_green") or 0,
        n_amber=row.get("n_amber") or 0,
        n_red=row.get("n_red") or 0,
        n_unknown=row.get("n_unknown") or 0,
        n_value=row.get("n_value") or 0,
        n_fundamental=row.get("n_fundamental") or 0,
        n_out=row.get("n_out") or 0,
        status=row["status"],
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )


# ─── Endpoints ──────────────────────────────────────────────────────
@router.post("/upload", response_model=UploadResponse)
async def upload_session(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    notes: str | None = Form(None),
) -> UploadResponse:
    pg: PostgresClient = request.app.state.pg
    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty.")

    filename = file.filename or "upload.csv"
    session_id = uuid.uuid4()
    is_review = filename.lower().endswith(_REVIEW_EXTS)

    if is_review:
        # Written research report → review mode. Extract text now (cheap); the
        # LLM verification runs at /analyze.
        report_text = extract_text(content, filename)
        if not report_text.strip():
            raise HTTPException(400, "Could not extract any text from the report.")
        final_title = (title or "").strip() or f"Review · {filename}"
        pg.execute(
            """
            INSERT INTO analysis_sessions
                (session_id, user_id, title, notes, source_filename,
                 tickers, n_tickers, status, mode, report_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'review',%s)
            """,
            (str(session_id), "ceo", final_title, (notes or None) and notes.strip(),
             filename, [], 0, "pending", report_text),
        )
        return UploadResponse(
            session_id=session_id, title=final_title, mode="review",
            n_tickers=0, tickers=[], unknown_tickers=[], status="pending",
        )

    # Ticker shortlist → screen mode (existing behaviour).
    all_tickers = _parse_tickers_from_bytes(content, filename)
    if not all_tickers:
        raise HTTPException(400, "No tickers found in uploaded file.")
    known, unknown = _split_known_unknown(pg, all_tickers)
    final_title = (title or "").strip() or f"Analysis · {filename}"

    pg.execute(
        """
        INSERT INTO analysis_sessions
            (session_id, user_id, title, notes, source_filename,
             tickers, n_tickers, status, mode)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'screen')
        """,
        (
            str(session_id), "ceo", final_title, (notes or None) and notes.strip(),
            filename, all_tickers, len(all_tickers), "pending",
        ),
    )

    return UploadResponse(
        session_id=session_id,
        title=final_title,
        mode="screen",
        n_tickers=len(all_tickers),
        tickers=known,
        unknown_tickers=unknown,
        status="pending",
    )


@router.post("/{session_id}/analyze", response_model=AnalyzeResponse)
async def run_analysis(
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: uuid.UUID = Path(...),
) -> AnalyzeResponse:
    pg: PostgresClient = request.app.state.pg

    sess = pg.fetch_one(
        "SELECT session_id, title, tickers, n_tickers, status, mode, report_text "
        "FROM analysis_sessions WHERE session_id = %s",
        (str(session_id),),
    )
    if sess is None:
        raise HTTPException(404, "Analysis session not found.")

    if sess["status"] in ("running", "succeeded"):
        return AnalyzeResponse(
            session_id=session_id, status=sess["status"],
            n_results=sess["n_tickers"],
        )

    # Review mode — written report: the multi-agent pipeline takes 30-90s, so run
    # it in the background and let the client poll get_session (status=running).
    if sess.get("mode") == "review":
        if not sess.get("report_text"):
            raise HTTPException(400, "No report text stored for this review session.")
        pg.execute(
            "UPDATE analysis_sessions SET status='running', started_at=now(), error_message=NULL WHERE session_id=%s",
            (str(session_id),),
        )
        report_text = sess["report_text"]

        def _bg() -> None:
            try:
                run_review_from_text(str(session_id), report_text, pg)
            except Exception:  # noqa: BLE001 — status is set to 'failed' inside the pipeline
                _log.exception("background review failed for %s", session_id)

        background_tasks.add_task(_bg)
        return AnalyzeResponse(session_id=session_id, status="running", n_results=0)

    pg.execute(
        "UPDATE analysis_sessions SET status='running', started_at=now(), error_message=NULL WHERE session_id=%s",
        (str(session_id),),
    )
    pg.execute("DELETE FROM analysis_results WHERE session_id=%s", (str(session_id),))

    try:
        results = analyze_tickers(list(sess["tickers"]), pg=pg)
    except Exception as e:
        _log.exception("analysis pipeline failed")
        pg.execute(
            "UPDATE analysis_sessions SET status='failed', error_message=%s, completed_at=now() WHERE session_id=%s",
            (str(e), str(session_id)),
        )
        raise HTTPException(500, f"Analysis failed: {e}") from e

    # LLM narrative comes first so per-ticker remarks/details can override the
    # template headline + provide rationale before we insert.
    narrative_md, narrative_model, per_ticker_remarks, per_ticker_details = generate_narrative(
        title=sess["title"],
        n_tickers=sess["n_tickers"],
        results=results,
    )

    # Insert per-ticker results — use LLM content if available, else templated fallback
    for r in results:
        llm_remark = per_ticker_remarks.get(r["scrip"])
        headline   = llm_remark or r.get("headline")
        # Detail rationale: prefer the LLM-generated paragraph, fall back to a
        # templated composition from cohort_reason + rule outcomes so the modal
        # always has substantial content.
        detail_rationale = per_ticker_details.get(r["scrip"]) or _build_detail_fallback(r)
        pg.execute(
            """
            INSERT INTO analysis_results
                (session_id, scrip, company_name, sector, flag, flag_score,
                 cohort, cohort_reason, rule_outcomes, snapshot, headline,
                 detail_rationale, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
            """,
            (
                str(session_id), r["scrip"], r.get("company_name"), r.get("sector"),
                r["flag"], r.get("flag_score"),
                r.get("cohort", "unknown"), r.get("cohort_reason"),
                json.dumps(r.get("rule_outcomes", []), default=str),
                json.dumps(r.get("snapshot", {}), default=str),
                headline, detail_rationale, r.get("error"),
            ),
        )

    final_status = "succeeded" if narrative_md else "partial"
    pg.execute(
        """
        UPDATE analysis_sessions
           SET status=%s, narrative_md=%s, narrative_model=%s, completed_at=now()
         WHERE session_id=%s
        """,
        (final_status, narrative_md, narrative_model, str(session_id)),
    )

    return AnalyzeResponse(
        session_id=session_id, status=final_status, n_results=len(results),
    )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(request: Request, limit: int = 50) -> list[SessionListItem]:
    pg: PostgresClient = request.app.state.pg
    rows = pg.fetch_all(
        """
        SELECT s.session_id, s.title, s.notes, s.n_tickers, s.status,
               s.created_at, s.completed_at,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='green'), 0)::int   AS n_green,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='amber'), 0)::int   AS n_amber,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='red'),   0)::int   AS n_red,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='unknown'), 0)::int AS n_unknown,
               COALESCE(COUNT(r.*) FILTER (WHERE r.cohort='value_universe'),       0)::int AS n_value,
               COALESCE(COUNT(r.*) FILTER (WHERE r.cohort='fundamental_universe'), 0)::int AS n_fundamental,
               COALESCE(COUNT(r.*) FILTER (WHERE r.cohort='out_of_universe'),      0)::int AS n_out
          FROM analysis_sessions s
          LEFT JOIN analysis_results r ON r.session_id = s.session_id
         GROUP BY s.session_id
         ORDER BY s.created_at DESC
         LIMIT %s
        """,
        (limit,),
    )
    return [_session_to_list_item(r) for r in rows]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(request: Request, session_id: uuid.UUID = Path(...)) -> SessionDetail:
    pg: PostgresClient = request.app.state.pg

    sess = pg.fetch_one(
        """
        SELECT s.session_id, s.title, s.notes, s.n_tickers, s.status, s.created_at, s.completed_at,
               s.tickers, s.narrative_md, s.narrative_model,
               s.mode, s.verdict, s.verdict_confidence,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='green'),   0)::int AS n_green,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='amber'),   0)::int AS n_amber,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='red'),     0)::int AS n_red,
               COALESCE(COUNT(r.*) FILTER (WHERE r.flag='unknown'), 0)::int AS n_unknown,
               COALESCE(COUNT(r.*) FILTER (WHERE r.cohort='value_universe'),       0)::int AS n_value,
               COALESCE(COUNT(r.*) FILTER (WHERE r.cohort='fundamental_universe'), 0)::int AS n_fundamental,
               COALESCE(COUNT(r.*) FILTER (WHERE r.cohort='out_of_universe'),      0)::int AS n_out
          FROM analysis_sessions s
          LEFT JOIN analysis_results r ON r.session_id = s.session_id
         WHERE s.session_id = %s
         GROUP BY s.session_id
        """,
        (str(session_id),),
    )
    if sess is None:
        raise HTTPException(404, "Analysis session not found.")

    result_rows = pg.fetch_all(
        """
        SELECT scrip, company_name, sector, flag, flag_score,
               cohort, cohort_reason, rule_outcomes, snapshot, headline,
               detail_rationale, error
          FROM analysis_results
         WHERE session_id = %s
         ORDER BY
            -- cohort priority: Value first, then Fundamental, then Out, then Unknown
            CASE COALESCE(cohort, 'unknown')
              WHEN 'value_universe'       THEN 0
              WHEN 'fundamental_universe' THEN 1
              WHEN 'out_of_universe'      THEN 2
              ELSE 3
            END,
            -- within a cohort, sort by flag_score descending (best first)
            COALESCE(flag_score, -1) DESC,
            scrip
        """,
        (str(session_id),),
    )

    chat_rows = pg.fetch_all(
        "SELECT turn_id, role, content, created_at FROM analysis_chat_turns WHERE session_id=%s ORDER BY created_at",
        (str(session_id),),
    )

    # Review-mode payload (empty for screen mode).
    claims: list[ReviewClaim] = []
    aspects: list[ReviewAspect] = []
    debate: list[ReviewDebateTurn] = []
    if sess.get("mode") == "review":
        claims = [ReviewClaim(
            scrip=c.get("scrip"), claim_text=c["claim_text"], claim_type=c.get("claim_type"),
            verdict=c.get("verdict"), actual_value=c.get("actual_value"),
            evidence=c.get("evidence") or {},
        ) for c in pg.fetch_all(
            "SELECT scrip, claim_text, claim_type, verdict, actual_value, evidence "
            "FROM analysis_claims WHERE session_id=%s ORDER BY verdict, scrip", (str(session_id),))]
        aspects = [ReviewAspect(
            scrip=a.get("scrip"), aspect=a["aspect"], rating=a.get("rating"),
            score=a.get("score"), assessment=a.get("assessment"),
        ) for a in pg.fetch_all(
            "SELECT scrip, aspect, rating, score, assessment FROM analysis_aspects "
            "WHERE session_id=%s ORDER BY scrip, aspect", (str(session_id),))]
        debate = [ReviewDebateTurn(role=d["role"], content=d["content"])
                  for d in pg.fetch_all(
            "SELECT role, content FROM analysis_debate WHERE session_id=%s ORDER BY "
            "CASE role WHEN 'bull' THEN 0 WHEN 'bear' THEN 1 ELSE 2 END", (str(session_id),))]

    results = [
        AnalysisResult(
            scrip=r["scrip"],
            company_name=r.get("company_name"),
            sector=r.get("sector"),
            flag=r["flag"],
            flag_score=r.get("flag_score"),
            cohort=(r.get("cohort") or "unknown"),
            cohort_reason=r.get("cohort_reason"),
            headline=r.get("headline"),
            detail_rationale=r.get("detail_rationale"),
            rule_outcomes=r.get("rule_outcomes") or [],
            snapshot=r.get("snapshot") or {},
            error=r.get("error"),
        )
        for r in result_rows
    ]

    return SessionDetail(
        session=_session_to_list_item(sess),
        mode=sess.get("mode") or "screen",
        tickers=list(sess.get("tickers") or []),
        results=results,
        narrative_md=sess.get("narrative_md"),
        narrative_model=sess.get("narrative_model"),
        chat=[ChatTurn(**c) for c in chat_rows],
        verdict=sess.get("verdict"),
        verdict_confidence=sess.get("verdict_confidence"),
        claims=claims,
        aspects=aspects,
        debate=debate,
    )


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: uuid.UUID = Path(...)) -> dict:
    pg: PostgresClient = request.app.state.pg
    n = pg.execute("DELETE FROM analysis_sessions WHERE session_id=%s", (str(session_id),))
    if n == 0:
        raise HTTPException(404, "Analysis session not found.")
    return {"status": "deleted", "session_id": str(session_id)}


# ─── Persistent chat scoped to a session ────────────────────────────
def _build_speculative_context(sess_detail: SessionDetail) -> dict:
    by_flag = {"green": [], "amber": [], "red": [], "unknown": []}
    for r in sess_detail.results:
        by_flag[r.flag].append(r.scrip)
    return {
        "speculative_analysis_id": str(sess_detail.session.session_id),
        "speculative_title": sess_detail.session.title,
        "speculative_tickers": sess_detail.tickers,
        "speculative_red": by_flag["red"],
        "speculative_amber": by_flag["amber"],
        "speculative_green": by_flag["green"],
    }


@router.post("/sessions/{session_id}/chat/stream")
async def session_chat_stream(
    request: Request,
    body: ChatRequestBody,
    session_id: uuid.UUID = Path(...),
) -> StreamingResponse:
    pg: PostgresClient = request.app.state.pg
    llm_router = request.app.state.router

    detail = await get_session(request, session_id)

    # Load chat history from Postgres (not Redis)
    history_rows = pg.fetch_all(
        "SELECT role, content FROM analysis_chat_turns WHERE session_id=%s ORDER BY created_at",
        (str(session_id),),
    )
    history = [{"role": r["role"], "content": r["content"]} for r in history_rows]

    # Persist the user message right away
    pg.execute(
        "INSERT INTO analysis_chat_turns (session_id, role, content) VALUES (%s, 'user', %s)",
        (str(session_id), body.query),
    )

    context = _build_speculative_context(detail)

    result_holder: list = []

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
        except Exception as e:
            _log.exception("speculative chat agent error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if result_holder:
            res = result_holder[0]
            pg.execute(
                "INSERT INTO analysis_chat_turns (session_id, role, content, trace_id) VALUES (%s, 'assistant', %s, %s)",
                (str(session_id), res.answer, res.trace_id),
            )
            trace = res.to_query_trace(user_id="ceo", session_id=str(session_id))
            write_trace(trace, pg=pg)
            yield f"data: {json.dumps({'type': 'done', 'trace_id': res.trace_id})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sample-template.csv")
async def sample_template_csv() -> PlainTextResponse:
    csv = "scrip\nNABIL\nNICASIA\nEBL\nSCB\nKBL\n"
    return PlainTextResponse(
        content=csv,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="speculative_template.csv"'},
    )
