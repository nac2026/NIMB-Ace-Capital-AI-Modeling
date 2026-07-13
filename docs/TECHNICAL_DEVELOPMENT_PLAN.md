# NEPSE Research Copilot — Technical Development Plan

**Project codename:** `nepse-research-copilot` (internal)
**Document type:** Engineering development specification
**Audience:** Development team + Claude Code (for AI-assisted implementation)
**Status:** Prototype planning, production-stack aligned

---

## 1. Project Overview

### 1.1 Context

A Nepali capital management bank requires an internal research and decision-review platform for their investment team. The system consists of two logical subsystems:

- **System A — Research Copilot:** A chat-based research assistant for traders and analysts to query NEPSE market data, fundamentals, sector screens, technicals, and news without manually pulling charts or reading reports.
- **System B — Order Decision Review:** A post-hoc analysis tool for upper management to evaluate whether trading decisions were justified at the time of placement, based on market conditions, fundamentals, and sentiment.

**This document covers System A (Research Copilot) only.** System B is a separate workstream that will reuse System A's data layer and tool interfaces.

### 1.2 Scope of the prototype

The prototype must:

- Demonstrate the research team's existing multi-stage analysis framework (macro → factor research → Stage 1 screening → Stage 2 screening → valuation → technical overlay), codified as deterministic tools callable by an LLM.
- Cover the **Banks & BFIs** sector only, ~20 scrips, end-of-day data.
- Run on a single 16GB Mac Mini (developer machine) during prototyping.
- Be built on the exact stack that will scale to production on the bank's future NVIDIA DGX Spark hardware with zero architectural rewrites.

### 1.3 Non-goals for prototype

- Real-time tick ingestion (architecture supports it, data flow stubbed with daily batch).
- Multi-sector coverage beyond banks.
- Fine-tuned models (off-the-shelf LLM with tool calling is sufficient).
- Multi-user auth / SSO / role-based access.
- System B (order decision review).
- Predictive modeling of future prices.
- Mobile applications.

---

## 2. Architecture

### 2.1 Guiding principles

1. **Lakehouse from day one.** All historical and analytical data lands in Delta Lake on MinIO. No throwaway SQLite or local-file-only stages.
2. **Same topology, lighter runtime.** Local prototype uses DuckDB + NATS JetStream; production uses Spark + Kafka. Code is identical; compute engine is swapped via abstraction layer.
3. **LLM for language, deterministic code for logic.** Every numerical or factual claim must come from a tool call, never from the model's parametric knowledge. Tools are versioned Python functions with Pydantic schemas.
4. **Decision lineage is first-class.** Every query produces a trace record: intent classification, tool calls made, tool outputs, LLM synthesis, latency, tokens. This is compliance infrastructure, debugging infrastructure, and eval infrastructure simultaneously.
5. **Bronze/Silver/Gold medallion.** Raw scraped data (Bronze) is preserved indefinitely. Silver is cleaned and typed. Gold is analytics-ready materializations served to tools.
6. **No Internet-dependent assumptions in production.** Bank deployment may be air-gapped. All external dependencies (LLM endpoints, data sources) are configured through adapters that can be swapped for on-prem equivalents.

### 2.2 System diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                               │
│  Python scrapers/API clients (orchestrated by Prefect → Dagster)      │
│    Sources: Sharesansar, Merolagani, NEPSE, NRB, news portals         │
│    Future: Broker TMS feed (licensed)                                 │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ publish raw events
                             ▼
                    ┌────────────────┐
                    │  Message Bus   │    Topics:
                    │  NATS (local)  │      raw.prices
                    │  Kafka (prod)  │      raw.fundamentals
                    └───────┬────────┘      raw.news
                            │               raw.macro
                            ▼               raw.corporate_actions
┌───────────────────────────┴──────────────────────────────────────────┐
│                        PROCESSING LAYER                               │
│   Compute engine abstraction (DuckDB local / Spark production)        │
│                                                                        │
│    bronze.* → silver.* → gold.*                                        │
│                                                                        │
│    Jobs:                                                               │
│      • price_normalizer (adjust for splits/bonuses)                   │
│      • fundamental_parser                                              │
│      • indicator_compute (SMA/EMA/RSI/MACD/Bollinger/ATR)              │
│      • peer_ranking                                                    │
│      • stage1_screen_materializer                                      │
│      • stage2_bank_screen_materializer                                 │
│      • valuation_materializer                                          │
│      • news_embedder                                                   │
└──────────────┬────────────────────────────────────┬──────────────────┘
               │                                    │
               ▼                                    ▼
      ┌──────────────────┐                  ┌──────────────────┐
      │   Delta Lake     │                  │   Postgres       │
      │   on MinIO       │                  │   + pgvector     │
      │                  │                  │                  │
      │  Full history,   │                  │  Serving copy of │
      │  audit, ML       │                  │  gold.* + vectors│
      └──────────────────┘                  └────────┬─────────┘
                                                     │
                                            ┌────────▼─────────┐
                                            │      Redis       │
                                            │  Hot cache,      │
                                            │  session state   │
                                            └────────┬─────────┘
                                                     │
┌────────────────────────────────────────────────────┴─────────────────┐
│                     SEMANTIC / TOOL LAYER                             │
│   FastAPI service exposing typed tools:                               │
│     get_quote, get_fundamentals, stage1_screen, stage2_bank_screen,   │
│     valuation, technicals, search_news, macro_snapshot, peer_compare  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     LLM ORCHESTRATION LAYER                           │
│   FastAPI + custom agent loop:                                        │
│     1. Intent classification (small fast model)                       │
│     2. Tool planning                                                   │
│     3. Parallel tool execution                                         │
│     4. Synthesis (larger model)                                        │
│   Semantic cache (Redis) keyed on query embedding                     │
│   Decision lineage writer (Postgres)                                  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js)                                │
│   Streaming chat UI, inline charts (Recharts), stage badges,          │
│   tool trace inspector (dev mode)                                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 Local vs production stack mapping

