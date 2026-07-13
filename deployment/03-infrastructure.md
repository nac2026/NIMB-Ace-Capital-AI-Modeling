# 03 — Infrastructure (Docker Compose)

The stateful backing services — **MinIO, Postgres/pgvector, Redis** — run as Docker
containers defined in `docker-compose.yml`. The app services (web, API, Dagster, dbt-docs)
and DuckDB compute do **not**; they run as host processes ([04-services](04-services.md)).

Prereq: `.env` is in place ([02-environment](02-environment.md)).

---

## Bring it up

```bash
make up          # = docker compose up -d  (then prints console/creds hints)
```

Or directly:

```bash
docker compose up -d
```

Check status:

```bash
make ps          # = docker compose ps
```

Expected — three long-running services healthy, plus the one-shot setter exited cleanly:

```
NAME               STATUS
nrc_minio          Up (healthy)
nrc_minio_setup    Exited (0)      ← one-shot: creates buckets, then exits
nrc_postgres       Up (healthy)
nrc_redis          Up (healthy)
```

---

## What each container is

| Container | Image | Port(s) | Role |
|-----------|-------|---------|------|
| `nrc_minio` | `minio/minio:latest` | 9000 (S3 API), 9001 (console) | Object store: Delta lakehouse + raw snapshots + internal uploads |
| `nrc_minio_setup` | `minio/mc:latest` | — | **One-shot** bucket creator; runs after MinIO is healthy, then exits `0` |
| `nrc_postgres` | `pgvector/pgvector:pg16` | 5432 | Serving DB + audit log + pgvector; runs `infra/postgres/init.sql` on first start |
| `nrc_redis` | `redis:7-alpine` | 6379 | Conversation-memory cache; AOF persistence, 200 MB `allkeys-lru` |

`restart: unless-stopped` is set on MinIO/Postgres/Redis, so they come back after a reboot.
`minio-setup` is `restart: "no"` — it is meant to exit.

---

## MinIO bucket provisioning

The `minio-setup` sidecar waits for MinIO to report healthy, then creates **three buckets**
idempotently (`mc mb --ignore-existing`) and marks them private (`mc anonymous set none`):

| Bucket | Env var (default) | Contents | Access |
|--------|-------------------|----------|--------|
| `nepse-lakehouse` | `MINIO_BUCKET_LAKEHOUSE` | Delta Lake tables (Bronze/Silver/Gold) | private |
| `raw-snapshots` | `MINIO_BUCKET_SNAPSHOTS` | Raw scraper output | private |
| `nrc-internal-uploads` | `MINIO_BUCKET_UPLOADS` | **In-app internal file uploads** (trade-book xlsx + strategy docs) | **private** |

You do not create buckets by hand. If you change a bucket name in `.env`, `make down &&
make up` re-runs the setter for the new name. The uploads bucket underpins
[06-file-uploads-and-surveillance](06-file-uploads-and-surveillance.md).

> **Security:** the MinIO console (`:9001`) and S3 API (`:9000`) are **internal-only** in
> production. End users never touch MinIO — they use the in-app upload page. Lock the
> ports down per [05-firewall-ports](05-firewall-ports.md) and harden creds per
> [07-minio-hardening](07-minio-hardening.md).

---

## Data volumes — where state lives

All persistent state is **bind-mounted under `./data/`** at the repo root (not named
Docker volumes), so it survives `make down` and is easy to back up:

| Path | Container | Contents |
|------|-----------|----------|
| `./data/minio` | `nrc_minio:/data` | All MinIO buckets/objects |
| `./data/postgres` | `nrc_postgres:/var/lib/postgresql/data` | Postgres data directory |
| `./data/redis` | `nrc_redis:/data` | Redis AOF |

Postgres also mounts `infra/postgres/init.sql` read-only as
`/docker-entrypoint-initdb.d/10-init.sql` — it runs **once**, on an empty data dir, to
create the schema and enable `pgvector`. Incremental schema changes are applied separately
via `uv run nrc-process apply-schema` (see [08-ci-deploy](08-ci-deploy.md)).

Back these up per [09-backup-restore](09-backup-restore.md).

---

## Stop / restart / destroy

```bash
make down        # stop containers, KEEP ./data volumes
make restart     # docker compose restart (no data loss)
make logs        # tail all container logs (-f --tail=200)
```

```bash
make clean       # ⚠️ DESTRUCTIVE: docker compose down -v AND rm -rf data/{minio,postgres,redis}
```

> `make clean` wipes **all** infra data including the uploads bucket and Postgres serving
> state. Never run it in production without a verified backup — the uploads bucket and
> Postgres are **not** regenerable ([09-backup-restore](09-backup-restore.md)).

---

## Verify connectivity

```bash
make verify      # = uv run python scripts/verify_infra.py
```

It prints one line per service and exits non-zero if any fail:

```
Infra check
  ✓ MinIO     live at http://localhost:9000
  ✓ Postgres  PostgreSQL 16.x, extensions: ['pg_trgm', 'vector']
  ✓ Redis     localhost:6379 PONG
```

The Postgres check also confirms the `vector` and `pg_trgm` extensions are present — if
they're missing, the init SQL didn't run (fresh data dir needed) or migrations are
incomplete. Continue to [04-services](04-services.md) to start the app.
