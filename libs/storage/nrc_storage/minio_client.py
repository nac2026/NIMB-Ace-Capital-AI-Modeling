"""Thin MinIO (S3-compatible) client for raw-snapshot storage.

Delta tables bypass this and use deltalake directly (see delta_io.py).
This client is for everything else: raw HTML/JSON/CSV snapshots, large binary
artifacts, presigned URLs for UI download, etc."""
from __future__ import annotations
from collections.abc import Iterator
from io import BytesIO
from typing import TYPE_CHECKING

import boto3
from botocore.client import Config

from .config import StorageSettings, get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client


class MinIOClient:
    """Object-storage client. Scoped to one bucket by default but accepts overrides."""

    def __init__(self, settings: StorageSettings | None = None, *, bucket: str | None = None):
        self._settings = settings or get_settings()
        self._bucket = bucket or self._settings.minio_bucket_snapshots
        self._s3: S3Client = boto3.client(
            "s3",
            endpoint_url=self._settings.minio_endpoint,
            aws_access_key_id=self._settings.minio_root_user,
            aws_secret_access_key=self._settings.minio_root_password,
            region_name=self._settings.minio_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload raw bytes. Returns the s3:// URI."""
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        return f"s3://{self._bucket}/{key}"

    def get_bytes(self, key: str) -> bytes:
        """Download an object as bytes."""
        resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        """True if object exists at key."""
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._s3.exceptions.ClientError:
            return False

    def list_keys(self, prefix: str = "", limit: int | None = None) -> Iterator[str]:
        """Stream keys matching a prefix. Paginated server-side."""
        paginator = self._s3.get_paginator("list_objects_v2")
        count = 0
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]
                count += 1
                if limit is not None and count >= limit:
                    return

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a time-limited HTTP URL for GET access to the object."""
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def ensure_bucket(self) -> None:
        """Create the bucket if it doesn't exist. Idempotent."""
        try:
            self._s3.head_bucket(Bucket=self._bucket)
        except self._s3.exceptions.ClientError:
            self._s3.create_bucket(Bucket=self._bucket)

    def put_stream(self, key: str, stream: BytesIO, content_type: str = "application/octet-stream") -> str:
        """Upload from a file-like object (e.g. tempfile or download stream)."""
        self._s3.upload_fileobj(stream, self._bucket, key, ExtraArgs={"ContentType": content_type})
        return f"s3://{self._bucket}/{key}"