| Component | Local (Mac Mini 16GB) | Production (DGX Spark, on-prem) |
|---|---|---|
| Container runtime | OrbStack | Docker / Kubernetes |
| Object storage | MinIO (single node) | MinIO cluster or bank-provided S3-compatible |
| Table format | Delta Lake OSS | Delta Lake OSS |
| Compute engine | DuckDB + delta-rs | Apache Spark + delta-spark |
| Message bus | NATS JetStream | Kafka / Redpanda |
| Serving DB | Postgres + pgvector | Postgres + pgvector (HA) |
| Hot cache | Redis | Redis (HA) |
| Orchestrator | Prefect | Dagster (or Prefect at scale) |
| LLM provider | Gemini / Claude API | Local hosted (Llama 3.3 70B / Qwen 2.5) via vLLM on DGX GPU |
| Embedding model | bge-m3 via API or local | bge-m3 local on DGX |
| Frontend | Next.js dev server | Next.js production build behind reverse proxy |
| Identity | None (single user) | SSO (OIDC / SAML) |
| Observability | Console logs + SQLite trace | OpenTelemetry + Grafana + Prometheus |

All swaps are behind interfaces. No business logic changes when moving from local to production.

---

## 3. Data Model

### 3.1 Medallion tables

All tables are Delta Lake tables stored on MinIO under the bucket `nepse-lakehouse`.

Paths follow the convention `s3://nepse-lakehouse/<layer>/<table_name>/`.

#### 3.1.1 Bronze (raw, append-only)

Bronze tables preserve raw scraped/ingested data with full fidelity. Never overwrite, never delete.

| Table | Partition | Key fields |
|---|---|---|
| `bronze.prices_raw` | ingestion_date | scrip, source, scrape_ts, raw_payload (JSON string), parser_version |
| `bronze.fundamentals_raw` | ingestion_date | scrip, source, scrape_ts, quarter, raw_payload, parser_version |
| `bronze.corporate_actions_raw` | ingestion_date | scrip, source, scrape_ts, raw_payload, parser_version |
| `bronze.news_raw` | ingestion_date | article_url, source, scrape_ts, raw_html, raw_text, parser_version |
| `bronze.macro_raw` | ingestion_date | indicator, source, scrape_ts, raw_payload, parser_version |
| `bronze.announcements_raw` | ingestion_date | scrip, source, scrape_ts, raw_payload, parser_version |

#### 3.1.2 Silver (cleaned, typed, deduped)

Silver tables are the authoritative business-entity layer. One row per canonical fact.

**`silver.prices`** — partitioned by `year`
```
scrip: string (PK)
date: date (PK)
open: double
high: double
low: double
close: double
volume: bigint
turnover: double
num_trades: int
adjusted_close: double    -- back-adjusted for splits/bonuses
source: string
ingested_at: timestamp
```

**`silver.fundamentals`** — partitioned by `fiscal_year`
```
scrip: string (PK)
fiscal_year: int (PK)         -- BS year
quarter: int (PK)             -- 1..4 (Q1=Shrawan-Ashwin, Q4=Baisakh-Ashad)
metric_name: string (PK)
value: double
reported_date: date
fiscal_year_ad_start: date    -- AD equivalent for joins
source: string
ingested_at: timestamp
```

Metrics stored (banks): `net_profit`, `operating_profit`, `net_interest_income`, `eps`, `bvps`, `roe`, `roa`, `npl_ratio`, `car`, `cd_ratio`, `total_deposits`, `total_loans`, `distributable_profit`, `paid_up_capital`, `pe_ratio`, `pb_ratio`.

**`silver.corporate_actions`**
```
scrip: string
action_type: string           -- bonus | rights | cash_dividend | split | merger
ratio: double                  -- e.g., 0.15 for 15% bonus
announcement_date: date
book_closure_date: date
ex_date: date
fiscal_year: int
source: string
```

**`silver.news`** — partitioned by `year_month`
```
article_id: string (PK, hash of url)
url: string
source: string
published_at: timestamp
title: string
body: string
language: string              -- en | ne | mixed
scrip_tags: array<string>
sector_tags: array<string>
event_type: string            -- earnings | dividend | management | regulatory | merger | other
ingested_at: timestamp
```

**`silver.macro`** — partitioned by `year`
```
indicator: string (PK)        -- policy_rate | crr | slr | inflation_cpi | m2 | remittance | forex_reserve | ...
date: date (PK)               -- first of month for monthly indicators
value: double
unit: string
source: string
ingested_at: timestamp
```

**`silver.sectors`**
```
scrip: string (PK)
sector: string                -- commercial_bank | development_bank | finance | hydropower | insurance | ...
sub_sector: string
listing_date: date
paid_up_capital: double
is_active: boolean
```

**`silver.trading_calendar`**
```
date: date (PK)
is_trading_day: boolean
reason_if_closed: string      -- weekend | public_holiday | nepse_closure
```

#### 3.1.3 Gold (analytics-ready, materialized)

Gold tables are what the tool layer reads. Pre-computed on a schedule to avoid runtime computation.

