# 02 — Environment variables

All configuration lives in a single **`.env` at the repo root**. It is **git-ignored** and
**never** synced to the client repo (the sync script even secret-scans for it — see
[08-ci-deploy](08-ci-deploy.md)). `.env.example` is the committed template; copy it and
fill in real values on the server.

```bash
cp .env.example .env
chmod 600 .env          # owner read/write only — see "Secrets management" below
```

Values below are grouped by subsystem. **Examples are placeholders from `.env.example`,
not real secrets.** Never print or commit real credentials.

---

## MinIO (object store)

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `MINIO_ENDPOINT` | S3 API URL the app/clients connect to | `http://localhost:9000` |
| `MINIO_ROOT_USER` | MinIO admin user (**rotate in prod**) | `minioadmin` |
| `MINIO_ROOT_PASSWORD` | MinIO admin password (**rotate in prod**) | `minioadmin` |
| `MINIO_BUCKET_LAKEHOUSE` | Delta Lake bucket | `nepse-lakehouse` |
| `MINIO_BUCKET_SNAPSHOTS` | Raw scraper snapshots bucket | `raw-snapshots` |
| `MINIO_BUCKET_UPLOADS` | **In-app internal file uploads bucket** | `nrc-internal-uploads` |
| `NRC_INTERNAL_TRADES_BACKEND` | Trade-book source for surveillance: `minio` (in-app uploads, **prod default**) or `local` (sibling `internal-trade-data/` folder, offline dev) | `minio` |

> In production keep `NRC_INTERNAL_TRADES_BACKEND=minio`. The `local` backend reads the
> sibling `internal-trade-data/` directory and is for offline dev only. See
> [06-file-uploads-and-surveillance](06-file-uploads-and-surveillance.md).

---

## Postgres (serving + operational DB)

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `POSTGRES_HOST` | Host for the serving DB | `localhost` |
| `POSTGRES_PORT` | Port | `5432` |
| `POSTGRES_USER` | DB user | `nepse` |
| `POSTGRES_PASSWORD` | DB password (**rotate in prod**) | `nepse` |
| `POSTGRES_DB` | Database name | `nepse` |
| `POSTGRES_URL` | Full DSN used by the app/pipeline | `postgresql://nepse:nepse@localhost:5432/nepse` |

> Keep the discrete vars and `POSTGRES_URL` **consistent** — the container reads
> `POSTGRES_USER/PASSWORD/DB`, the app reads `POSTGRES_URL`. A mismatch causes `/ready` to
> fail.

---

## Redis (session memory cache)

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `REDIS_URL` | Conversation-memory cache DSN | `redis://localhost:6379/0` |

---

## Compute engine

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `COMPUTE_ENGINE` | `duckdb` (local/prototype) or `spark` (future prod) | `duckdb` |

---

## LLM — Vertex AI (Gemini)

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `GCP_VERTEX_API_KEY` | Vertex AI API key (**required for LLM**) | *(set on server)* |
| `GCP_PROJECT_ID` | GCP project | *(set on server)* |
| `GCP_REGION` | Vertex region | `global` |
| `LLM_INTENT_MODEL` | Intent-classification model | `gemini-2.5-flash-lite` |
| `LLM_SYNTHESIZER_MODEL` | Answer-synthesis model | `gemini-2.5-pro` |

---

## SMTM Data API (live NEPSE feed)

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `SMTM_BASE_URL` | SMTM API base URL | `https://dataapi.smtmcapital.com.np` |
| `SMTM_USERNAME` | SMTM login (client-provided) | *(set on server)* |
| `SMTM_PASSWORD` | SMTM password (client-provided) | *(set on server)* |
| `SMTM_RATE_LIMIT_PER_MIN` | Client-side rate cap | `100` |

---

## Embeddings

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `EMBEDDING_PROVIDER` | Embedding backend | `bge` |
| `EMBEDDING_MODEL` | Model id | `bge-m3` |
| `EMBEDDING_DIM` | Vector dimension (must match pgvector column) | `1024` |

---

## Observability (logging / OTel)

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` | `INFO` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint (blank = disabled) | *(blank)* |

---

## Notifications — email alerts (speculation alerts)

Until `NOTIFICATIONS_ENABLED=true`, alerts evaluate and log but send nothing.

| Variable | Purpose | Example / placeholder |
|----------|---------|-----------------------|
| `NOTIFICATIONS_ENABLED` | Master switch | `false` |
| `NOTIFICATIONS_PROVIDER` | `resend` / `sendgrid` / `smtp` | `resend` |
| `NOTIFICATIONS_FROM_EMAIL` | Verified sender address | `onboarding@resend.dev` |
| `NOTIFICATIONS_FROM_NAME` | Sender display name | `NIMB Ace Alerts` |
| `NOTIFICATIONS_API_KEY` | API key (Resend/SendGrid transports) | *(set on server)* |
| `NOTIFICATIONS_SMTP_HOST` | SMTP host (smtp transport only) | `smtp.gmail.com` |
| `NOTIFICATIONS_SMTP_PORT` | SMTP port | `587` |
| `NOTIFICATIONS_SMTP_USERNAME` | SMTP user | *(set on server)* |
| `NOTIFICATIONS_SMTP_PASSWORD` | SMTP password / Gmail App Password | *(set on server)* |

---

## App runtime (API bind + frontend)

These are **not** in `.env.example` but are read by the process at runtime — set them in
the systemd unit / pm2 config ([04-services](04-services.md)), not in `.env`, if you need
to override defaults.

| Variable | Purpose | Default |
|----------|---------|---------|
| `NRC_HOST` | FastAPI bind host | `127.0.0.1` |
| `NRC_PORT` | FastAPI bind port | `8080` |
| `NEXT_PUBLIC_BACKEND_URL` | Backend URL the web app proxies to | `http://localhost:8080` |

> Keep `NRC_HOST=127.0.0.1` (loopback) in production and let the reverse proxy reach it —
> the API should never bind a public interface directly. See [05-firewall-ports](05-firewall-ports.md).

---

## Secrets management

**`.env` is injected out-of-band on the server — never via git.** The client repo is
mirrored from the personal machine with tracked files only; `.env`, `.venv`, and `data/`
never leave the dev box.

Placing `.env` on the server:

```bash
# Option A — scp the prepared file (never commit it anywhere)
scp .env.production user@server:/opt/nimb-ace/nep-trade-analytics/.env
ssh user@server 'chmod 600 /opt/nimb-ace/nep-trade-analytics/.env'

# Option B — a secrets manager (Vault / SSM / Doppler) renders .env at boot
```

File permissions and hygiene:
- `chmod 600 .env` and own it as the service user. It must not be world/group readable.
- Confirm it is git-ignored: `git check-ignore .env` should print `.env`.
- Do **not** place `.env` inside any directory the sync script copies (it only ships
  tracked, non-ignored files — `.env` is neither, so it is safe by construction).

Rotation notes:
- **MinIO root creds** (`MINIO_ROOT_USER/PASSWORD`) — rotate away from `minioadmin`
  immediately; give the app a scoped service account instead ([07-minio-hardening](07-minio-hardening.md)).
- **Postgres password** — change `POSTGRES_PASSWORD` **and** `POSTGRES_URL` together, then
  `ALTER ROLE nepse PASSWORD '…'` in the DB and restart the app.
- **`GCP_VERTEX_API_KEY`, `SMTM_PASSWORD`, `NOTIFICATIONS_API_KEY`** — rotate at the
  provider, update `.env`, restart the API + Dagster. No code change needed.
- After any rotation: restart the affected processes and run `make verify` +
  `curl localhost:8080/ready`.
