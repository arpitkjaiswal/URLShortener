"""Tests for scalable features."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.utils.cache import create_cache, RedisCache, InMemoryCache
from app.services.shortener import ShortenerService
from app.schemas.url import UrlCreate


def test_redis_cache_fallback() -> None:
    """RedisCache should fallback to InMemoryCache on connection failures."""

    # Set up cache with a invalid redis url
    cache = create_cache("redis://localhost:9999/0")
    assert isinstance(cache, RedisCache)

    # Set and get should fall back to InMemoryCache and work successfully
    cache.set("key1", "val1")
    assert cache.get("key1") == "val1"
    assert cache._use_fallback is True

    # Delete and clear should also work
    cache.delete("key1")
    assert cache.get("key1") is None
    cache.clear()


def test_random_short_code_generation(db_session, settings) -> None:
    """Shortening a URL should generate a random 7-character base62 code."""

    cache = InMemoryCache(ttl_seconds=60)
    service = ShortenerService(session=db_session, settings=settings, cache=cache)

    payload = UrlCreate(url="https://scalability-test.com")
    url1 = service.shorten_url(payload)
    url2 = service.shorten_url(payload)

    assert len(url1.short_code) == 7
    assert len(url2.short_code) == 7
    assert url1.short_code != url2.short_code