**`gold.indicators_daily`** — partitioned by `year`
```
scrip: string (PK)
date: date (PK)
close: double
sma_20: double
sma_50: double
sma_200: double
ema_12: double
ema_26: double
rsi_14: double
macd: double
macd_signal: double
macd_histogram: double
bollinger_upper: double
bollinger_middle: double
bollinger_lower: double
atr_14: double
adx_14: double
volume_sma_20: double
computed_at: timestamp
```

**`gold.peer_rankings_quarterly`**
```
scrip: string (PK)
sector: string
fiscal_year: int (PK)
quarter: int (PK)
metric_name: string (PK)
value: double
rank_in_sector: int
percentile_in_sector: double
sector_median: double
sector_mean: double
computed_at: timestamp
```

**`gold.stage1_screen_results`**
```
scrip: string (PK)
fiscal_year: int (PK)
quarter: int (PK)
sector: string
profitability_score: double
revenue_growth_score: double
return_ratio_score: double
composite_score: double
passed: boolean               -- true if in top 50-60% of sector
rank: int
computed_at: timestamp
```

**`gold.stage2_bank_screen`**
```
scrip: string (PK)
fiscal_year: int (PK)
quarter: int (PK)
roe: double
roe_percentile: double
npl_ratio: double
npl_percentile: double
car: double
car_percentile: double
cd_ratio: double
cd_percentile: double
composite_score: double
flags: array<string>          -- e.g., ["NPL_HIGH", "CAR_BELOW_THRESHOLD"]
computed_at: timestamp
```

**`gold.valuation`**
```
scrip: string (PK)
date: date (PK)
pe_trailing: double
pe_forward: double
pb: double
peer_pe_median: double
peer_pb_median: double
pe_vs_peer_pct: double         -- positive = premium, negative = discount
fair_value_forward_eps: double
upside_pct: double
computed_at: timestamp
```

**`gold.news_embeddings`**
```
article_id: string (PK)
scrip_tag: string              -- denormalized, one row per (article, scrip)
published_at: timestamp
embedding: array<float>        -- bge-m3 dimensions
embedding_model: string
embedding_version: string
```

### 3.2 Postgres serving schema

Postgres holds a serving copy of Gold tables plus vector index plus operational tables. Sync job runs after each Gold materialization.

```sql
-- Mirrors of gold.* tables
CREATE TABLE indicators_daily (...);
CREATE TABLE peer_rankings_quarterly (...);
CREATE TABLE stage1_screen_results (...);
CREATE TABLE stage2_bank_screen (...);
CREATE TABLE valuation (...);

-- News with embeddings
CREATE TABLE news_articles (
    article_id TEXT PRIMARY KEY,
    url TEXT,
    source TEXT,
    published_at TIMESTAMPTZ,
    title TEXT,
    body TEXT,
    scrip_tags TEXT[],
    event_type TEXT,
    embedding vector(1024)         -- bge-m3 = 1024 dims
);
CREATE INDEX ON news_articles USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON news_articles USING GIN (scrip_tags);

-- Operational tables
CREATE TABLE query_traces (
    trace_id UUID PRIMARY KEY,
    user_id TEXT,
    session_id TEXT,
    query_text TEXT,
    query_embedding vector(1024),
    intent_classification JSONB,
    tool_calls JSONB,               -- array of {tool, input, output, latency_ms}
    final_response TEXT,
    total_latency_ms INT,
    input_tokens INT,
    output_tokens INT,
    model_used TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE semantic_cache (
    cache_key TEXT PRIMARY KEY,      -- hash of normalized query
    query_text TEXT,
    query_embedding vector(1024),
    response TEXT,
    tool_call_results JSONB,
    hit_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX ON semantic_cache USING hnsw (query_embedding vector_cosine_ops);

CREATE TABLE scrips (
    scrip TEXT PRIMARY KEY,
    company_name TEXT,
    sector TEXT,
    sub_sector TEXT,
    is_active BOOLEAN
);
```

### 3.3 Redis key patterns

```
quote:<scrip>                    -- latest tick/EOD quote, TTL 60s
indicators:<scrip>:latest        -- latest indicator row, TTL 5min
stage1:<fiscal_year>:<quarter>   -- latest screen, TTL 1h
session:<session_id>             -- conversation state, TTL 1h
rate_limit:<user_id>             -- API rate limiting
```

---

## 4. Components

### 4.1 Library layout (monorepo)

