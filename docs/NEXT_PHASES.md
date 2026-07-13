# NEPSE Research Copilot — Roadmap

*Last updated: 2026-04-21. Audience: engineering + stakeholders.*

---

## Where we are (Phase 0 — Prototype delivered)

A working end-to-end research copilot with real data, real LLM, production-deployable
architecture. 14 packages, 89 tests, full pipeline < 30 seconds, sub-3 ms point lookups.

**Stack:** Delta Lake on MinIO → Silver/Gold transforms via DuckDB → Postgres serving
→ 10-tool deterministic library → Vertex Gemini agent loop → FastAPI + Streamlit UI.

**Demonstrated:**
- Full EOD pipeline: scraped CSVs → Bronze → Silver (contract-validated) → Gold (decision tables) → Postgres serving
- 10 deterministic tools the LLM can call (`get_quote`, `get_fundamentals`, `get_technicals`, `get_valuation`, `stage2_bank_screen`, …)
- Intent tier (Flash-Lite) gates off-topic queries before Pro is invoked
- Agent loop with parallel tool-use, retries, error wrapping
- Full audit trail in `query_traces` (every tool call, token count, latency, model)
- Streamlit UI showing answer + tool trace + token usage per query

**What it can't do yet** — enumerated below as the next phases, in priority order.

---

## Phase 1 — Production-hardening (2–3 weeks)

**Goal:** the research team uses it daily without breaking anything.

### 1.1  Real GCP deployment (must-do)
- Create a dedicated GCP project (not the auto-created `gen-lang-client-*`)
- Attach a billing account with budget alerts at 50% / 80% / 100%
- Create service accounts: `nrc-orchestrator-sa` (read-only Vertex + secrets),
  `nrc-pipeline-sa` (read/write Postgres + MinIO, no LLM access)
- Move Postgres + MinIO + Redis to Cloud SQL + GCS + Memorystore (or keep self-hosted
  on a single VM if cost matters — lakehouse is ~10 GB)
- Deploy the orchestrator to Cloud Run using the existing `infra/cloud-run/orchestrator.yaml`
- Put the API key in Secret Manager (rotate every 90 days with `gcloud secrets versions add`)
- Front with an HTTPS load balancer + Identity-Aware Proxy (IAP) so only the research
  team's Google accounts reach `/chat`

### 1.2  Auth + rate limiting
- IAP handles authn (Google SSO); propagate the user email as `x-goog-authenticated-user-email`
  into the request, use it as `user_id` on the trace
- Redis-backed per-user rate limiter: 30 req/minute, 500 req/day (we already have `RedisClient`)
- Config-driven — override per-user via `query_traces` table (power users get higher limits)

### 1.3  Scraper scheduling
- Wire the existing Sharesansar scrapers as the first task in `bronze_flow`
- Schedule via Prefect deployment: `daily_eod_flow` runs every weekday at 17:00 NPT
  (post-NEPSE close + margin for scrape)
- Failure alerts to Slack via Prefect's notification hooks

