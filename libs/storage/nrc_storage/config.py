"""Storage-layer settings. Single source of truth for MinIO/Postgres/Redis connection info.

Reads from environment (or a .env file at the project root). Downstream clients
take a Settings instance by dependency injection — no module-level globals, no
scattered os.getenv calls."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = three parents up from this file (libs/storage/nrc_storage/config.py -> NRC/).
_REPO_ROOT = Path(__file__).resolve().parents[3]


class StorageSettings(BaseSettings):
    """Connection settings for every storage backend in the stack."""
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MinIO / S3-compatible object store.
    minio_endpoint: str = Field(default="http://localhost:9000")
    minio_root_user: str = Field(default="minioadmin")
    minio_root_password: str = Field(default="minioadmin")
    minio_region: str = Field(default="us-east-1")
    minio_bucket_lakehouse: str = Field(default="nepse-lakehouse")
    minio_bucket_snapshots: str = Field(default="raw-snapshots")

    # Postgres.
    postgres_url: str = Field(default="postgresql://nepse:nepse@localhost:5432/nepse")
    postgres_pool_min: int = Field(default=1, ge=0)
    postgres_pool_max: int = Field(default=5, ge=1)

    # Redis.
    redis_url: str = Field(default="redis://localhost:6379/0")

    @property
    def lakehouse_uri(self) -> str:
        """s3://{bucket}/ — the root URI of the Delta lakehouse."""
        return f"s3://{self.minio_bucket_lakehouse}/"

    def delta_storage_options(self) -> dict[str, str]:
        """Storage options dict for deltalake + boto3 against MinIO.

        `AWS_ALLOW_HTTP` + `AWS_S3_ALLOW_UNSAFE_RENAME` are required for local
        S3-compatible stores that don't support TLS or atomic rename."""
        return {
            "AWS_ENDPOINT_URL": self.minio_endpoint,
            "AWS_ACCESS_KEY_ID": self.minio_root_user,
            "AWS_SECRET_ACCESS_KEY": self.minio_root_password,
            "AWS_REGION": self.minio_region,
            "AWS_ALLOW_HTTP": "true",
            "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
        }


@lru_cache(maxsize=1)
def get_settings() -> StorageSettings:
    """Cached settings singleton. Tests can clear the cache via get_settings.cache_clear()."""
    return StorageSettings()