```
nepse-research-copilot/
├── docker-compose.yml
├── docker-compose.prod.yml.example
├── Makefile
├── pyproject.toml                  # uv workspace root
├── libs/
│   ├── contracts/                  # Pydantic schemas shared across services
│   │   ├── market.py               # Quote, OHLCV, CorporateAction
│   │   ├── fundamentals.py         # FundamentalSnapshot, ScreenResult
│   │   ├── technicals.py           # IndicatorSet
│   │   ├── news.py                 # NewsArticle, NewsSearchResult
│   │   ├── trace.py                # QueryTrace, ToolCall
│   │   └── __init__.py
│   ├── compute/                    # Compute engine abstraction
│   │   ├── engine.py               # ComputeEngine interface
│   │   ├── duckdb_engine.py
│   │   ├── spark_engine.py
│   │   └── factory.py
│   ├── bus/                        # Message bus abstraction
│   │   ├── bus.py                  # MessageBus interface
│   │   ├── nats_bus.py
│   │   ├── kafka_bus.py
│   │   └── factory.py
│   ├── storage/                    # Storage clients
│   │   ├── minio_client.py
│   │   ├── delta_io.py             # Delta read/write using delta-rs
│   │   ├── postgres_client.py
│   │   └── redis_client.py
│   ├── llm/                        # LLM provider abstraction
│   │   ├── provider.py             # LLMProvider interface
│   │   ├── gemini_provider.py
│   │   ├── claude_provider.py
│   │   ├── vllm_provider.py        # For future local hosting
│   │   └── factory.py
│   ├── embeddings/
│   │   ├── provider.py
│   │   ├── bge_provider.py
│   │   └── factory.py
│   ├── nepal/                      # Nepal-specific utilities
│   │   ├── bs_date.py              # Bikram Sambat conversion
│   │   ├── devanagari.py           # Nepali text normalization
│   │   ├── fiscal_year.py          # BS fiscal year helpers
│   │   └── trading_calendar.py
│   └── observability/
│       ├── logging.py              # Structured logging
│       ├── tracing.py              # OpenTelemetry setup
│       └── metrics.py
├── services/
│   ├── ingestion/
│   │   ├── scrapers/
│   │   │   ├── sharesansar/
│   │   │   ├── merolagani/
│   │   │   ├── nepse/
│   │   │   └── nrb/
│   │   ├── publishers/             # Publish to message bus
│   │   └── main.py
│   ├── processing/
│   │   ├── jobs/
│   │   │   ├── price_normalizer.py
│   │   │   ├── fundamental_parser.py
│   │   │   ├── indicator_compute.py
│   │   │   ├── peer_ranking.py
│   │   │   ├── stage1_screen.py
│   │   │   ├── stage2_bank_screen.py
│   │   │   ├── valuation.py
│   │   │   └── news_embedder.py
│   │   └── common/
│   ├── tools/                      # Tool layer (FastAPI)
│   │   ├── app.py
│   │   ├── routers/
│   │   │   ├── market.py
│   │   │   ├── fundamentals.py
│   │   │   ├── screens.py
│   │   │   ├── technicals.py
│   │   │   ├── news.py
│   │   │   └── macro.py
│   │   └── main.py
│   ├── orchestrator/               # LLM agent loop (FastAPI)
│   │   ├── app.py
│   │   ├── agent/
│   │   │   ├── intent.py
│   │   │   ├── planner.py
│   │   │   ├── executor.py
│   │   │   ├── synthesizer.py
│   │   │   └── cache.py
│   │   ├── routers/
│   │   │   ├── chat.py             # POST /chat (streaming)
│   │   │   └── trace.py            # GET /trace/{trace_id}
│   │   └── main.py
│   └── frontend/                   # Next.js app
│       ├── app/
│       │   ├── chat/
│       │   ├── trace/              # Dev-mode trace viewer
│       │   └── layout.tsx
│       ├── components/
│       │   ├── ChatMessage.tsx
│       │   ├── ToolCallBadge.tsx
│       │   ├── StageBadge.tsx
│       │   ├── InlineChart.tsx
│       │   └── StreamingResponse.tsx
│       └── lib/
├── pipelines/                      # Prefect flows
│   ├── daily_ingestion.py
│   ├── indicator_materialization.py
│   ├── screen_materialization.py
│   └── news_embedding.py
├── migrations/                     # Postgres migrations (Alembic)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── scripts/
│   ├── bootstrap_local.sh
│   ├── seed_scrips.py
│   └── backfill.py
└── docs/
    ├── architecture.md
    ├── data_dictionary.md
    ├── tool_reference.md
    └── runbook.md
```

### 4.2 Component specifications

#### 4.2.1 Ingestion service

**Responsibilities:**
- Run scheduled scrapers against configured sources.
- Emit raw events to the message bus (one event per record scraped).
- Snapshot raw payloads to `bronze.*` tables directly (write-through).

**Technology:**
- Python 3.12, `httpx` (async), `selectolax` (fast HTML parsing), `pydantic` for contracts.
- Scraping rate-limited (2-5s delays), rotating user agents, retry with exponential backoff.
- Each scraper is idempotent — re-running for the same date produces no duplicates (upsert by natural key).

**Configuration:**
- `config/sources.yaml` defines sources, endpoints, selectors, frequency, retry policy.
- Secrets (API keys, if any) from environment variables; never committed.

**Key scrapers for prototype:**

| Scraper | Source | Frequency | Output topic |
|---|---|---|---|
| `sharesansar_prices` | sharesansar.com | Daily after market close | `raw.prices` |
| `sharesansar_fundamentals` | sharesansar.com | Daily (checks for new quarterly releases) | `raw.fundamentals` |
| `sharesansar_news` | sharesansar.com news feed | Every 15 min | `raw.news` |
| `sharesansar_corporate_actions` | sharesansar.com | Daily | `raw.corporate_actions` |
| `merolagani_prices` | merolagani.com | Daily (fallback) | `raw.prices` |
| `nepse_index` | nepalstock.com.np | Daily | `raw.prices` (special scrip `NEPSE`) |
| `nrb_macro` | nrb.org.np | Monthly (checks for new report PDFs) | `raw.macro` |

**Raw HTML snapshots:**
- All scraped pages saved to `s3://nepse-lakehouse/raw-snapshots/<source>/<date>/<hash>.html.gz`.
- Enables re-parsing when a parser bug is discovered.

#### 4.2.2 Processing jobs

**Job: `price_normalizer`**
- Reads `bronze.prices_raw` since last watermark.
- Validates schema, deduplicates by (scrip, date, source) preferring highest-priority source.
- Joins with `silver.corporate_actions` to compute `adjusted_close` (back-adjusts for splits and bonuses).
- Writes to `silver.prices`.

