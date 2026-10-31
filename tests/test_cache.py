"""Tests for the in-memory cache helper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.utils.cache import CacheEntry, InMemoryCache


def test_cache_set_and_get() -> None:
    """Stored values should be returned before they expire."""

    cache = InMemoryCache(ttl_seconds=60)
    cache.set("abc", {"value": 1})

    assert cache.get("abc") == {"value": 1}


def test_cache_expiration() -> None:
    """Expired values should be evicted on read."""

    cache = InMemoryCache(ttl_seconds=60)
    cache._entries["abc"] = CacheEntry(  # type: ignore[attr-defined]
        value={"value": 1},
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert cache.get("abc") is None


def test_cache_delete() -> None:
    """Deleting a key should remove it from the cache."""

    cache = InMemoryCache(ttl_seconds=60)
    cache.set("abc", {"value": 1})
    cache.delete("abc")

    assert cache.get("abc") is None