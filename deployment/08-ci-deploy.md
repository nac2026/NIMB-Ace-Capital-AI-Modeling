# 08 — Release flow & server deploy

How code gets from the developer's laptop to the production server.

```
 Personal repo (source of truth)            Client repo                Server
 YarshaLabs/nep-trade-analytics             nac2026/NIMB-Ace-…          (checkout of client dev)
 branch: dev                                branch: dev
      │  develop + verify                        │                          │
      │  make check / make verify                │                          │
      ▼                                          ▼                          ▼
  ../sync-to-client.sh "msg"  ───────────►  one snapshot commit  ──git──►  git pull + deploy
                                            pushed to origin/dev            (steps below)
```

---

## Step 1 — Develop + verify (personal repo)

Work happens in the personal repo on branch `dev`. Before shipping:

```bash
make check          # ruff lint + pytest
make verify         # infra connectivity (Docker must be up)
# smoke-test the app locally (API /health /ready, web, a chat query)
```

---

## Step 2 — Sync to the client repo

`../sync-to-client.sh` (in the parent folder, `/Users/sudipadh/Desktop/PERSONAL/NIMB/`)
mirrors the **personal working tree** into the client repo and pushes **one snapshot
commit** to the client's `dev` branch. It:

- copies **only tracked + non-ignored files** — so `.env`, `.venv/`, `data/`, caches, and
  Dagster tmp dirs **never** leave the personal machine;
- runs a **secret scan** that aborts if any `.env` secret value appears in the files about
  to be committed;
- fetches and resets the client `dev` to `origin/dev`, mirrors the tree, commits, pushes;
- pushes to `dev` **only** — never `main`.

```bash
# from /Users/sudipadh/Desktop/PERSONAL/NIMB/
CLIENT_SSH_KEY=~/.ssh/personal ./sync-to-client.sh "release: internal uploads + surveillance source"
```

The `~/.ssh/personal` key is required — the default key lacks access to the client remote.
Useful variants:

```bash
./sync-to-client.sh --dry-run "msg"      # mirror + stage + show diff, no commit/push
./sync-to-client.sh --no-push "msg"      # commit locally in the client repo, push later
```

The client repo keeps its own history; each sync is one commit on `dev`. The commit message
defaults to `sync from nep-trade-analytics @ <short-sha>` if omitted.

---

## Step 3 — Deploy on the server

On the server, in the checked-out **client** repo on branch `dev`
(e.g. `/opt/nimb-ace/nep-trade-analytics`):

### 3.1 Pull the release

```bash
git fetch origin && git checkout dev && git pull --ff-only origin dev
```

### 3.2 Ensure `.env` is present and current

`.env` is **never** in git — inject it out-of-band and confirm it exists with mode 600
([02-environment](02-environment.md)). Add any new keys this release introduced
(e.g. `MINIO_BUCKET_UPLOADS`, `NRC_INTERNAL_TRADES_BACKEND`) by diffing against
`.env.example`:

```bash
diff <(grep -oE '^[A-Z_]+=' .env.example | sort) \
     <(grep -oE '^[A-Z_]+=' .env         | sort)
```

### 3.3 Python deps

```bash
make sync           # = uv sync  (installs all workspace members into .venv)
```

### 3.4 Web build

```bash
cd services/web && npm install && npm run build && cd ../..
```

### 3.5 Database migrations

Migrations are **plain SQL files in `infra/postgres/schema/*.sql`**, applied in filename
order and recorded in a `schema_migrations` table (a tiny idempotent runner — no Alembic).
Apply pending ones with:

```bash
uv run nrc-process apply-schema
```

This applies only files not yet recorded, inside a transaction each, and prints the
newly-applied versions. It is safe to run on every deploy — already-applied migrations are
skipped.

> The repo-root `migrations/` folder is an empty scaffold placeholder (`.gitkeep`); the
> **actual** migrations live in `infra/postgres/schema/`. On a brand-new Postgres data dir,
> `infra/postgres/init.sql` also runs once at container init to create the base schema +
> enable `pgvector` ([03-infrastructure](03-infrastructure.md)).

### 3.6 dbt (Gold layer)

```bash
make dbt-deps       # one-time / when packages change (dbt_utils etc.)
make dbt-parse      # regenerate the dbt manifest (Dagster reads it)
make dbt-build      # dbt run + dbt test on every Gold model
```

### 3.7 Restart the app services

```bash
sudo systemctl restart nimb-api nimb-web nimb-dagster
# or: pm2 restart nimb-api nimb-web nimb-dagster
```

Restart order after infra is up: **API → Dagster → web** ([10-runbook](10-runbook.md)).

### 3.8 Post-deploy verification

```bash
make verify                                  # MinIO / Postgres / Redis reachable
curl -fsS http://127.0.0.1:8080/health       # {"status":"ok"}
curl -fsS http://127.0.0.1:8080/ready        # {"status":"ok","checks":{"postgres":true}}
curl -fsS http://127.0.0.1:8080/api/universe | python3 -m json.tool | head
# uploads/surveillance smoke test: see 06-file-uploads-and-surveillance.md
```

Load the web app through the `:443` proxy and send a chat query + open the surveillance
board to confirm the full stack.

---

## One-shot deploy script (optional)

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/nimb-ace/nep-trade-analytics
git fetch origin && git checkout dev && git pull --ff-only origin dev
make sync
( cd services/web && npm install && npm run build )
uv run nrc-process apply-schema
make dbt-deps && make dbt-parse && make dbt-build
sudo systemctl restart nimb-api nimb-web nimb-dagster
sleep 5
make verify
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/ready
echo "✔ deploy complete"
```

Rollback: revert to the previous client `dev` commit and redeploy — see
[10-runbook](10-runbook.md).
