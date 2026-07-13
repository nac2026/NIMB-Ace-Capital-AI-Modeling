# NEPSE Research Copilot

Internal LLM-powered research tool for NEPSE Commercial Banks.
Ask questions in plain English — prices, fundamentals, peer comparisons, risk screens — and get answers grounded in the serving database with a full tool-use audit trail.

**Scope (prototype):** 19 active Commercial Bank scrips, EOD data, single-user.

---

## Table of contents

1. [Architecture overview](#architecture-overview)
2. [Repository layout](#repository-layout)
3. [Prerequisites](#prerequisites)
4. [First-time setup](#first-time-setup)
5. [Step 1 — Environment variables](#step-1--environment-variables)
6. [Step 2 — Start Docker infrastructure](#step-2--start-docker-infrastructure)
7. [Step 3 — Start the backend (FastAPI)](#step-3--start-the-backend-fastapi)
8. [Step 4 — Start the frontend (Next.js)](#step-4--start-the-frontend-nextjs)
9. [Step 5 — Verify everything is working](#step-5--verify-everything-is-working)
10. [Running the data pipeline](#running-the-data-pipeline)
11. [Running tests](#running-tests)
12. [Port reference](#port-reference)
13. [Common commands](#common-commands)
14. [Troubleshooting](#troubleshooting)

---

## Architecture overview

```
Browser (localhost:3000)
        │
        ▼
  Next.js frontend
  services/web/
        │  REST
        ▼
  FastAPI backend (localhost:8080)
  services/orchestrator/
        │
        ├── Intent classifier  ──► Vertex AI (Gemini Flash-Lite)
        ├── Agent loop         ──► Vertex AI (Gemini Flash)
        ├── Tool layer         ──► Postgres (serving queries)
        ├── Conversation memory ► Redis
        └── Trace writer       ──► Postgres (audit log)

Infrastructure (Docker)
  ├── MinIO      :9000 / :9001  — Delta Lake object store
  ├── Postgres   :5432          — Serving DB + pgvector
  └── Redis      :6379          — Session memory cache

Data pipeline (orchestrated by Dagster on localhost:3001)
  services/pipelines/   — Dagster assets + jobs + schedules (single UI)
       │
       ├─► client CSVs (OneDrive)
       │        client-docs/OneDrive_*/           [primary source]
       │   ↓
       ├─► Bronze Delta tables on MinIO
       │        services/ingestion/               [Python — file parsing]
       │   ↓
       ├─► Silver Delta tables
       │        services/processing/              [Python — tier-dedup,
       │                                           Pydantic validation]
       │   ↓
       ├─► Gold Parquet tables on MinIO
       │        dbt/models/gold/                  [dbt SQL — indicators,
       │                                           rankings, screens,
       │                                           valuation, ratios]
       │   ↓
       └─► Postgres serving layer (LLM tool layer reads from here)
```

Python owns ingestion + Silver (Pydantic contracts, ticker canonicalization,
source-tier precedence — all things SQL can't do idiomatically). **dbt
owns the Gold layer** (declarative SQL, ref-based lineage, column-level
docs, schema tests). `dagster-dbt` renders dbt models as Dagster assets so
the lineage graph still shows the whole chain in one UI.

---

## Repository layout

```
NRC/
├── libs/
│   ├── contracts/        # Shared Pydantic schemas
│   ├── compute/          # DuckDB (local) / Spark (prod) abstraction
│   ├── storage/          # MinIO + Delta + Postgres + Redis clients
│   ├── llm/              # Vertex AI Gemini client
│   ├── embeddings/       # Embedding provider abstraction
│   ├── nepal/            # Bikram Sambat calendar utils
│   └── observability/    # structlog + OpenTelemetry
├── dbt/                   # dbt project — Gold-layer analytics (SQL models, tests, docs)
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── gold/          # indicators, peer rankings, screens, valuation
│   │   └── sources/       # Silver tables declared as dbt sources
│   └── macros/            # source_tier_rank, gold_external_location
├── services/
│   ├── ingestion/         # Source adapters: client CSV + Sharesansar scraper → Bronze
│   ├── processing/        # Bronze → Silver transforms + Postgres sync (Python)
│   ├── pipelines/         # Dagster orchestration — assets, jobs, schedules (UI :3001)
│   ├── tools/             # LLM tool implementations (get_quote, get_fundamentals, …)
│   ├── orchestrator/      # FastAPI + LLM agent loop (chat backend, :8080)
│   └── web/               # Next.js 16 chat frontend (:3000)
├── scrapers/             # Sharesansar scraper (stand-alone)
├── tests/                # unit/ + integration/
├── infra/                # Postgres init SQL, Cloud Run config
├── scripts/              # verify_infra.py and other one-shots
├── docs/                 # Architecture and development plan
├── docker-compose.yml    # MinIO + Postgres + Redis
├── pyproject.toml        # uv workspace root
├── Makefile              # Developer shortcuts
└── .env.example          # Environment variable template
```

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker Desktop | 4.x+ | https://www.docker.com/products/docker-desktop |
| Docker Compose | v2 (bundled with Docker Desktop) | — |
| Python | 3.12 | https://www.python.org/downloads/ |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20+ | https://nodejs.org |
| npm | 10+ | bundled with Node |
| git | any | https://git-scm.com |

Check your versions:

```bash
docker --version          # Docker version 24+
docker compose version    # Docker Compose version v2+
python --version          # Python 3.12.x
uv --version              # uv 0.x
node --version            # v20+
npm --version             # 10+
```

---

## First-time setup

### Clone the repository

```bash
git clone git@github.com:YarshaLabs/nep-trade-analytics.git
cd nep-trade-analytics
git checkout dev
```

---

## Step 1 — Environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and fill in the required fields:

```bash
# MinIO — leave defaults for local dev
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Postgres — leave defaults for local dev
POSTGRES_USER=nepse
POSTGRES_PASSWORD=nepse
POSTGRES_DB=nepse
POSTGRES_URL=postgresql://nepse:nepse@localhost:5432/nepse

# Redis — leave default for local dev
REDIS_URL=redis://localhost:6379/0

# --- REQUIRED: Vertex AI (for the LLM to work) ---
# Get a key: GCP Console → APIs & Services → Credentials → Create API Key
# Make sure "Vertex AI API" is enabled on the project.
GCP_VERTEX_API_KEY=your-key-here
GCP_PROJECT_ID=your-gcp-project-id
GCP_REGION=global

# LLM models (defaults are fine)
LLM_INTENT_MODEL=gemini-2.5-flash-lite
LLM_SYNTHESIZER_MODEL=gemini-2.5-flash
```

> **Never commit `.env`** — it is gitignored. The API key grants access to Vertex AI billing.

---

## Step 2 — Start Docker infrastructure

The Docker Compose file starts three services: **MinIO** (object store), **Postgres** (serving DB), and **Redis** (session cache).

### Start all containers

```bash
docker compose up -d
```

Or using make:

```bash
make up
```

### What happens on first start

- MinIO starts and the `minio-setup` sidecar automatically creates two buckets:
  - `nepse-lakehouse` — Delta Lake tables
  - `raw-snapshots` — raw scraper output
- Postgres starts and runs `infra/postgres/init.sql` to create the schema and enable `pgvector`.
- Redis starts with AOF persistence and a 200 MB memory limit.

### Check that everything is healthy

```bash
docker compose ps
```

Expected output — all services should show `healthy` or `Up`:

```
NAME               STATUS
nrc_minio          Up (healthy)
nrc_minio_setup    Exited (0)    ← one-shot, exits after creating buckets
nrc_postgres       Up (healthy)
nrc_redis          Up (healthy)
```

### Verify connectivity from Python

```bash
make verify
# or:
uv run python scripts/verify_infra.py
```

### Access the MinIO web console

Open `http://localhost:9001` in your browser.

- Username: `minioadmin`
- Password: `minioadmin`

---

## Step 3 — Start the backend (FastAPI)

The backend is a FastAPI app that wraps the LLM agent loop.

### Install Python dependencies (first time only)

```bash
uv sync
```

This installs all workspace packages (libs + services) into a shared `.venv` at the repo root.

### Start the API server

```bash
uv run nrc-serve
```

The server starts on `http://localhost:8080`.

You should see:

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     orchestrator ready
INFO:     Uvicorn running on http://127.0.0.1:8080
```

### Verify the backend

```bash
# Liveness
curl http://localhost:8080/health
# → {"status":"ok"}

# Readiness (checks Postgres connectivity)
curl http://localhost:8080/ready
# → {"status":"ok","checks":{"postgres":true}}

# Test a chat message
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "List all available bank scrips", "session_id": "test-1"}'
```

### Available API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Readiness probe (checks Postgres) |
| `POST` | `/chat` | Send a question, get an answer |
| `DELETE` | `/chat/session/{id}` | Clear conversation memory for a session |
| `GET` | `/api/universe` | All 19 bank scrips with latest metrics |
| `GET` | `/api/indices` | NEPSE + Banking index history |
| `GET` | `/api/stage2` | Stage-2 health-screened banks |
| `GET` | `/api/prices/{scrip}` | EOD price history for one scrip |

Interactive API docs (Swagger): `http://localhost:8080/docs`

---

## Step 4 — Start the frontend (Next.js)

The frontend is a Next.js 16 app inside `services/web/`.

### Install Node dependencies (first time only)

```bash
cd services/web
npm install
```

### Start the dev server

```bash
npm run dev
```

The frontend starts on `http://localhost:3000` and automatically opens in your browser.

You should see:

```
  ▲ Next.js 16.x
  - Local: http://localhost:3000
  - Ready in 1.2s
```

Open `http://localhost:3000` — it redirects to `/chat`.

### What the UI does

- **Left sidebar** — conversation history, grouped by date. New chat, delete individual conversations, clear all.
- **Chat area** — type a question and hit Enter. Answers are streamed back as Markdown.
- **Trace panel** — click the small metadata line under each answer to see which tools were called, latency, and token counts.

---

## Step 5 — Verify everything is working

With Docker, backend, and frontend all running:

1. Open `http://localhost:3000`
2. Click one of the suggestion cards, e.g. **"List the top 5 banks by composite health score."**
3. You should see a typing indicator, then a formatted answer appear.
4. Click the small trace line underneath to confirm tool calls are shown (e.g. `stage2_bank_screen`).

**Full stack health checklist:**

| Check | Expected |
|-------|----------|
| `docker compose ps` | minio, postgres, redis all `healthy` |
| `curl localhost:8080/health` | `{"status":"ok"}` |
| `curl localhost:8080/ready` | `{"status":"ok","checks":{"postgres":true}}` |
| `http://localhost:3000` | Chat UI loads |
| Send a message | Answer appears with trace metadata |

---

## Data sources — tier hierarchy

The lakehouse now has **four explicit data-source tiers**. When multiple
sources cover the same (scrip, period, metric) key, Silver-layer dedup
picks the winner via this ranking:

| Tier | Slug | Who writes it | Example source | Precedence |
|------|------|---------------|---------|--------------:|
| 1 | `client_authoritative` | Hand-curated tidy client dump | Shreyas `CB Data by Shreyas/*.csv` | wins |
| 2 | `client_historical` | Long-range historical client backfill | Format B `Commercial bank/**/<TICKER>.csv` | |
| 3 | `live_api` | NEPSE API (future) | — | |
| 4 | `scraped` | Sharesansar HTML scrape | `scrapers/sharesansar/*` | loses |

**Primary ingestion = client CSV dumps.** Scraping is demoted to a manual,
opt-in fallback — it never runs automatically as part of the default flow.
When the client sends an updated CSV, client-authoritative rows immediately
overwrite both historical and scraped rows for the quarters they cover.

Every Bronze row carries a `source` slug and `source_tier` enum value, and
multiple sources safely coexist in the same Bronze table via delta-rs
predicate-based partition overwrite (`DeltaIO.upsert_source_partition`).

## Running the data pipeline

**The orchestrator is Dagster.** Every Bronze/Silver/Gold table is a named
asset with declared lineage; the Dagster UI renders the dependency graph
and shows materialization state per asset. Local dev UI lives on
`http://localhost:3001`.

Three jobs are pre-defined:

| Job | What it runs | When to use |
|---|---|---|
| `daily_eod_job` | client CSV → Silver → Gold → Postgres sync | Primary daily refresh. Scheduled at 20:00 NPT (disabled by default). |
| `manual_scrape_job` | Sharesansar scraper → scraper Silver/Gold | Opt-in fallback when client CSVs are stale or out of universe. Never scheduled. |
| `postgres_sync_job` | Gold → Postgres only | Fast re-sync when the lakehouse is fresh but serving tables drifted. |

### Launch the Dagster UI

```bash
make dagster-dev            # uv run dagster dev -m nrc_pipelines --port 3001
```

Open `http://localhost:3001`. The **Assets** tab shows the full lineage
graph (Bronze → Silver → Gold → Postgres). Click any asset to see its
latest materialization, metadata (row counts, Delta version, duration),
and logs. Click any job to run it.

### Running jobs from the CLI

```bash
make dagster-eod            # runs daily_eod_job end-to-end (client CSV → Postgres)
make dagster-scrape         # runs manual_scrape_job (opt-in scraper)
make dagster-sync           # runs postgres_sync_job (Postgres-only re-sync)
```

First-time bootstrap requires `make dagster-scrape` once to populate
`bronze.scrip_master_raw` (the only source for the universe master).
After that, `make dagster-eod` is self-sufficient indefinitely.

### Standalone CLIs (still available — Dagster wraps these)

```bash
# Ingestion — what Dagster calls under the hood
uv run nrc-ingest all                       # all 3 client adapters
uv run nrc-ingest shreyas                   # CLIENT_AUTHORITATIVE
uv run nrc-ingest format-b                  # CLIENT_HISTORICAL
uv run nrc-ingest format-b-prices

# Scraper fallback (manual, never automatic)
uv run nrc-scrape all                       # all 6 scraper adapters
uv run nrc-scrape prices
uv run nrc-scrape scrip-master
# etc.

# Silver transforms (bypass Dagster if needed)
uv run nrc-process silver-all
uv run nrc-process sync-postgres

# Gold models (all dbt now)
make dbt-build                              # dbt run + dbt test on all Gold models
cd dbt && dbt run --select valuation        # one model only
cd dbt && dbt test                          # just run tests
```

Use the Dagster UI during active development (lineage, re-runs, logs all
in one place). Use the CLIs for scripted CI jobs or quick iteration on
a single transform.

### Verify data in Postgres

```bash
curl http://localhost:8080/api/universe | python3 -m json.tool | head -40
```

---

## Adding a new Gold analytic (dbt)

Use this flow whenever you want a new metric, screen, or derived table
over Silver data — e.g. DuPont decomposition, Piotroski F-Score,
cash-flow quality, expanded ratio library, speculation composite score.
dbt is the authoring surface; Dagster picks it up automatically.

1. **Write the SQL model.** Create `dbt/models/gold/<name>.sql`:

    ```sql
    {{ config(location=gold_external_location(),
              description='One-line summary of the output.') }}

    select
        fs.scrip,
        fs.fiscal_year_bs,
        fs.quarter,
        -- your metric math here, using canonical Silver columns
        fs.net_profit * 1.0 / nullif(fs.shareholders_equity, 0) as roe_computed
    from {{ source('silver', 'fundamentals_snapshots') }} fs
    join {{ source('silver', 'scrip_master') }} sm using (scrip)
    where sm.is_active
    ```

   Use `{{ source('silver', <table>) }}` to read Silver — that registers
   the upstream dep so dagster-dbt draws the correct lineage edge.

2. **Describe columns + add tests.** Append a block to
   `dbt/models/gold/schema.yml`:

    ```yaml
    - name: <name>
      description: What this table is and who consumes it.
      columns:
        - name: scrip
          data_tests: [not_null]
        - name: roe_computed
          data_tests:
            - dbt_utils.accepted_range: {min_value: -1, max_value: 5}
      data_tests:
        - dbt_utils.unique_combination_of_columns:
            combination_of_columns: [scrip, fiscal_year_bs, quarter]
    ```

3. **Regenerate the dbt manifest + run.**

    ```bash
    make dbt-parse              # dagster-dbt needs this to see the new model
    make dbt-build              # run the model + run its tests
    make dbt-docs               # (optional) serve docs on :8081
    ```

4. **Wire into Dagster job selection.** If the new model should run in
   `daily_eod_job` (client-data-driven), add its AssetKey to
   `_DAILY_EOD_KEYS` in
   `services/pipelines/nrc_pipelines/jobs.py`:

    ```python
    ["gold", "<name>"],
    ```

   Same for `_MANUAL_SCRAPE_KEYS` if it depends on scraper-only Silver
   data (e.g. silver.prices). Dagster auto-discovers the dbt asset on
   next boot — no code in `nrc_pipelines` needs to touch the dbt model
   itself.

5. **Verify the full pipeline.** `make dagster-eod` runs the whole chain.
   The Dagster UI at `:3001` shows the new asset in the lineage graph
   with its test results as AssetCheck pills.

**Rules of thumb — Python vs dbt.** Stay in Python for anything that
validates row-by-row against a Pydantic contract, parses files, maps
ticker aliases, or needs imperative control flow. Everything else —
ratios, rankings, screens, peer medians, time-series aggregations —
belongs in dbt. If you're about to write a SQL string inside a `.py`
file, it's a dbt model.

---

## Running tests

### Unit tests (no Docker needed)

```bash
uv run pytest tests/unit/ -v
```

### Integration tests (Docker must be running)

```bash
uv run pytest tests/integration/ -v
```

### All tests

```bash
make test
# or:
uv run pytest -v
```

### Lint and format

```bash
make lint    # ruff check
make fmt     # ruff format (auto-fix)
```

---

## Port reference

| Port | Service | URL |
|------|---------|-----|
| `3000` | Next.js frontend | http://localhost:3000 |
| `3001` | Dagster UI (data pipeline orchestrator) | http://localhost:3001 |
| `8080` | FastAPI backend (chat) | http://localhost:8080 |
| `8080/docs` | Swagger UI | http://localhost:8080/docs |
| `5432` | Postgres | `postgresql://nepse:nepse@localhost:5432/nepse` |
| `6379` | Redis | `redis://localhost:6379/0` |
| `9000` | MinIO S3 API | http://localhost:9000 |
| `9001` | MinIO Web Console | http://localhost:9001 |

---

## Common commands

```bash
# --- Infrastructure ---
make up           # start Docker containers
make down         # stop containers (keeps data)
make restart      # restart all containers
make logs         # tail all container logs
make ps           # show container status
make clean        # DESTRUCTIVE: stop + delete all data volumes

# --- Python ---
uv sync           # install / update all Python deps
uv run nrc-serve  # start FastAPI backend on :8080
uv run nrc-ask "How is NABIL doing?"   # one-shot CLI query
uv run nrc-ingest all                  # ingest client CSV dumps to Bronze (primary path)
uv run nrc-scrape all                  # OPTIONAL fallback: run Sharesansar scrapers
uv run nrc-process silver-all          # Bronze → Silver
uv run nrc-process gold-all            # Silver → Gold
uv run nrc-process sync-postgres       # Gold → Postgres

# --- Frontend ---
cd services/web && npm install         # install Node deps (first time)
cd services/web && npm run dev         # start Next.js on :3000
cd services/web && npm run build       # production build
cd services/web && npm run start       # serve production build

# --- Tests & quality ---
make test         # run all pytest tests
make lint         # ruff check
make fmt          # ruff format
make check        # lint + test
make verify       # verify infra connectivity
```

---

## Troubleshooting

### Docker containers not starting

```bash
docker compose logs minio     # check MinIO logs
docker compose logs postgres  # check Postgres logs
```

Make sure ports `5432`, `6379`, `9000`, `9001` are not already in use:

```bash
lsof -i :5432 -i :6379 -i :9000 -i :9001
```

### Backend fails to connect to Postgres

Check your `.env` has `POSTGRES_URL=postgresql://nepse:nepse@localhost:5432/nepse` and that Postgres is healthy:

```bash
docker compose ps postgres
```

### "GCP_VERTEX_API_KEY not set" error

You need a Vertex AI API key in `.env`. The LLM will not work without it:

1. Go to [GCP Console](https://console.cloud.google.com) → **APIs & Services → Credentials**
2. Click **Create credentials → API key**
3. Enable **Vertex AI API** on your project
4. Add the key to `.env` as `GCP_VERTEX_API_KEY=...`

### Backend returns 429 errors (quota exceeded)

The free-tier Vertex quota is low. Either:
- Attach billing to your GCP project (recommended), or
- Wait a minute and retry — the client retries with exponential backoff

### Frontend shows blank / error page

Make sure the backend is running on `:8080`. The frontend proxies API calls to `NEXT_PUBLIC_BACKEND_URL` (defaults to `http://localhost:8080`).

### Resetting everything from scratch

```bash
make clean                                        # wipe all Docker volumes
make up                                           # fresh start
uv run nrc-ingest all                             # reload client CSV data
uv run nrc-process silver-all                     # rebuild Silver
uv run nrc-process gold-all                       # rebuild Gold
uv run nrc-process apply-schema && uv run nrc-process sync-postgres
```

---

## Environment variable reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIO_ENDPOINT` | `http://localhost:9000` | MinIO S3 API URL |
| `MINIO_ROOT_USER` | `minioadmin` | MinIO admin username |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | MinIO admin password |
| `MINIO_BUCKET_LAKEHOUSE` | `nepse-lakehouse` | Delta Lake bucket name |
| `MINIO_BUCKET_SNAPSHOTS` | `raw-snapshots` | Raw snapshot bucket name |
| `POSTGRES_URL` | `postgresql://nepse:nepse@localhost:5432/nepse` | Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `COMPUTE_ENGINE` | `duckdb` | `duckdb` (local) or `spark` (prod) |
| `GCP_VERTEX_API_KEY` | *(required)* | Vertex AI API key |
| `GCP_PROJECT_ID` | *(required)* | GCP project ID |
| `GCP_REGION` | `global` | Vertex AI region |
| `LLM_INTENT_MODEL` | `gemini-2.5-flash-lite` | Model for intent classification |
| `LLM_SYNTHESIZER_MODEL` | `gemini-2.5-flash` | Model for answer synthesis |
| `LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`) |
| `NRC_HOST` | `127.0.0.1` | Backend bind host |
| `NRC_PORT` | `8080` | Backend bind port |