**Job: `fundamental_parser`**
- Reads `bronze.fundamentals_raw`.
- Normalizes field names across sources (different portals call the same metric different things).
- Unpivots wide-format scrapes into the long `(scrip, fiscal_year, quarter, metric_name, value)` shape.
- Writes to `silver.fundamentals`.

**Job: `indicator_compute`**
- Reads `silver.prices` for all active scrips.
- Computes per-scrip rolling indicators: SMA(20, 50, 200), EMA(12, 26), RSI(14), MACD(12,26,9), Bollinger(20, 2), ATR(14), ADX(14), volume SMA(20).
- Implemented using pandas-ta or a handwritten module (handwritten preferred for auditability and for porting to Spark).
- Writes to `gold.indicators_daily` (full overwrite partition by year; idempotent).

**Job: `peer_ranking`**
- For each (fiscal_year, quarter, sector, metric), computes rank, percentile, median, mean across scrips in the sector.
- Reads `silver.fundamentals`, writes `gold.peer_rankings_quarterly`.

**Job: `stage1_screen`**
- For each (fiscal_year, quarter, sector):
  - Computes profitability score (z-score of net_profit growth).
  - Computes revenue growth score (z-score of net_interest_income growth for banks).
  - Computes return ratio score (z-score of ROE).
  - Combines into composite with configurable weights (stored in `config/screens.yaml`).
  - Ranks and flags top 50-60%.
- Writes to `gold.stage1_screen_results`.

**Job: `stage2_bank_screen`**
- For each bank scrip per quarter:
  - Pulls ROE, NPL, CAR, CD ratio from fundamentals.
  - Computes percentiles from `gold.peer_rankings_quarterly`.
  - Applies configurable thresholds (e.g., `CAR < 11% → flag CAR_LOW`).
  - Produces composite score.
- Writes to `gold.stage2_bank_screen`.

**Job: `valuation`**
- For each scrip on each trading date:
  - Pulls latest EPS, BVPS, close price.
  - Computes trailing P/E, P/B.
  - Pulls sector peer medians from `gold.peer_rankings_quarterly`.
  - Computes relative premium/discount.
  - Computes forward EPS using trailing growth rate (configurable method; prototype uses simple YoY extrapolation, production to use analyst model).
- Writes to `gold.valuation`.

**Job: `news_embedder`**
- Reads unembedded rows from `silver.news`.
- Generates embeddings using configured embedding provider (bge-m3).
- Writes to `gold.news_embeddings` and syncs to Postgres `news_articles` table with embedding.

**All jobs:**
- Expose `watermark` state (last successful run partition) in a `processing_state` table.
- Are idempotent (re-running for the same partition produces identical output).
- Emit metrics: rows read, rows written, duration, errors.
- Use the compute engine abstraction — never import `pyspark` or `duckdb` directly.

#### 4.2.3 Tool layer (FastAPI service)

**Port:** 8001 (local)
**Base URL:** `http://tools:8001`

Each tool is a POST endpoint with Pydantic request/response models. Tools are pure — they read from Postgres/Redis and return JSON. No side effects.

**Tool catalog (prototype):**

| Tool | Endpoint | Purpose |
|---|---|---|
| `get_quote` | `POST /tools/get_quote` | Latest price/EOD snapshot for a scrip |
| `get_price_history` | `POST /tools/get_price_history` | OHLCV over a date range |
| `get_fundamentals` | `POST /tools/get_fundamentals` | Fundamentals for a scrip at a given quarter |
| `get_peer_ranking` | `POST /tools/get_peer_ranking` | Scrip's rank on specified metric in its sector |
| `stage1_screen` | `POST /tools/stage1_screen` | Stage 1 screen results for a sector + quarter |
| `stage2_bank_screen` | `POST /tools/stage2_bank_screen` | Stage 2 metrics for a bank |
| `valuation` | `POST /tools/valuation` | P/E, P/B, fair value estimate |
| `technicals` | `POST /tools/technicals` | Indicator values on a date |
| `search_news` | `POST /tools/search_news` | Hybrid semantic + scrip-tag news search |
| `macro_snapshot` | `POST /tools/macro_snapshot` | Current macro indicators |
| `peer_compare` | `POST /tools/peer_compare` | Side-by-side comparison of scrips on metrics |
| `list_scrips` | `POST /tools/list_scrips` | List scrips by sector |

Every tool response includes:
```json
{
  "data": { ... },
  "metadata": {
    "tool": "get_quote",
    "tool_version": "1.0.0",
    "data_as_of": "2026-04-20T10:15:00+05:45",
    "sources": ["silver.prices"],
    "latency_ms": 12
  }
}
```

**Tool schemas (OpenAPI spec auto-generated by FastAPI)** must be machine-readable by the LLM orchestrator — the orchestrator loads them at startup and passes the tool definitions to the LLM for tool-calling.

#### 4.2.4 Orchestrator service

**Port:** 8000 (local)
**Base URL:** `http://orchestrator:8000`

**Primary endpoint:** `POST /chat`

Request:
```json
{
  "session_id": "optional-uuid",
  "message": "How is NABIL doing this quarter?",
  "user_id": "demo-user",
  "stream": true
}
```

Response: Server-Sent Events stream with message chunks, tool call events, and the final response.

**Agent loop:**

1. **Cache check.** Embed the query. Cosine-search `semantic_cache` in Postgres. If similarity > 0.95 and not expired, return cached response with `cache_hit: true`.

