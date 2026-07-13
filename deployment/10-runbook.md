# 10 — Day-2 operations runbook

Start/stop order, where the logs are, common failures with fixes, and rollback. Keep this
open during incidents.

---

## Start / stop / restart order

**Infra must be up before the app processes** (the API's `/ready`, Dagster's scans, and
uploads all depend on MinIO + Postgres).

### Start (cold boot)

```bash
# 1) Infrastructure (containers)
make up
make verify                          # confirm MinIO / Postgres / Redis healthy

# 2) API
sudo systemctl start nimb-api
curl -fsS http://127.0.0.1:8080/ready

# 3) Dagster (pipelines / surveillance scans)
sudo systemctl start nimb-dagster

# 4) Web (last — it fronts the API)
sudo systemctl start nimb-web
```

### Stop (reverse order)

```bash
sudo systemctl stop nimb-web nimb-dagster nimb-api
make down                            # stop containers, KEEP data
```

### Restart just the app tier (e.g. after a deploy)

```bash
sudo systemctl restart nimb-api nimb-dagster nimb-web
```

> `make down` keeps `./data`. `make clean` **destroys** it — never in production without a
> verified backup ([09-backup-restore](09-backup-restore.md)).

---

## Where the logs are

| Component | Logs |
|-----------|------|
| API (`nimb-api`) | `journalctl -u nimb-api -f` (or `pm2 logs nimb-api`) |
| Web (`nimb-web`) | `journalctl -u nimb-web -f` |
| Dagster (`nimb-dagster`) | `journalctl -u nimb-dagster -f`; per-run logs in the Dagster UI (`:3001`, via SSH tunnel) |
| Containers | `make logs` (= `docker compose logs -f --tail=200`), or `docker compose logs <svc>` |
| MinIO / Postgres / Redis | `docker compose logs minio` / `postgres` / `redis` |

Set `LOG_LEVEL=DEBUG` in `.env` and restart the API for verbose app logs.

---

## Health checks at a glance

```bash
make ps                                      # containers Up (healthy)
make verify                                  # MinIO / Postgres / Redis reachable
curl -fsS localhost:8080/health              # {"status":"ok"}   — liveness
curl -fsS localhost:8080/ready               # {"status":"ok","checks":{"postgres":true}}  — readiness
curl -fsS localhost:8080/api/pipeline/tradebook-files   # surveillance source visibility
```

---

## Common failures & fixes

### MinIO down → uploads 502 and `tradebook_job` fails

- **Symptom:** `POST /api/internal/uploads` (and list/download) return **502 "object
  storage unavailable"**. The surveillance scan (`tradebook_job` → `bronze_internal_trades`)
  fails loud with:
  `no trade-book files under 'internal-trade-data/' in bucket 'nrc-internal-uploads' — upload via /internal/file/uploads first.`
- **Diagnose:** `make ps` (is `nrc_minio` healthy?), `docker compose logs minio`,
  `make verify`.
- **Fix:** `docker compose up -d minio` (or `make up`); wait for healthy; retry.
- **Note:** the same error text appears when MinIO is **up but the uploads bucket is
  empty** — the fix there is to upload a trade-book file for the date first
  ([06-file-uploads-and-surveillance](06-file-uploads-and-surveillance.md)), not to restart
  MinIO. Check `/api/pipeline/tradebook-files` `count` to tell them apart.

### Postgres down → `/ready` fails

- **Symptom:** `curl /ready` returns non-ok / `"postgres":false`; chat data endpoints error.
  `/health` (liveness) may still be `ok`.
- **Diagnose:** `docker compose ps postgres`, `docker compose logs postgres`, `make verify`
  (Postgres line ✗).
- **Fix:** `docker compose up -d postgres`; wait for `healthy`; the API recovers on the next
  `/ready`. Confirm `.env` `POSTGRES_URL` matches `POSTGRES_USER/PASSWORD/DB`.

### Wrong `NRC_INTERNAL_TRADES_BACKEND`

- **Symptom:** in production, the scan reads an empty/absent local folder instead of MinIO
  (or vice-versa in dev). `/api/pipeline/tradebook-files` shows `dir` as a local path when
  it should be `minio://…`.
- **Fix:** set `NRC_INTERNAL_TRADES_BACKEND=minio` in `.env` and **restart both the API and
  Dagster** (the API's `tradebook-files` endpoint and the Dagster asset read the same
  toggle — they must agree). `local` is offline-dev only.

### Redis down

- **Symptom:** conversation memory lost / errors on `/chat` session ops. Non-fatal to data
  endpoints.
- **Fix:** `docker compose up -d redis`. It's a cache; state rebuilds.

### Web app blank / API errors in browser

- **Fix:** confirm `nimb-api` is up (`/health`), and `NEXT_PUBLIC_BACKEND_URL` points at the
  API. Check the nginx proxy for `/api/*` ([04-services](04-services.md)).

### 429 from the LLM (Vertex quota)

- **Fix:** attach billing to the GCP project, or wait — the client retries with backoff.
  Verify `GCP_VERTEX_API_KEY` is set.

### Dagster job won't launch from the board

- **Symptom:** "Load new trade-book data" button says "Launch failed — is Dagster running?"
- **Fix:** ensure `nimb-dagster` is running (`systemctl status nimb-dagster`); the API POSTs
  to Dagster to launch `tradebook_job`.

---

## Rollback

Deploys are snapshot commits on the client `dev` branch, so rollback = check out the
previous commit and redeploy.

```bash
cd /opt/nimb-ace/nep-trade-analytics
git fetch origin
git log --oneline origin/dev | head        # find the last-good commit SHA
git checkout dev && git reset --hard <last-good-sha>   # or: git checkout <sha>

make sync
( cd services/web && npm install && npm run build )
uv run nrc-process apply-schema            # migrations are additive/idempotent; safe to re-run
make dbt-parse && make dbt-build
sudo systemctl restart nimb-api nimb-dagster nimb-web
make verify && curl -fsS localhost:8080/ready
```

Cautions:
- **Schema migrations are forward-only** (no down-migrations). Rolling *code* back is safe;
  rolling the *DB* back is not automatic. If a bad migration is the problem, fix forward
  with a new migration file rather than reverting the DB, and restore from backup only as a
  last resort ([09-backup-restore](09-backup-restore.md)).
- **Data is untouched by rollback.** `./data` and MinIO buckets are not reverted — only code
  + schema application.

For a clean re-sync of a prior release from the personal repo instead, re-run
`../sync-to-client.sh` from the corresponding personal-repo state ([08-ci-deploy](08-ci-deploy.md)).
