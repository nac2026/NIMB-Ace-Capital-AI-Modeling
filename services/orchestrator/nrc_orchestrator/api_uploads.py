"""Internal file-uploads API — in-app replacement for dropping files on disk or
handing users the MinIO console.

Endpoints:
  POST   /api/internal/uploads            multipart upload → MinIO
  GET    /api/internal/uploads            list stored files (optionally by category/date)
  GET    /api/internal/uploads/categories allowed categories + extensions (UI dropdown)
  GET    /api/internal/uploads/download   proxied download of one object
  DELETE /api/internal/uploads            delete one object by key

Files land in the `minio_bucket_uploads` bucket keyed `{category}/{date}/{name}`
(see nrc_storage.uploads.UploadStore). Downloads are proxied through this API
rather than via presigned URLs, so MinIO stays firewalled/internal in prod.

Endpoints are sync `def` on purpose: FastAPI runs them in a threadpool, so the
blocking boto3 upload/download calls never stall the event loop."""
from __future__ import annotations

import io
import logging
from datetime import date, datetime

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from nrc_storage import ALLOWED_EXTENSIONS, UPLOAD_CATEGORIES, UploadStore
from pydantic import BaseModel

_log = logging.getLogger("nrc_orchestrator.api_uploads")

router = APIRouter(prefix="/api/internal/uploads", tags=["internal-uploads"])

# Downloads are served by this API, not by presigned MinIO URLs (MinIO is
# internal in prod). The frontend builds this same path in lib/api.ts.
_DOWNLOAD_PATH = "/api/internal/uploads/download"


# ─── response shapes ────────────────────────────────────────────────
class UploadItem(BaseModel):
    key: str
    filename: str
    category: str
    date: str
    size: int
    modified_at: datetime | None = None
    download_url: str


class UploadResult(BaseModel):
    key: str
    filename: str
    category: str
    date: str
    replaced: bool


class CategoryInfo(BaseModel):
    category: str
    extensions: list[str]


def _ext(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def _download_url(key: str) -> str:
    from urllib.parse import quote

    return f"{_DOWNLOAD_PATH}?key={quote(key, safe='')}"


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise HTTPException(400, f"invalid date {raw!r}; expected YYYY-MM-DD") from e


@router.get("/categories", response_model=list[CategoryInfo])
def list_categories() -> list[CategoryInfo]:
    return [
        CategoryInfo(category=c, extensions=sorted(ALLOWED_EXTENSIONS.get(c, frozenset())))
        for c in sorted(UPLOAD_CATEGORIES)
    ]


@router.post("", response_model=UploadResult)
def upload_file(
    file: UploadFile = File(...),
    category: str = Form(...),
    date: str | None = Form(None),  # noqa: A002 — matches the form field name
) -> UploadResult:
    if category not in UPLOAD_CATEGORIES:
        raise HTTPException(400, f"unknown category {category!r}; allowed: {sorted(UPLOAD_CATEGORIES)}")
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(400, "missing filename")
    ext = _ext(filename)
    allowed = ALLOWED_EXTENSIONS.get(category, frozenset())
    if ext not in allowed:
        raise HTTPException(400, f"{ext or 'file'} not allowed for {category}; allowed: {sorted(allowed)}")

    on_date = _parse_date(date)
    try:
        rec = UploadStore().put(
            category, filename, file.file, content_type=file.content_type, on_date=on_date
        )
    except (ClientError, BotoCoreError) as e:
        _log.exception("MinIO upload failed")
        raise HTTPException(502, f"object storage unavailable: {e}") from e
    return UploadResult(
        key=rec.key, filename=rec.filename, category=rec.category, date=rec.date, replaced=rec.replaced
    )


@router.get("", response_model=list[UploadItem])
def list_files(
    category: str | None = Query(None),
    date: str | None = Query(None),  # noqa: A002
) -> list[UploadItem]:
    if category is not None and category not in UPLOAD_CATEGORIES:
        raise HTTPException(400, f"unknown category {category!r}")
    on_date = _parse_date(date)
    try:
        records = UploadStore().list(category, on_date)
    except (ClientError, BotoCoreError) as e:
        _log.exception("MinIO list failed")
        raise HTTPException(502, f"object storage unavailable: {e}") from e
    return [
        UploadItem(
            key=r.key, filename=r.filename, category=r.category, date=r.date,
            size=r.size, modified_at=r.modified_at, download_url=_download_url(r.key),
        )
        for r in records
    ]


@router.get("/download")
def download_file(key: str = Query(...)) -> StreamingResponse:
    store = UploadStore()
    try:
        data = store.get_bytes(key)  # validates key ∈ allowed category
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except (ClientError, BotoCoreError) as e:
        _log.exception("MinIO download failed")
        raise HTTPException(502, f"object storage unavailable: {e}") from e
    filename = key.rsplit("/", 1)[-1]
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("")
def delete_file(key: str = Query(...)) -> dict[str, str]:
    try:
        UploadStore().delete(key)  # validates key ∈ allowed category
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except (ClientError, BotoCoreError) as e:
        _log.exception("MinIO delete failed")
        raise HTTPException(502, f"object storage unavailable: {e}") from e
    return {"status": "deleted", "key": key}