2. **Intent classification.** Call the small/fast LLM with a system prompt describing intent categories. Expected output (structured JSON):
   ```json
   {
     "intent": "fundamental_query",
     "entities": {"scrip": "NABIL", "timeframe": "latest_quarter"},
     "requires_tools": ["get_fundamentals", "stage2_bank_screen", "peer_ranking"],
     "requires_news": false,
     "complexity": "medium"
   }
   ```

   Intent categories: `quote_query`, `fundamental_query`, `screen_query`, `valuation_query`, `technical_query`, `news_query`, `macro_query`, `hybrid_query`, `meta_query`, `out_of_scope`.

3. **Tool planning.** Based on intent, compose a DAG of tool calls. Independent calls run in parallel; dependent calls run sequentially.

4. **Tool execution.** Call each tool via HTTP. Aggregate results. Record each call's input, output, and latency into the trace.

5. **Synthesis.** Call the main LLM with: the original query, the structured tool results, and a system prompt instructing it to:
   - Base every numerical claim on tool output.
   - Cite which tool produced each fact (internally, for trace; surface in UI as tooltips).
   - Follow the bank's research framework terminology (Stage 1, Stage 2, etc.).
   - Surface relevant warnings (e.g., "data is from last quarter" if no current quarter available).

6. **Stream response.** Stream tokens back to frontend as SSE. After completion, write trace to `query_traces`, write response to `semantic_cache`.

**Error handling:**
- Tool call failures are caught; the LLM is informed ("tool X returned an error") and asked to produce the best possible answer from remaining data, flagging the gap to the user.
- LLM API failures trigger retries with exponential backoff, then fallback to a secondary provider if configured.
- If no tools succeed, return an honest "I couldn't retrieve data to answer this" message.

**Out-of-scope handling:**
- Queries classified as `out_of_scope` (e.g., "what's the weather") get a polite refusal without tool calls.

#### 4.2.5 Frontend

**Framework:** Next.js 14+ (App Router), TypeScript, Tailwind.

**Key pages:**
- `/` — landing with chat UI
- `/chat/[session_id]` — persistent chat sessions
- `/trace/[trace_id]` — dev-mode trace viewer (tool call inspector)

**Key components:**
- `ChatInput` — message composer
- `ChatMessage` — rendered message with markdown, inline charts, tool badges
- `StageBadge` — visual indicator showing which research stage (Stage 1, Stage 2, Valuation, Technical, News) was invoked, referencing the bank's research flow
- `ToolCallBadge` — small chip showing tool called, expandable to show inputs/outputs
- `InlineChart` — Recharts-based renderer for time series, bar charts, ranking tables
- `StreamingResponse` — handles SSE parsing and progressive rendering

**Styling:**
- Professional, financial-terminal aesthetic (dark mode default, monospace for numbers).
- Numbers always formatted with thousand separators and consistent precision.
- NEPSE-native colors (green for up moves, red for down — this is universal).

**State:**
- Zustand for session state.
- Server components for data fetching where possible.
- No client-side localStorage for sensitive data (bank will require this).

---

## 5. Abstractions (Critical)

These interfaces are the migration payoff. Implement carefully.

### 5.1 Compute engine

```python
# libs/compute/engine.py
from abc import ABC, abstractmethod
from typing import Any
import pandas as pd

class ComputeEngine(ABC):
    @abstractmethod
    def read_delta(self, path: str, filters: list | None = None) -> pd.DataFrame: ...

    @abstractmethod
    def write_delta(self, df: pd.DataFrame, path: str, mode: str = "append",
                    partition_by: list[str] | None = None) -> None: ...

    @abstractmethod
    def sql(self, query: str, **params) -> pd.DataFrame: ...

    @abstractmethod
    def register_view(self, name: str, df_or_path: Any) -> None: ...
```

Implementations: `DuckDBEngine` (uses `duckdb` + `deltalake` Python package), `SparkEngine` (uses pyspark + delta-spark).

Factory resolves from env var `COMPUTE_ENGINE=duckdb|spark`.

All processing jobs receive a `ComputeEngine` instance via dependency injection. They never import DuckDB or Spark directly.

### 5.2 Message bus

```python
# libs/bus/bus.py
class MessageBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, message: dict) -> None: ...

    @abstractmethod
    async def subscribe(self, topic: str, handler: Callable, consumer_group: str) -> None: ...

    @abstractmethod
    async def create_topic(self, topic: str, partitions: int = 1) -> None: ...
```

Implementations: `NATSBus`, `KafkaBus`. Factory via `MESSAGE_BUS=nats|kafka`.

### 5.3 LLM provider

```python
# libs/llm/provider.py
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[Message], tools: list[Tool] | None = None,
                       **kwargs) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, messages: list[Message], tools: list[Tool] | None = None,
                     **kwargs) -> AsyncIterator[LLMChunk]: ...
```

Implementations: `GeminiProvider`, `ClaudeProvider`, `VLLMProvider` (for future local hosting on DGX).

Factory resolves model per task from config:
```yaml
llm:
  intent_classifier:
    provider: gemini
    model: gemini-2.5-flash-lite
  synthesizer:
    provider: claude
    model: claude-opus-4-7
  fallback:
    provider: gemini
    model: gemini-2.5-pro
```

### 5.4 Embedding provider

Same pattern. `BGEProvider` (HTTP to hosted or local endpoint).

---

## 6. Configuration

All configuration lives in `config/` and is environment-overridable.

```
config/
├── base.yaml              # Defaults
├── local.yaml             # Mac Mini overrides
├── production.yaml.example
├── sources.yaml           # Scraper definitions
├── screens.yaml           # Stage 1/2 thresholds and weights
├── scrips.yaml            # Active scrip list for prototype
└── llm.yaml               # Model assignments per task
```

