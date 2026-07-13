# 06 — Internal file uploads & the surveillance scan

This release replaces "drop files on a server folder / hand users the MinIO console" with
an **in-app upload page** that streams files to a private MinIO bucket, and a
**surveillance scan** that reads the firm's trade-book from that bucket. This doc covers
the flow end to end in production.

Related config: `MINIO_BUCKET_UPLOADS`, `NRC_INTERNAL_TRADES_BACKEND`
([02-environment](02-environment.md)); bucket provisioning ([03-infrastructure](03-infrastructure.md)).

---

## The end-to-end flow

```
 User (browser, via :443 reverse proxy)
   │  opens the "Internal Files" module → /internal/file/uploads
   │  picks a CATEGORY + a DATE, selects a file
   ▼
 FastAPI API  POST /api/internal/uploads   (multipart: file, category, date)
   │  validates category ∈ allow-list, extension ∈ per-category allow-list
   │  streams bytes to MinIO  (blocking boto3 in a threadpool)
   ▼
 MinIO bucket  nrc-internal-uploads
   key = {category}/{YYYY-MM-DD}/{filename}
   e.g.  internal-trade-data/2026-07-13/Trade_Book_Details_2026-07-13.xlsx
   ▼
 Surveillance scan  (Dagster tradebook_job → bronze_internal_trades asset)
   │  NRC_INTERNAL_TRADES_BACKEND=minio → download every *.xlsx under
   │  the `internal-trade-data/` prefix into a temp dir, then ingest →
   │  bronze.internal_trades_raw → silver → internal-surveillance Gold → Postgres
   ▼
 Surveillance board (web app)  ← results, cases, alerts
```

The user triggers the scan from the surveillance board's **"Load new trade-book data"**
button, which POSTs `/api/pipeline/refresh {jobs:["tradebook_job"]}` and polls
`/api/pipeline/status`. The button's caption shows the file count from
`/api/pipeline/tradebook-files`.

---

## Categories & allowed file types

Defined in `libs/storage/nrc_storage/uploads.py`. Uploads are scoped to an allow-list of
categories, each with an allow-list of extensions:

| Category | Allowed extensions | Feeds the surveillance scan? |
|----------|--------------------|------------------------------|
| `internal-trade-data` | `.xlsx` only | **Yes** — the only category the scan reads |
| `strategic-plans` | `.pdf .docx .xlsx .csv .txt` | No (stored for reference) |
| `goals-and-strategy` | `.pdf .docx .xlsx .csv .txt` | No (stored for reference) |

Only `internal-trade-data` is ingested by `tradebook_job`; the trade-book xlsx are the
firm's own executed fills (`bronze.internal_trades_raw`), joined to floorsheet downstream
to recover broker/counterparty for surveillance.

---

## Why MinIO is not exposed and downloads are API-proxied

- **Console/S3 stay internal.** Exposing `:9001`/`:9000` would hand users (or attackers)
  the whole object store — every bucket, root-level. Instead the app is the only client,
  and it is scoped to the uploads bucket + the category allow-list ([07-minio-hardening](07-minio-hardening.md)).
- **Downloads are proxied, not presigned.** `GET /api/internal/uploads/download?key=…`
  streams the object **through the API** (`StreamingResponse`) and validates the key
  belongs to an allowed category. There are **no presigned MinIO URLs** — nothing points a
  browser at MinIO directly, so MinIO can stay firewalled.
- **Server-side validation.** The API rejects unknown categories and disallowed
  extensions before anything reaches storage; MinIO failures surface as `502` (object
  storage unavailable), not a stack trace.

---

## Upload API reference

Router prefix `/api/internal/uploads` (`services/orchestrator/nrc_orchestrator/api_uploads.py`):

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/internal/uploads` | Upload one file (multipart: `file`, `category`, optional `date`) |
| `GET` | `/api/internal/uploads` | List stored files (optional `?category=&date=`) |
| `GET` | `/api/internal/uploads/categories` | Allowed categories + extensions (UI dropdown) |
| `GET` | `/api/internal/uploads/download?key=…` | Proxied download of one object |
| `DELETE` | `/api/internal/uploads?key=…` | Delete one object by key |
| `GET` | `/api/pipeline/tradebook-files` | What the scan will ingest (count + files) before launch |

---

## Production checklist

- [ ] `NRC_INTERNAL_TRADES_BACKEND=minio` (never `local` in prod).
- [ ] `nrc-internal-uploads` bucket exists (auto-created by `minio-setup`) and is private.
- [ ] MinIO `:9000/:9001` firewalled ([05-firewall-ports](05-firewall-ports.md)).
- [ ] Reverse-proxy `client_max_body_size` large enough for the biggest trade-book xlsx.
- [ ] App uses a scoped MinIO service account, not root ([07-minio-hardening](07-minio-hardening.md)).

---

## Smoke test (curl)

Run against the **internal** API (`127.0.0.1:8080`) on the server, or through the proxy.
Use a small real `.xlsx` for the trade-book category (only `.xlsx` is allowed there).

```bash
API=http://127.0.0.1:8080
DATE=2026-07-13

# 1) Confirm allowed categories/extensions
curl -fsS "$API/api/internal/uploads/categories" | python3 -m json.tool

# 2) Upload a trade-book file (multipart)
curl -fsS -X POST "$API/api/internal/uploads" \
  -F "file=@./Trade_Book_Details_${DATE}.xlsx" \
  -F "category=internal-trade-data" \
  -F "date=${DATE}" | python3 -m json.tool
# → {"key":"internal-trade-data/2026-07-13/Trade_Book_Details_2026-07-13.xlsx", ..., "replaced":false}

# 3) List what's stored for that category/date
curl -fsS "$API/api/internal/uploads?category=internal-trade-data&date=${DATE}" \
  | python3 -m json.tool

# 4) Confirm the scan will see it (source is MinIO because backend=minio)
curl -fsS "$API/api/pipeline/tradebook-files" | python3 -m json.tool
# → {"dir":"minio://nrc-internal-uploads/internal-trade-data/","count":1,"files":[...]}

# 5) (optional) Launch the surveillance scan
curl -fsS -X POST "$API/api/pipeline/refresh" \
  -H "Content-Type: application/json" \
  -d '{"jobs":["tradebook_job"]}' | python3 -m json.tool
# then poll:
curl -fsS "$API/api/pipeline/status" | python3 -m json.tool
```

If step 4 returns `count: 0`, the scan will **fail loud** with
`no trade-book files under 'internal-trade-data/' in bucket 'nrc-internal-uploads' — upload
via /internal/file/uploads first.` Upload a file first. See [10-runbook](10-runbook.md) for
failure handling.