### 1.4  Streaming answers
- Swap `/chat` to SSE: stream Gemini tokens as they arrive during the synthesis turn
- Keep tool-use turns non-streaming (they're atomic — all tools or nothing)
- Streamlit 1.36+ has native `st.write_stream()` that consumes SSE directly

### 1.5  Observability
- Structured JSON logs → Cloud Logging (already Cloud-Logging-compatible, just enable)
- OpenTelemetry tracing: one span per `/chat` request, child spans per tool call
- Cloud Monitoring dashboard: p50/p95/p99 latency, error rate, token spend per user, daily pipeline success
- Alerts: pipeline fails, error rate > 5%, any single query > 60s, daily token spend > $X

---

## Phase 2 — Answer quality (4–6 weeks)

**Goal:** the answers are not just accurate but useful. Measured via offline evaluation.

### 2.1  Evaluation harness
- Curated golden set of 50–100 (question, expected_facts, expected_tools) triples
  — split across easy (single-tool), medium (multi-tool), hard (comparative / reasoning)
- Nightly CI run: replay all questions, score on (a) which tools called, (b) fact
  recall, (c) hallucination detection (LLM-as-judge on "is every number in the answer
  present in the tool output?")
- Track metrics over time in a dashboard so model / prompt regressions are visible

### 2.2  Prompt + tool refinement
- Stage 2 tool description is currently 40 lines explaining percentile directionality —
  simplify by renaming fields: `npl_percentile` → `npl_rank` (1 = best) across the whole
  contract chain. Contract change, so fan out through Silver + Postgres
- Add `get_news_details(article_id)` — fetch body + embedding on demand (right now news
  returns title only; body retrieval is a stubbed future-hook in the contract)
- Add `compare_scrips(scrips: list, metrics: list)` as a first-class tool — the model
  currently does N parallel `get_fundamentals` calls; one dedicated tool is faster and
  cheaper

### 2.3  Claude on Vertex (synthesis tier)
- Create a Vertex service account (API keys can't reach Claude partner models)
- Enable Claude Opus 4.7 + Sonnet 4.6 in Vertex Model Garden (one-time Anthropic terms acceptance)
- Implement `ClaudeVertexClient` in `nrc-llm` (same `LLMClient` protocol — one file)
- Swap `LLMRouter.synthesizer()` to return Claude via env var `LLM_SYNTHESIZER_MODEL=claude-opus-4-7`
- A/B on the eval harness: pick whichever wins on fact recall + hallucination rate

### 2.4  News semantic search
- News embeddings table (pgvector + BGE-M3) — already scaffolded in `nrc-embeddings`
  — wire to the existing `libs/embeddings` package
- Add `search_news_semantic(query, limit)` tool — "what news mattered to commercial
  banks this month?" type questions
- Body-fetching pipeline: per-URL `httpx` fetch → extract → embed → upsert — run after
  `bronze.news_raw` is updated

### 2.5  Bank-specific fundamentals expansion
- Map 10 more Sharesansar metrics into canonical snapshot fields (currently 15 / ~85
  raw metrics mapped). Candidates: Interest Spread, Cost of Funds, Base Rate,
  Tier-1 CAR, CET-1 CAR. Bronze already has them; Silver just needs the `METRIC_MAP`
  entry + contract field
- Multi-quarter fundamentals → revenue-growth-score in Stage 1 becomes real (currently
  a placeholder = 0)

---

## Phase 3 — Beyond Commercial Banks (6–10 weeks)

**Goal:** same system covers Development Banks, Microfinance, Hydropower, Insurance.

### 3.1  Sector-agnostic fundamentals
- Hydropower financials are structurally different (no NPL, no CAR — but plant capacity
  factor, tariff escalation). Refactor `FundamentalSnapshot` into a base + sector-specific
  extension tables: `silver.fundamentals_banks`, `silver.fundamentals_hydro`, etc.
- New tools per sector: `stage2_hydro_screen`, `stage2_insurance_screen`
- Keep Commercial Banks on the critical path — other sectors load incrementally

### 3.2  Scraper expansion
- Hydropower scripts on Sharesansar (BARUN, CHCL, UPPER, etc.)
- Development Banks + Microfinance are less liquid — lower priority
- Insurance (LI-prefix for life, NL-prefix for non-life) has different reporting periods

### 3.3  Corporate action adjustments
- `silver.prices_adjusted`: apply bonus/rights/split factors retroactively so
  technicals are consistent across ex-dates
- Cross-sector corporate actions differ (rights issues more common in banks; power
  purchase agreements unique to hydro)

---

## Phase 4 — On-prem DGX Spark migration (timing: TBD, capability ready day-one)

**Why now:** compliance / data-locality requirements will push the whole stack on-prem
eventually. The codebase was designed for this — the migration should take days not months.

### 4.1  What doesn't change
- `nrc_contracts` — Pydantic schemas are pure data, portable anywhere
- `nrc_tools` — all 10 tools query Postgres, which moves on-prem trivially
- `nrc_orchestrator` — runs anywhere as a container
- Silver/Gold SQL — DuckDB and Spark speak the same dialect for what we use

### 4.2  What changes (three files)
- `libs/compute/nrc_compute/spark_engine.py` — stub becomes real (~200 lines of
  `SparkSession.builder...` + `df.writeStream...`)
- `libs/llm/nrc_llm/vertex_gemini.py` — replace with `vllm_client.py` or
  on-prem Ollama client. Same `LLMClient` protocol, same behavior
- `libs/storage/nrc_storage/config.py` — flip endpoints to on-prem equivalents
  (MinIO runs identically on DGX)

### 4.3  Data migration
- Delta tables replicate cleanly: `mc mirror` (MinIO → MinIO) or
  `aws s3 sync` (GCS → MinIO). Delta's transaction log follows
- Postgres: `pg_dump | pg_restore` on a snapshot; zero-downtime with logical replication
  if needed
- News embeddings in pgvector migrate as a normal table

### 4.4  LLM choice on DGX
- Llama 3.1 70B Instruct or Qwen 2.5 72B for synthesis (A100/H100 inference via vLLM)
- BGE-M3 for embeddings (already the planned embedder)
- Smaller model (Phi-4, Llama 3.1 8B) for intent tier — fits on a fraction of one GPU

---

## Phase 5 — Advanced agent capabilities (future)

### 5.1  Multi-turn reasoning
- Current: one question → one answer
- Next: "show me NABIL's valuation" → "now compare to EBL" → "which is cheaper per unit of ROE?"
  The `session_id` is already wired; just need to load last N turns as conversation history

### 5.2  Proactive monitoring / alerts
- "Tell me when NABIL's RSI crosses 70" / "Alert when any bank gets a new NPL_HIGH flag"
- Scheduled Prefect flow that re-runs stored queries against new data, emits to Slack

### 5.3  Report generation
- "Generate a weekly sector report" — chain 20 tool calls, produce a multi-section
  PDF with charts (Matplotlib → base64 → PDF via ReportLab)

### 5.4  Portfolio-aware queries
- Upload a portfolio CSV → "how is my portfolio doing? which holdings flag risk?"
  — portfolio table in Postgres + new tool `analyze_portfolio(positions)`

---

## Rough cost envelope (Phase 1 steady state)

- Vertex Gemini 2.5 Pro: ~$1.50 / 1M input tokens, $10 / 1M output. At 100 queries/day
  averaging 3k input + 200 output tokens → ~$0.50/day = **$15/month**
- Gemini 2.5 Flash-Lite (intent tier): negligible (~$0.10/month at same volume)
- Cloud Run: 1 GB / 1 CPU, scale-to-zero → **$5–15/month** for a low-traffic internal tool
- Cloud SQL (Postgres): `db-g1-small` (1.7 GB RAM) → **$25/month**
- GCS (lakehouse, ~20 GB): **$0.50/month**
- Memorystore Redis (1 GB): **$35/month** — optional, could self-host if cost matters
- IAP + Load Balancer: **$20/month**
- **Total: ~$100/month** for 1-10 researchers, scales linearly with LLM usage

---

## Decisions log (why things are the way they are)

| Decision | Why | Reversible? |
|---|---|---|
| Delta Lake over Iceberg | `delta-rs` is mature + no catalog service needed | Yes — switch the `DeltaIO` internals |
| DuckDB for compute | Embedded, zero-ops, matches Spark dialect | Yes — `ComputeEngine` protocol |
| Vertex API key (not service account) | User's starting creds; fastest path | Yes, planned for Phase 2 (Claude needs it) |
| Gemini over Claude for synthesis | User's API key only supports Gemini today | Yes — swap via `LLMRouter` env var |
| Single Postgres for serving + traces | Small team; one DB is simpler than two | Yes, but why? |
| Streamlit for UI | Demo-fast; not prod-quality UX | Replace with Next.js in Phase 2 if team wants richer UI |
| API key in `.env` file (local) | Fastest path for single-dev prototype | Secret Manager in Phase 1 deploy |

---

## Exit criteria per phase

- **Phase 1 done when:** (a) running on Cloud Run behind IAP, (b) 10 internal users
  can hit it without shared credentials, (c) daily pipeline runs unattended for 1 week,
  (d) rate limits + budget alerts proven by triggering them in staging.
- **Phase 2 done when:** eval harness scores ≥ 0.85 on fact-recall and ≤ 0.05 on
  hallucination across the golden set, for 2 consecutive weekly runs.
- **Phase 3 done when:** same eval set — plus hydro/microfinance subsets — passes
  the same thresholds, and the system handles a question that spans sectors.
- **Phase 4 done when:** all queries pass on-prem with identical results to the
  GCP deployment; migration runbook tested by someone other than the author.
