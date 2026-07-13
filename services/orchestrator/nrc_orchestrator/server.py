"""FastAPI chat endpoint + health checks.

POST /chat — one-shot question/answer (no streaming yet; will add SSE once
the basic loop is validated in production). Returns the final answer, the
tool-use audit trail, and the trace_id for correlating with logs.

GET /health   — liveness (process is up)
GET /ready    — readiness (can reach Postgres + Vertex)
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from nrc_contracts import LiveTick
from nrc_llm import get_router
from nrc_storage import PostgresClient, RedisClient, get_settings

from .agent import Agent, AgentResult
from .api_alerts import alerts_background_loop, router as alerts_router
from .api_compare import router as compare_router
from .api_data import router as data_router
from .api_pipeline import router as pipeline_router
from .api_screen import router as screen_router
from .api_scrip import router as scrip_router
from .api_smtm import router as smtm_router
from .api_speculative import router as speculative_router
from .api_surveillance import router as surveillance_router
from .api_uploads import router as uploads_router
from .conversation import ConversationStore
from .trace_writer import write_trace

_log = logging.getLogger("nrc_orchestrator.server")


# ------------------------------------------------------------ request/response
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None
    session_id: str | None = None
    # `context` carries page-level scrip awareness from the chat drawer.
    # Shape: {"current_scrip": "NABIL"} | {"current_scrips": ["NABIL","NICA"]}
    # | {"current_screen": "top-quality"}. Agent prepends a one-liner to
    # the system prompt so the LLM sees it without the user restating the
    # scrip. Backward compatible — missing means no change.
    context: dict[str, Any] | None = None


class ToolCallSummary(BaseModel):
    tool: str
    input: dict[str, Any]
    latency_ms: int
    error: str | None = None


class ChatResponse(BaseModel):
    trace_id: str
    answer: str
    tool_calls: list[ToolCallSummary]
    total_latency_ms: int
    input_tokens: int
    output_tokens: int
    model_used: str
    intent_category: str
    intent_reason: str


async def _retention_loop(pg: PostgresClient) -> None:
    """Hourly: delete tick_history rows older than 7 days to bound table growth."""
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(
                pg.execute,
                "DELETE FROM tick_history WHERE tick_at < NOW() - INTERVAL '7 days'",
            )
            _log.info("retention: pruned tick_history rows older than 7 days")
        except Exception as exc:
            _log.warning("retention job failed: %s", exc)


# ---------------------------------------------------------------- lifespan
@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Open one shared Postgres pool at startup, close at shutdown."""
    pg = PostgresClient()
    pg.open()
    app.state.pg = pg
    app.state.redis = RedisClient()
    app.state.convo = ConversationStore(redis=app.state.redis)
    app.state.router = get_router()  # warms the Vertex client on first request
    settings = get_settings()
    app.state.redis_pub = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    retention_task = asyncio.create_task(_retention_loop(pg))
    alerts_task = asyncio.create_task(alerts_background_loop(pg))
    _log.info("orchestrator ready")
    try:
        yield
    finally:
        retention_task.cancel()
        alerts_task.cancel()
        pg.close()
        await app.state.redis_pub.aclose()
        _log.info("orchestrator shutdown complete")


app = FastAPI(
    title="NEPSE Research Copilot",
    version="0.1.0",
    description="Internal research tool — LLM agent over NEPSE data.",
    lifespan=_lifespan,
)

