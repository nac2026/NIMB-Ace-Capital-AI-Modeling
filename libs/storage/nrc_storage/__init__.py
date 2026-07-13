"""Storage clients — MinIO, Delta (via delta-rs), Postgres, Redis."""
from __future__ import annotations

__version__ = "0.1.0"

from .config import StorageSettings, get_settings
from .delta_io import DeltaIO, WriteMode
from .minio_client import MinIOClient
from .postgres_client import PostgresClient
from .redis_client import RedisClient
from .uploads import (
    ALLOWED_EXTENSIONS,
    INTERNAL_TRADES_CATEGORY,
    UPLOAD_CATEGORIES,
    UploadRecord,
    UploadStore,
)

__all__ = [
    "StorageSettings",
    "get_settings",
    "MinIOClient",
    "DeltaIO",
    "WriteMode",
    "PostgresClient",
    "RedisClient",
    "UploadStore",
    "UploadRecord",
    "UPLOAD_CATEGORIES",
    "INTERNAL_TRADES_CATEGORY",
    "ALLOWED_EXTENSIONS",
]