`config/screens.yaml` example:
```yaml
stage1:
  profitability_weight: 0.4
  revenue_growth_weight: 0.3
  return_ratio_weight: 0.3
  pass_threshold_percentile: 0.4    # Top 60%

stage2_bank:
  roe_min_threshold: 0.12
  npl_max_threshold: 0.03
  car_min_threshold: 0.11
  cd_max_threshold: 0.90
  flags:
    NPL_HIGH: "npl_ratio > 0.03"
    CAR_LOW: "car < 0.11"
    CD_HIGH: "cd_ratio > 0.90"
    ROE_STRONG: "roe > 0.15"
```

This file is editable by the bank's research team without code changes — they tune the thresholds, redeploy, done.

---

## 7. Observability

### 7.1 Logging

- Structured JSON logs via `structlog`.
- Every request tagged with `trace_id` propagated across services.
- Log levels: DEBUG (dev), INFO (prod default), WARNING, ERROR.

### 7.2 Tracing

- OpenTelemetry instrumentation on FastAPI services.
- Local: log to console.
- Production: export to OTLP collector (Grafana Tempo or similar).

### 7.3 Metrics

- Prometheus `/metrics` endpoints on each service.
- Key metrics:
  - `nepse_scraper_records_total{source, scrip}` — counter
  - `nepse_scraper_errors_total{source, reason}` — counter
  - `nepse_tool_call_duration_seconds{tool}` — histogram
  - `nepse_llm_tokens_total{provider, model, type}` — counter
  - `nepse_cache_hits_total{level}` — counter
  - `nepse_orchestrator_latency_seconds{intent}` — histogram

### 7.4 Query traces

- Every chat query writes a row to `query_traces`.
- Trace viewer UI at `/trace/{trace_id}` shows:
  - Query text
  - Intent classification
  - Each tool call with inputs, outputs, latency
  - Final LLM prompt and response
  - Total latency breakdown

This is both debugging infrastructure and the compliance artifact.

---

## 8. Testing Strategy

### 8.1 Unit tests

- Every deterministic function: indicator calculations, BS date conversion, screen logic.
- Pure functions with fixtures checked in under `tests/fixtures/`.
- Target: >80% coverage on `libs/` and `services/processing/jobs/`.

### 8.2 Integration tests

- Full pipeline test: seed bronze → run jobs → verify gold.
- Tool API tests with test Postgres + Redis (docker-compose.test.yml).
- Orchestrator tests with mocked LLM provider returning fixed tool calls.

### 8.3 Eval suite for LLM pipeline

- Curated set of ~50 queries with expected behaviors (not exact responses).
- Each eval checks:
  - Correct intent classification.
  - Correct tools called.
  - Response mentions all required facts.
  - Response does not hallucinate numbers absent from tool outputs.
- Run on every orchestrator change.

### 8.4 Scraper tests

