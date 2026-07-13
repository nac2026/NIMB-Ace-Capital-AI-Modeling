# NIMB Ace — Deployment Runbook

Production deployment and day-2 operations for **NIMB Ace / nep-trade-analytics**, an
LLM-powered NEPSE trade-analytics platform (Python `uv` workspace monorepo + a Next.js
frontend). This folder is the single source of truth for standing the platform up on a
server, hardening it, and running it.

> **Read `08-ci-deploy.md` first if you only want the release flow.** Development happens
> in the personal repo (`YarshaLabs/nep-trade-analytics`, branch `dev`), is mirrored to the
> client repo with `../sync-to-client.sh`, and is deployed on the server from the client's
> `dev` branch.

---

## What the platform is

| Layer | Runs as | Notes |
|-------|---------|-------|
| **Infrastructure** | Docker Compose containers (`make up`) | MinIO, Postgres/pgvector, Redis |
| **App services** | Long-running host processes (systemd / pm2) | Web, API, Dagster, dbt-docs — **not** containerized |
| **Compute** | Python processes (DuckDB) | Ingestion + Silver transforms; no container |

The only user-facing surfaces in production are the **Next.js web app** and its **FastAPI
API**, both behind a TLS reverse proxy. Everything else (MinIO, Postgres, Redis, Dagster,
dbt-docs) is **internal-only / firewalled**.

---

## Service + port map

| Port | Service | Runs as | Exposure | Start command |
|------|---------|---------|----------|---------------|
| `443` | Reverse proxy (nginx/TLS) | host | **public** | see [04-services](04-services.md) |
| `3000` | Next.js web app | host process | internal (proxied) | `cd services/web && npm run start` |
| `8080` | FastAPI orchestrator API | host process | internal (proxied) | `uv run nrc-serve` |
| `3001` | Dagster UI (pipeline orchestrator) | host process | **internal-only** | `make dagster-dev` |
| `8081` | dbt docs | host process | **internal-only** | `make dbt-docs` |
| `9000` | MinIO S3 API | container | **internal-only** | `make up` |
| `9001` | MinIO web console | container | **internal-only** | `make up` |
| `5432` | Postgres + pgvector | container | **internal-only** | `make up` |
| `6379` | Redis | container | **internal-only** | `make up` |

See [05-firewall-ports](05-firewall-ports.md) for the enforced exposure matrix.

---

## Architecture

```
                         Internet
                            │  443/TLS
                            ▼
                 ┌──────────────────────┐
                 │  Reverse proxy (nginx)│   ← only public surface
                 └───────────┬──────────┘
                 /           │          /api/*
                 ▼                       ▼
      ┌────────────────┐        ┌─────────────────────┐
      │ Next.js web    │  REST  │ FastAPI orchestrator │
      │ :3000          ├───────►│ :8080  (nrc-serve)   │
      └────────────────┘        └───────┬─────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────┐
        ▼                ▼               ▼               ▼            ▼
   ┌─────────┐     ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌──────────┐
   │ Vertex  │     │ Postgres │   │  Redis   │   │  MinIO   │   │  SMTM    │
   │ (Gemini)│     │  :5432   │   │  :6379   │   │:9000/9001│   │ live API │
   │ outbound│     │ serving  │   │ sessions │   │ buckets  │   │ outbound │
   └─────────┘     └────┬─────┘   └──────────┘   └────┬─────┘  └──────────┘
                        │                             │
                        │        ┌────────────────────┘
                        ▼        ▼
                 ┌──────────────────────────┐
                 │ Dagster :3001 (pipelines) │  ← Bronze→Silver→Gold→Postgres
                 │ dbt :8081 (Gold + docs)   │     + tradebook surveillance scan
                 └──────────────────────────┘

  Buckets in MinIO:  nepse-lakehouse (Delta)   raw-snapshots   nrc-internal-uploads
```

---

## Start here — numbered docs

| # | Doc | What it covers |
|---|-----|----------------|
| 01 | [Prerequisites](01-prerequisites.md) | Server sizing, OS, required software, outbound network |
| 02 | [Environment](02-environment.md) | Full env-var reference + secrets management |
| 03 | [Infrastructure](03-infrastructure.md) | `make up`, containers, buckets, volumes, `make verify` |
| 04 | [Services](04-services.md) | Web/API/Dagster/dbt-docs as systemd/pm2, nginx reverse proxy |
| 05 | [Firewall & ports](05-firewall-ports.md) | Port-exposure matrix, ufw/iptables |
| 06 | [File uploads & surveillance](06-file-uploads-and-surveillance.md) | Internal uploads → surveillance scan, end to end |
| 07 | [MinIO hardening](07-minio-hardening.md) | Root creds, scoped service account, TLS, console lockdown |
| 08 | [CI / deploy](08-ci-deploy.md) | Personal → client sync → server deploy steps |
| 09 | [Backup & restore](09-backup-restore.md) | Postgres, MinIO buckets, `./data/` volumes |
| 10 | [Runbook](10-runbook.md) | Day-2 ops: start/stop order, logs, failures, rollback |

---

## The 60-second deploy summary

```bash
# On the server, in the checked-out client repo on branch `dev`:
git pull                                  # get the latest client dev snapshot
make sync                                 # uv sync (Python deps)
cd services/web && npm install && npm run build && cd ../..
uv run nrc-process apply-schema           # apply infra/postgres/schema/*.sql migrations
make dbt-deps && make dbt-parse && make dbt-build
# restart the app services (systemd/pm2 — see 04-services.md), then:
make verify
curl -fsS localhost:8080/health && curl -fsS localhost:8080/ready
```

Full details: [08-ci-deploy](08-ci-deploy.md).