# CORS for the Next.js dev server on :3000 and whatever deploy URL is configured.
_allowed_origins = os.getenv(
    "NRC_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Read-only data endpoints
app.include_router(data_router)        # /api/universe, /api/indices, /api/stage2, /api/scorecard, /api/quadrant, /api/sector-momentum
app.include_router(scrip_router)       # /api/scrip/{symbol}/*
app.include_router(smtm_router)        # /api/scrip/{symbol}/{financials,intraday}, /api/index/{slug}/timeseries (live SMTM)
app.include_router(compare_router)     # /api/compare
app.include_router(screen_router)      # /api/screen/*
app.include_router(pipeline_router)    # /api/pipeline/refresh, /api/pipeline/status
app.include_router(speculative_router) # /api/speculative/*
app.include_router(alerts_router)      # /api/alerts/*
app.include_router(surveillance_router) # /api/surveillance/*
app.include_router(uploads_router)     # /api/internal/uploads/*


# ---------------------------------------------------------------- endpoints
@app.get("/health")
def health() -> dict:
    """Liveness — process is serving HTTP. Used by platform health probes."""
    return {"status": "ok"}


@app.get("/ready")
def ready(request: Request) -> dict:
    """Readiness — downstream dependencies reachable."""
    pg: PostgresClient = request.app.state.pg
    checks = {
        "postgres": pg.ping(),
        # Don't burn Vertex quota on readiness pings — model is assumed
        # available unless a real request fails. Extend here if the customer
        # wants a synthetic Vertex ping.
    }
    healthy = all(checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    """Run one user question through the full tool-use loop."""
    router = request.app.state.router
    convo: ConversationStore = request.app.state.convo

    _log.info("► query=%r  session=%s", req.query[:120], req.session_id or "none")

    history = convo.load(req.session_id) if req.session_id else []

    agent = Agent(llm=router.synthesizer())
    result = agent.ask(req.query, history=history, context=req.context)

    _log.info(
        "◄ trace=%s  intent=%s  tools=%d  latency=%dms  tok_in=%d  tok_out=%d",
        result.trace_id[:8], result.intent_category,
        len(result.tool_calls), result.total_latency_ms,
        result.input_tokens, result.output_tokens,
    )

    if req.session_id:
        convo.append(req.session_id, user=req.query, assistant=result.answer)

    trace = result.to_query_trace(user_id=req.user_id, session_id=req.session_id)
    write_trace(trace, pg=request.app.state.pg)

    return ChatResponse(
        trace_id=result.trace_id,
        answer=result.answer,
        tool_calls=[
            ToolCallSummary(
                tool=tc.tool_name,
                input=tc.input,
                latency_ms=tc.latency_ms,
                error=tc.error,
            )
            for tc in result.tool_calls
        ],
        total_latency_ms=result.total_latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        model_used=result.model_used,
        intent_category=result.intent_category,
        intent_reason=result.intent_reason,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Stream the synthesis step via Server-Sent Events.

    Uses ask_stream_async() which drives the SDK's native async HTTP client
    directly — no thread pools, no queues. Each await in the async generator
    gives uvicorn a chance to flush the chunk immediately.

    AFC bypass: synthesis calls omit tools= so the SDK doesn't hold tokens
    waiting to inspect for function calls (AFC buffering).

    Events:
      data: {"type": "token", "text": "..."}   — one text fragment
      data: {"type": "done",  "trace_id": "..."} — stream complete
      data: {"type": "error", "message": "..."}  — failure
    """
    router = request.app.state.router
    convo: ConversationStore = request.app.state.convo

    _log.info("► stream  query=%r  session=%s", req.query[:120], req.session_id or "none")

    history = convo.load(req.session_id) if req.session_id else []
    result_holder: list = []

    def on_done(r: Any) -> None:
        result_holder.append(r)

    async def generate():
        try:
            agent = Agent(llm=router.synthesizer())
            async for token in agent.ask_stream_async(
                req.query, history=history, context=req.context, on_done=on_done
            ):
                if token.startswith("\x00"):
                    yield f"data: {json.dumps({'type': 'status', 'text': token[1:]})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
        except Exception as e:
            _log.exception("stream agent error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if result_holder:
            result = result_holder[0]
            _log.info("◄ stream  trace=%s  tools=%d  latency=%dms",
                      result.trace_id[:8], len(result.tool_calls), result.total_latency_ms)
            if req.session_id:
                convo.append(req.session_id, user=req.query, assistant=result.answer)
            trace = result.to_query_trace(user_id=req.user_id, session_id=req.session_id)
            write_trace(trace, pg=request.app.state.pg)
            yield f"data: {json.dumps({'type': 'done', 'trace_id': result.trace_id})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/chat/session/{session_id}")
def clear_session(session_id: str, request: Request) -> dict:
    """Wipe the conversation memory for one session_id."""
    convo: ConversationStore = request.app.state.convo
    convo.clear(session_id)
    return {"status": "cleared", "session_id": session_id}


# ---------------------------------------------------------------- real-time
class TickIngestRequest(BaseModel):
    scrip: str
    price: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int = 0
    turnover: float = 0.0
    change_abs: float | None = None
    change_pct: float | None = None
    prev_close: float | None = None
    source: str = "simulator"


@app.post("/ingest/tick", status_code=200)
def ingest_tick(req: TickIngestRequest, request: Request) -> dict:
    """Accept a single market tick, persist it, and broadcast via Redis pub/sub.

    1. UPSERT into live_quotes (one row per scrip — always the latest)
    2. INSERT into tick_history (append-only audit trail)
    3. PUBLISH to Redis channel 'market:ticks' for SSE broadcast
    """
    pg: PostgresClient = request.app.state.pg
    redis_client: RedisClient = request.app.state.redis
    now = datetime.now(timezone.utc)

    pg.execute(
        """
        INSERT INTO live_quotes
            (scrip, price, open, high, low, volume, turnover,
             change_abs, change_pct, prev_close, tick_at, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (scrip) DO UPDATE SET
            price      = EXCLUDED.price,
            open       = EXCLUDED.open,
            high       = EXCLUDED.high,
            low        = EXCLUDED.low,
            volume     = EXCLUDED.volume,
            turnover   = EXCLUDED.turnover,
            change_abs = EXCLUDED.change_abs,
            change_pct = EXCLUDED.change_pct,
            prev_close = EXCLUDED.prev_close,
            tick_at    = EXCLUDED.tick_at,
            source     = EXCLUDED.source
        """,
        (
            req.scrip.upper(), req.price, req.open, req.high, req.low,
            req.volume, req.turnover, req.change_abs, req.change_pct,
            req.prev_close, now, req.source,
        ),
    )

    pg.execute(
        """
        INSERT INTO tick_history (scrip, price, volume, tick_at, source)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (req.scrip.upper(), req.price, req.volume, now, req.source),
    )

    tick_payload = json.dumps({
        "scrip": req.scrip.upper(),
        "price": req.price,
        "open": req.open,
        "high": req.high,
        "low": req.low,
        "volume": req.volume,
        "turnover": req.turnover,
        "change_abs": req.change_abs,
        "change_pct": req.change_pct,
        "prev_close": req.prev_close,
        "tick_at": now.isoformat(),
        "source": req.source,
    })
    redis_client.raw.publish("market:ticks", tick_payload)

    return {"status": "ok", "scrip": req.scrip.upper()}


@app.post("/ingest/ticks", status_code=200)
def ingest_ticks(ticks: list[TickIngestRequest], request: Request) -> dict:
    """Batch ingest — one HTTP call for a full tick round (all scrips at once).

    Same logic as /ingest/tick but accepts an array, runs all DB writes in one
    pass, and publishes all Redis events after the writes complete.
    Reduces HTTP overhead from N req/round to 1 req/round.
    """
    if not ticks:
        return {"status": "ok", "count": 0}

    pg: PostgresClient = request.app.state.pg
    redis_client: RedisClient = request.app.state.redis
    now = datetime.now(timezone.utc)
    payloads: list[str] = []

    for req in ticks:
        scrip = req.scrip.upper()
        pg.execute(
            """
            INSERT INTO live_quotes
                (scrip, price, open, high, low, volume, turnover,
                 change_abs, change_pct, prev_close, tick_at, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (scrip) DO UPDATE SET
                price      = EXCLUDED.price,
                open       = EXCLUDED.open,
                high       = EXCLUDED.high,
                low        = EXCLUDED.low,
                volume     = EXCLUDED.volume,
                turnover   = EXCLUDED.turnover,
                change_abs = EXCLUDED.change_abs,
                change_pct = EXCLUDED.change_pct,
                prev_close = EXCLUDED.prev_close,
                tick_at    = EXCLUDED.tick_at,
                source     = EXCLUDED.source
            """,
            (scrip, req.price, req.open, req.high, req.low,
             req.volume, req.turnover, req.change_abs, req.change_pct,
             req.prev_close, now, req.source),
        )
        pg.execute(
            "INSERT INTO tick_history (scrip, price, volume, tick_at, source) VALUES (%s, %s, %s, %s, %s)",
            (scrip, req.price, req.volume, now, req.source),
        )
        payloads.append(json.dumps({
            "scrip": scrip, "price": req.price,
            "open": req.open, "high": req.high, "low": req.low,
            "volume": req.volume, "turnover": req.turnover,
            "change_abs": req.change_abs, "change_pct": req.change_pct,
            "prev_close": req.prev_close, "tick_at": now.isoformat(),
            "source": req.source,
        }))

    for payload in payloads:
        redis_client.raw.publish("market:ticks", payload)

    return {"status": "ok", "count": len(ticks)}


@app.get("/stream/market")
async def stream_market(request: Request, scrips: str = "") -> StreamingResponse:
    """Server-Sent Events stream of live market ticks.

    Query param: scrips=NABIL,EBL,NIMB (comma-separated). Omit for all scrips.

    Events:
      data: {"scrip": "NABIL", "price": 1240.0, ...}
      data: {"type": "ping"}   — keepalive every 15 s
    """
    wanted: set[str] = {s.strip().upper() for s in scrips.split(",") if s.strip()} if scrips else set()

    async def generate():
        redis_pub: aioredis.Redis = request.app.state.redis_pub
        pubsub = redis_pub.pubsub()
        await pubsub.subscribe("market:ticks")
        try:
            ping_task = asyncio.create_task(asyncio.sleep(15))
            listen_task = asyncio.create_task(pubsub.get_message(ignore_subscribe_messages=True, timeout=15))

            while True:
                if await request.is_disconnected():
                    break

                done, _ = await asyncio.wait(
                    [ping_task, listen_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if ping_task in done:
                    yield "data: {\"type\": \"ping\"}\n\n"
                    ping_task = asyncio.create_task(asyncio.sleep(15))

                if listen_task in done:
                    msg = listen_task.result()
                    if msg and msg.get("data"):
                        data = msg["data"]
                        if not wanted or json.loads(data).get("scrip") in wanted:
                            yield f"data: {data}\n\n"
                    listen_task = asyncio.create_task(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                    )

        except asyncio.CancelledError:
            pass
        finally:
            ping_task.cancel()
            listen_task.cancel()
            await pubsub.unsubscribe("market:ticks")
            await pubsub.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------- CLI entrypoint
def main() -> None:
    """Entry for `nrc-serve` script."""
    import uvicorn

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quieten noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)

    host = os.getenv("NRC_HOST", "127.0.0.1")
    port = int(os.getenv("NRC_PORT", "8080"))
    _log.info("starting nrc-serve  host=%s  port=%d  log_level=%s", host, port, log_level)
    uvicorn.run(
        "nrc_orchestrator.server:app",
        host=host, port=port,
        log_level=log_level.lower(),
        log_config=None,  # use our basicConfig, not uvicorn's default
    )


if __name__ == "__main__":
    main()
