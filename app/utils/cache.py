"""Cache implementations including InMemory and Redis options."""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class CacheEntry(Generic[T]):
    """Store a cached value and its expiry timestamp."""

    value: T
    expires_at: datetime


class InMemoryCache(Generic[T]):
    """Thread-safe in-memory cache with a fixed TTL per entry."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, CacheEntry[T]] = {}
        self._lock = RLock()

    def get(self, key: str) -> T | None:
        """Return a cached value if it exists and has not expired."""

        now = datetime.now(timezone.utc)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store a value in the cache."""

        entry_ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=entry_ttl)
        with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        """Remove a cached value if it exists."""

        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        """Remove all cached values."""

        with self._lock:
            self._entries.clear()


class RedisCache:
    """Redis-backed distributed cache with automatic fallback to InMemoryCache."""

    def __init__(self, redis_url: str, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self.redis_url = redis_url
        import redis

        self._client = redis.Redis.from_url(redis_url)
        self._fallback_cache = InMemoryCache[Any](ttl_seconds=ttl_seconds)
        self._use_fallback = False

    def get(self, key: str) -> Any | None:
        """Get a value from Redis, falling back to InMemoryCache on failure."""

        if self._use_fallback:
            return self._fallback_cache.get(key)
        try:
            data = self._client.get(key)
            if data is None:
                return None
            return pickle.loads(data)
        except Exception as e:
            logger.warning("Redis GET failed, falling back to in-memory: %s", e)
            self._use_fallback = True
            return self._fallback_cache.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a value in Redis, falling back to InMemoryCache on failure."""

        entry_ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        if self._use_fallback:
            self._fallback_cache.set(key, value, entry_ttl)
            return
        try:
            data = pickle.dumps(value)
            self._client.set(key, data, ex=entry_ttl)
        except Exception as e:
            logger.warning("Redis SET failed, falling back to in-memory: %s", e)
            self._use_fallback = True
            self._fallback_cache.set(key, value, entry_ttl)

    def delete(self, key: str) -> None:
        """Delete a value from Redis, falling back to InMemoryCache on failure."""

        if self._use_fallback:
            self._fallback_cache.delete(key)
            return
        try:
            self._client.delete(key)
        except Exception as e:
            logger.warning("Redis DELETE failed, falling back to in-memory: %s", e)
            self._use_fallback = True
            self._fallback_cache.delete(key)

    def clear(self) -> None:
        """Clear all values from Redis, falling back to InMemoryCache on failure."""

        if self._use_fallback:
            self._fallback_cache.clear()
            return
        try:
            self._client.flushdb()
        except Exception as e:
            logger.warning("Redis CLEAR failed, falling back to in-memory: %s", e)
            self._use_fallback = True
            self._fallback_cache.clear()


def create_cache(redis_url: str | None, ttl_seconds: int = 300) -> InMemoryCache[Any] | RedisCache:
    """Build the cache instance based on the settings."""

    if redis_url:
        try:
            return RedisCache(redis_url, ttl_seconds=ttl_seconds)
        except Exception as e:
            logger.warning("Failed to initialize RedisCache: %s. Using InMemoryCache.", e)
    return InMemoryCache[Any](ttl_seconds=ttl_seconds)