# 09 — Backup & restore

What to back up, how, and how to restore. The guiding rule:

> **Source-of-truth (back these up):** the `nrc-internal-uploads` MinIO bucket and the
> Postgres serving state. These are **not** regenerable — losing them loses uploaded
> trade-book/strategy files and serving/audit/surveillance state.
>
> **Regenerable (nice to have):** the Delta **Gold** layer in `nepse-lakehouse` can be
> rebuilt from Bronze/Silver via the pipeline; `raw-snapshots` is scraper output. Bronze/
> Silver themselves derive from client CSVs — keep those upstream sources safe too.

Everything persistent lives under `./data/` (bind mounts) plus MinIO's internal buckets.

---

## What to back up

| Target | Where | Source of truth? | Method |
|--------|-------|:---:|--------|
| Postgres DB | `nrc_postgres` container / `./data/postgres` | **Yes** | `pg_dump` (logical) |
| `nrc-internal-uploads` bucket | MinIO | **Yes** | `mc mirror` |
| `nepse-lakehouse` bucket (Delta) | MinIO | Gold regenerable; Bronze/Silver keep | `mc mirror` |
| `raw-snapshots` bucket | MinIO | Regenerable | optional `mc mirror` |
| `.env` | repo root (git-ignored) | **Yes** (secrets) | store in your secrets manager, offline |

---

## Postgres — pg_dump / pg_restore

Run against the container. Creds come from `.env` (`POSTGRES_USER/DB`).

### Backup

```bash
# Custom-format dump (compressed, supports selective restore)
docker exec -t nrc_postgres \
  pg_dump -U "${POSTGRES_USER:-nepse}" -d "${POSTGRES_DB:-nepse}" -Fc \
  > backups/nepse_$(date +%F_%H%M).dump

# Or plain SQL
docker exec -t nrc_postgres \
  pg_dump -U "${POSTGRES_USER:-nepse}" -d "${POSTGRES_DB:-nepse}" \
  | gzip > backups/nepse_$(date +%F_%H%M).sql.gz
```

### Restore

```bash
# Custom-format dump → restore into the (existing, empty) DB
cat backups/nepse_2026-07-13_2000.dump \
  | docker exec -i nrc_postgres \
      pg_restore -U "${POSTGRES_USER:-nepse}" -d "${POSTGRES_DB:-nepse}" --clean --if-exists

# Plain SQL restore
gunzip -c backups/nepse_2026-07-13_2000.sql.gz \
  | docker exec -i nrc_postgres psql -U "${POSTGRES_USER:-nepse}" -d "${POSTGRES_DB:-nepse}"
```

For a fully fresh DB, ensure `pgvector` is available (the `pgvector/pgvector:pg16` image
provides it; `infra/postgres/init.sql` enables the extension on init). After restore, run
`uv run nrc-process apply-schema` to reconcile any migrations, then `make verify`.

---

## MinIO buckets — mc mirror

Use the `mc` client with an admin/backup alias (see [07-minio-hardening](07-minio-hardening.md)).

### Backup (to another disk / offsite S3)

```bash
mc alias set nimb   http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc alias set backup s3://your-backup-endpoint  <KEY> <SECRET>   # or a local fs alias

# CRITICAL buckets (source of truth)
mc mirror --overwrite nimb/nrc-internal-uploads  backup/nimb/nrc-internal-uploads
# Lakehouse (Gold regenerable, but Bronze/Silver worth keeping)
mc mirror --overwrite nimb/nepse-lakehouse       backup/nimb/nepse-lakehouse
# Optional: raw snapshots (regenerable)
mc mirror --overwrite nimb/raw-snapshots         backup/nimb/raw-snapshots
```

Schedule via cron (e.g. nightly after the EOD pipeline). `mc mirror --remove` keeps an
exact mirror (deletes on the target too) — omit `--remove` for additive backups.

### Restore

```bash
mc mb --ignore-existing nimb/nrc-internal-uploads     # ensure bucket exists
mc mirror --overwrite backup/nimb/nrc-internal-uploads nimb/nrc-internal-uploads
mc mirror --overwrite backup/nimb/nepse-lakehouse      nimb/nepse-lakehouse
```

> **Alternative — filesystem-level.** Since MinIO stores objects under `./data/minio`, you
> can snapshot that directory while MinIO is **stopped** (`make down`) for a crash-consistent
> copy. `mc mirror` is preferred because it works live and is portable across endpoints.

---

## `./data/` volume backup (offline / crash-consistent)

For a whole-stack snapshot, stop infra first so files are quiescent:

```bash
make down
tar czf backups/data_$(date +%F_%H%M).tar.gz data/minio data/postgres data/redis
make up
```

Redis (`data/redis`) is a session cache and is safe to lose (it rebuilds); include it only
for completeness.

---

## Restore procedure (whole stack)

1. Provision the host + software ([01-prerequisites](01-prerequisites.md)) and place `.env`.
2. `make up` to create containers + buckets (`minio-setup` recreates empty buckets).
3. Restore **MinIO uploads + lakehouse** with `mc mirror` (above).
4. Restore **Postgres** with `pg_restore`/`psql` (above), then
   `uv run nrc-process apply-schema`.
5. If serving tables look stale but the lakehouse is fresh, re-sync Gold → Postgres:
   `make dagster-sync` (runs `postgres_sync_job`).
6. Rebuild Gold from Silver if needed: `make dbt-build` (or full pipeline `make dagster-eod`).
7. Start app services, then `make verify` + `curl /health` + `curl /ready`.

---

## Backup checklist

- [ ] Nightly `pg_dump` retained off-box.
- [ ] Nightly `mc mirror` of `nrc-internal-uploads` **and** `nepse-lakehouse` off-box.
- [ ] `.env` stored in a secrets manager (not in any backup tarball in plaintext).
- [ ] A restore has been **tested** end to end at least once.
