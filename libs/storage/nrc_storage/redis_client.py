"""Redis client for cache + rate-limit primitives.

Semantic caching of LLM responses and intent classifications lives here.
Pgvector stores the embedding; Redis stores the query -> trace_id map for
O(1) lookups and TTL-driven expiry."""
from __future__ import annotations
import json
from typing import Any

import redis

from .config import StorageSettings, get_settings


class RedisClient:
    """Thin wrapper. JSON (de)serialization built in; binary ops use .raw."""

    def __init__(self, settings: StorageSettings | None = None):
        self._settings = settings or get_settings()
        self.raw: redis.Redis = redis.Redis.from_url(
            self._settings.redis_url,
            decode_responses=True,
        )

    def get_json(self, key: str) -> Any | None:
        """Fetch + json.loads. Returns None if key missing."""
        payload = self.raw.get(key)
        if payload is None:
            return None
        return json.loads(payload)

    def set_json(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        """json.dumps + SET [EX ttl]. Default: no expiry."""
        self.raw.set(key, json.dumps(value, default=str), ex=ttl_seconds)

    def delete(self, *keys: str) -> int:
        """Delete one or more keys. Returns count removed."""
        if not keys:
            return 0
        return int(self.raw.delete(*keys))

    def incr(self, key: str, *, ttl_seconds: int | None = None) -> int:
        """Atomic increment. Sets TTL on first increment if provided."""
        pipe = self.raw.pipeline()
        pipe.incr(key)
        if ttl_seconds is not None:
            pipe.expire(key, ttl_seconds, nx=True)
        value, *_ = pipe.execute()
        return int(value)

    def ping(self) -> bool:
        """True if Redis is reachable."""
        try:
            return bool(self.raw.ping())
        except redis.exceptions.RedisError:
            return False