- Checked-in HTML fixtures for each source.
- Parser tests run against fixtures offline.
- Live scrape tests gated behind env flag (don't run in CI).

---

## 9. Local Development

### 9.1 Prerequisites

- macOS 14+ on Apple Silicon
- OrbStack installed
- Homebrew
- uv (Python package manager)
- Node.js 20+ via `fnm` or `nvm`

### 9.2 Bootstrap

```bash
# Install dependencies
brew install duckdb postgresql@16 pgvector
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and bootstrap
git clone <repo>
cd nepse-research-copilot
./scripts/bootstrap_local.sh

# Start infrastructure
docker compose up -d minio nats postgres redis

# Install Python workspace
uv sync

# Run migrations
uv run alembic upgrade head

# Seed scrips
uv run python scripts/seed_scrips.py

# Start services (separate terminals or tmux)
uv run fastapi dev services/tools/main.py --port 8001
uv run fastapi dev services/orchestrator/main.py --port 8000
cd services/frontend && npm run dev
```

### 9.3 Docker Compose

```yaml
# docker-compose.yml (local)
services:
  minio:
    image: minio/minio:latest
    platform: linux/arm64
    command: server /data --console-address ":9001"
    ports: ["9000:9000", "9001:9001"]
    volumes: ["./data/minio:/data"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin

  nats:
    image: nats:2-alpine
    platform: linux/arm64
    command: ["-js", "-sd", "/data"]
    ports: ["4222:4222", "8222:8222"]
    volumes: ["./data/nats:/data"]

  postgres:
    image: pgvector/pgvector:pg16
    platform: linux/arm64
    environment:
      POSTGRES_USER: nepse
      POSTGRES_PASSWORD: nepse
      POSTGRES_DB: nepse
    ports: ["5432:5432"]
    volumes: ["./data/postgres:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    platform: linux/arm64
    ports: ["6379:6379"]
    volumes: ["./data/redis:/data"]
```

### 9.4 RAM budget (enforced)

| Service | Target RAM | Max RAM |
|---|---|---|
| MinIO | 200 MB | 400 MB |
| NATS | 100 MB | 300 MB |
| Postgres | 400 MB | 800 MB |
| Redis | 100 MB | 200 MB |
| Tools service | 200 MB | 400 MB |
| Orchestrator service | 300 MB | 500 MB |
| Next.js dev | 900 MB | 1.2 GB |
| Processing jobs | 500 MB | 1.5 GB (burst) |

Total steady-state: ~2.7 GB. Peak during processing: ~4 GB. Leaves 12 GB for macOS + IDE + browser.

---

## 10. Migration to Production

### 10.1 Infrastructure changes

1. Move containers to Kubernetes manifests (k3s or full k8s on DGX).
2. Replace NATS with Redpanda (or Kafka) — same producer/consumer code.
3. Replace DuckDB engine with Spark engine — flip env var, re-run jobs.
4. Deploy vLLM server on DGX GPU for local LLM inference.
5. Replace external LLM API with vLLM endpoint — change config, no code.
6. Enable Postgres HA (streaming replication).
7. Enable Redis HA (sentinel or cluster).
8. Add reverse proxy (Nginx/Traefik) with TLS.
9. Integrate SSO.

### 10.2 Data migration

- Delta tables: copy from local MinIO to production MinIO (`mc mirror`).
- Postgres: pg_dump/restore.
- No schema changes.

### 10.3 Net-new for production

- SSO integration.
- Audit log export to bank's SIEM.
- User-level rate limiting.
- Regulator-compliant disclosure banners on responses.
- Human-in-the-loop review queue (if SEBON/NRB require).

---

## 11. Open Questions for the Bank

Resolve these before production build. Prototype can proceed without them but must flag assumptions.

**Data:**
1. Will the bank provide a licensed NEPSE TMS feed, and through which broker relationship?
2. What format is their order history in (database, CSV export, API)?
3. Do they have a historical "approved investment list" we can use as validation ground truth?
4. What are their exact Stage 1 weights and Stage 2 thresholds?
5. Is the bank subscribed to any premium data vendor (Bloomberg, Refinitiv)?
6. Licensing terms for consuming Sharesansar/Merolagani content inside a commercial bank product?

**Infrastructure:**
7. Is the DGX Spark environment air-gapped or does it have outbound Internet?
8. What's the Postgres / storage HA story on the DGX host?
9. SSO provider (Keycloak, Azure AD, Okta)?

**Regulatory:**
10. SEBON / NRB requirements on AI-driven research output disclosure?
11. Data residency requirements?
12. Audit log retention period?
13. Does research output require human sign-off before presentation to traders?

**Product:**
14. Who are the first three users (trader, analyst, CEO)? Their top use cases?
15. Integration targets: OMS, Bloomberg Terminal, Teams/email?
16. Mobile access required?
17. Definition of "good decision" for System B (future): absolute return, risk-adjusted, alpha over index?

---

## 12. Definition of Done (Prototype)

The prototype is considered complete when:

1. Data for 20 commercial banks is flowing end-to-end: scrape → bronze → silver → gold, orchestrated by Prefect, no manual steps.
2. All 12 tools are implemented, tested, documented in OpenAPI, and callable from the orchestrator.
3. The orchestrator handles the three core demo queries with correct intent classification, tool calls, and synthesized responses:
   - "Which banks pass our Stage 1 screen this quarter?"
   - "Show me NABIL's Stage 2 metrics and how it ranks among banks on ROE and NPL."
   - "Is NABIL fairly valued right now, and what do the technicals say?"
4. Frontend renders streaming responses with inline charts, stage badges, and tool call chips.
5. Query traces are persisted and viewable at `/trace/{id}`.
6. The entire stack starts with `docker compose up` plus `make dev` and runs steadily on 16GB.
7. Migration path to Spark/Kafka/vLLM is documented with a runbook — and dry-run tested by swapping the compute engine factory once.
8. Eval suite passes with >90% on intent classification and >80% on response-quality checks.
9. README, architecture doc, data dictionary, tool reference, and runbook are complete.

---

## Appendix A — Technology Decisions Log

| Decision | Chosen | Rejected | Rationale |
|---|---|---|---|
| Table format | Delta Lake | Iceberg, Hudi | Ecosystem maturity, delta-rs enables Python-native reads, Spark compatibility |
| Object store | MinIO | AWS S3 | On-prem requirement for bank |
| Local compute | DuckDB | Spark-local | 10x lower RAM; Spark runs on production |
| Message bus (local) | NATS JetStream | Kafka | 5x lower RAM, adequate durability for prototype |
| Message bus (prod) | Redpanda / Kafka | NATS | Ecosystem + ops maturity |
| LLM (prototype) | Claude / Gemini API | Local Llama | Faster iteration; local LLM available on DGX |
| Embedding | bge-m3 | OpenAI text-embed-3 | Multilingual (Nepali support), open-weight, portable |
| Orchestrator (prototype) | Prefect | Dagster | Lighter RAM footprint |
| Serving DB | Postgres + pgvector | Dedicated vector DB (Qdrant) | Fewer services to operate; pgvector is fast enough for 100K-scale corpus |
| Frontend | Next.js | Streamlit | Production-grade UX; Streamlit is prototype-only |
| Container runtime | OrbStack | Docker Desktop | Dramatically lower RAM on Mac |
| Package manager | uv | poetry, pip | 10x faster installs |

---

## Appendix B — Glossary

- **NEPSE:** Nepal Stock Exchange
- **BFI:** Bank or Financial Institution
- **NRB:** Nepal Rastra Bank (central bank)
- **SEBON:** Securities Board of Nepal (regulator)
- **TMS:** Trade Management System (NEPSE's broker trading platform)
- **BS:** Bikram Sambat (Nepali calendar)
- **AD:** Anno Domini (Gregorian calendar)
- **ROE:** Return on Equity
- **NPL:** Non-Performing Loan ratio
- **CAR:** Capital Adequacy Ratio
- **CD ratio:** Credit-to-Deposit ratio
- **Stage 1 screen:** Quantitative screen on profitability, growth, return ratios (top 50-60% of sector)
- **Stage 2 screen:** Sector-specific deep screen (for banks: ROE, NPL, CAR, CD ratio)
- **Bronze/Silver/Gold:** Medallion data quality tiers

---

*End of document.*
