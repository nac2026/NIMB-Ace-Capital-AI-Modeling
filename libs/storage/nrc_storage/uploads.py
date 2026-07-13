"""Business-document uploads on MinIO — the single source of truth for the
in-app file-upload feature and the surveillance scan's object-storage source.

Lives in nrc_storage because it is the one package imported by BOTH the
orchestrator API (which serves the upload endpoints + the tradebook-files count)
and the Dagster ingestion process (which pulls trade-book files for the scan).

Key layout (category-first): ``{category}/{YYYY-MM-DD}/{filename}`` in the
``minio_bucket_uploads`` bucket. Category-first means the scan lists exactly one
server-filtered prefix (``internal-trade-data/``); the browse UI reconstructs a
date-grouped tree from the middle path segment."""
from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

from .config import StorageSettings, get_settings
from .minio_client import MinIOClient

# Upload categories exposed to users. Only INTERNAL_TRADES_CATEGORY feeds the
# surveillance scan; the rest are stored for reference / future use. Extend this
# set (and ALLOWED_EXTENSIONS) to add a new folder.
INTERNAL_TRADES_CATEGORY = "internal-trade-data"
UPLOAD_CATEGORIES: frozenset[str] = frozenset(
    {INTERNAL_TRADES_CATEGORY, "strategic-plans", "goals-and-strategy"}
)

# Per-category allowed file extensions (lowercase, with dot). The trade-book scan
# only reads xlsx, so that category is xlsx-only; document categories are broader.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".xlsx", ".csv", ".txt"})
ALLOWED_EXTENSIONS: dict[str, frozenset[str]] = {
    INTERNAL_TRADES_CATEGORY: frozenset({".xlsx"}),
    "strategic-plans": _DOC_EXTENSIONS,
    "goals-and-strategy": _DOC_EXTENSIONS,
}

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class UploadRecord:
    """One stored object. `date` is the YYYY-MM-DD folder derived at upload time."""
    key: str
    filename: str
    category: str
    date: str
    size: int
    modified_at: datetime | None = None
    replaced: bool = False


def validate_category(category: str) -> None:
    if category not in UPLOAD_CATEGORIES:
        raise ValueError(
            f"unknown category {category!r}; allowed: {sorted(UPLOAD_CATEGORIES)}"
        )


def _safe_filename(filename: str) -> str:
    """Reduce to a bare basename and reject path-traversal / empty names."""
    name = os.path.basename((filename or "").strip())
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"invalid filename: {filename!r}")
    return name


def _content_type_for(filename: str, fallback: str | None) -> str:
    if fallback and fallback != "application/octet-stream":
        return fallback
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if filename.lower().endswith(".xlsx"):
        return _XLSX_CONTENT_TYPE
    return "application/octet-stream"


class UploadStore:
    """Category/date-aware wrapper over MinIOClient for the uploads bucket."""

    def __init__(self, settings: StorageSettings | None = None):
        self._settings = settings or get_settings()
        self._client = MinIOClient(self._settings, bucket=self._settings.minio_bucket_uploads)

    @property
    def bucket(self) -> str:
        return self._client.bucket

    def build_key(self, category: str, filename: str, on_date: date | None = None) -> str:
        validate_category(category)
        name = _safe_filename(filename)
        d = on_date or date.today()
        return f"{category}/{d:%Y-%m-%d}/{name}"

    def put(
        self,
        category: str,
        filename: str,
        fileobj: BinaryIO,
        content_type: str | None = None,
        on_date: date | None = None,
    ) -> UploadRecord:
        """Stream `fileobj` to `{category}/{date}/{filename}`. Overwrites on key
        collision (idempotent re-upload of a corrected file)."""
        key = self.build_key(category, filename, on_date)
        name = key.rsplit("/", 1)[-1]
        d = key.split("/", 2)[1]
        replaced = self._client.exists(key)
        self._client.ensure_bucket()
        self._client.put_stream(key, fileobj, _content_type_for(name, content_type))
        # Size is not returned by upload_fileobj; a follow-up head via exists() is
        # unnecessary here — the browse list() reports authoritative sizes.
        return UploadRecord(
            key=key, filename=name, category=category, date=d, size=0, replaced=replaced
        )

    def list(self, category: str | None = None, on_date: date | None = None) -> list[UploadRecord]:
        """List stored objects, newest first. Optionally scope to a category (and date)."""
        if category is not None:
            validate_category(category)
            prefix = f"{category}/"
            if on_date is not None:
                prefix = f"{category}/{on_date:%Y-%m-%d}/"
        else:
            prefix = ""
        records: list[UploadRecord] = []
        for obj in self._client.list_objects(prefix):
            rec = self._parse(obj)
            if rec is not None:
                records.append(rec)
        records.sort(key=lambda r: (r.date, r.filename), reverse=True)
        return records

    def download_category(self, category: str, dest_dir: Path) -> list[Path]:
        """Download every object under `{category}/` into a FLAT dest_dir, named
        `{date}__{filename}` to avoid same-name collisions across date folders
        (the ingest globs a single directory, non-recursively). Returns local paths."""
        validate_category(category)
        dest_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for obj in self._client.list_objects(f"{category}/"):
            rec = self._parse(obj)
            if rec is None:
                continue
            local = dest_dir / f"{rec.date}__{rec.filename}"
            local.write_bytes(self._client.get_bytes(rec.key))
            paths.append(local)
        return paths

    def delete(self, key: str) -> None:
        self._require_allowed_key(key)
        self._client.delete(key)

    def get_bytes(self, key: str) -> bytes:
        self._require_allowed_key(key)
        return self._client.get_bytes(key)

    # -- helpers ----------------------------------------------------------------
    @staticmethod
    def _require_allowed_key(key: str) -> None:
        """Guard download/delete: the key's leading segment must be a known
        category, and it must not escape the prefix."""
        if ".." in key.split("/") or key.startswith("/"):
            raise ValueError(f"invalid key: {key!r}")
        top = key.split("/", 1)[0]
        validate_category(top)

    @staticmethod
    def _parse(obj: dict) -> UploadRecord | None:
        """Turn a raw {key,size,last_modified} into an UploadRecord; skip
        anything that isn't a `{category}/{date}/{file}` object (e.g. folder markers)."""
        key = obj["key"]
        parts = key.split("/")
        if len(parts) < 3 or not parts[-1]:
            return None
        category, d, filename = parts[0], parts[1], parts[-1]
        if category not in UPLOAD_CATEGORIES:
            return None
        return UploadRecord(
            key=key,
            filename=filename,
            category=category,
            date=d,
            size=int(obj.get("size", 0)),
            modified_at=obj.get("last_modified"),
        )
