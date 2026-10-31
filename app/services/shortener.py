"""Business logic for shortening and resolving URLs."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from math import ceil
from typing import Any
from urllib.parse import urljoin

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.repositories.url_repository import UrlRepository
from app.schemas.url import UrlCreate
from app.utils.base62 import ALPHABET
from app.utils.cache import InMemoryCache
from app.utils.validators import is_valid_url


@dataclass(frozen=True, slots=True)
class RedirectTarget:
    """Cache only redirect fields, never a detached ORM graph."""
    original_url: str
    expires_at: datetime | None
    is_paused: bool


def record_click_task(session_factory: Any, short_code: str) -> None:
    """Background task to record clicks using a dedicated session."""
    with session_factory() as session:
        repository = UrlRepository(session)
        now = datetime.now(timezone.utc)
        repository.record_access_by_short_code(short_code, accessed_at=now)
        repository.commit()


class ShortenerService:
    """Coordinate URL validation, persistence, and code generation."""

    def __init__(self, session: Session, settings: Settings, cache: InMemoryCache) -> None:
        self.repository = UrlRepository(session)
        self.settings = settings
        self.cache = cache
        self.logger = logging.getLogger(self.__class__.__name__)

    def shorten_url(self, payload: UrlCreate) -> Any:
        """Validate and store a new shortened URL."""

        if not is_valid_url(payload.url):
            self.logger.warning("Invalid URL request")
            raise ValueError("Invalid URL")

        now = datetime.now(timezone.utc)
        expires_at = None
        if payload.ttl_seconds is not None:
            expires_at = now + self._ttl_to_delta(payload.ttl_seconds)

        if payload.custom_alias and payload.custom_alias.lower() in {"health", "docs", "redoc", "static", "api", "openapi.json"}:
            raise ValueError("This alias is reserved. Please choose another.")

        # Retry only unique-code collisions; infrastructure errors must propagate.
        max_retries = 3
        url = None
        for attempt in range(max_retries):
            short_code = payload.custom_alias or "".join(secrets.choice(ALPHABET) for _ in range(7))
            try:
                self.repository.session.begin_nested()
                url = self.repository.create(
                    payload.url.strip(),
                    short_code=short_code,
                    ttl_seconds=payload.ttl_seconds,
                    expires_at=expires_at,
                )
                self.repository.session.commit()
                break
            except IntegrityError as e:
                self.repository.session.rollback()
                if payload.custom_alias:
                    raise ValueError("This alias is already taken. Please choose another.") from e
                if attempt == max_retries - 1:
                    self.logger.error("Failed to generate a unique short code after %s attempts", max_retries)
                    raise RuntimeError("Failed to generate short code") from e
                self.logger.warning("Collision detected for short code %s, retrying...", short_code)

        self.repository.commit()
        self.cache.set(short_code, RedirectTarget(url.original_url, url.expires_at, url.is_paused), ttl_seconds=self._cache_ttl_seconds(url, now))
        self.logger.info("Shortened URL id=%s", url.id)
        return url

    def resolve_url(self, short_code: str) -> Any:
        """Look up a short code."""

        now = datetime.now(timezone.utc)

        cached_url = self.cache.get(short_code)
        if cached_url is not None:
            if cached_url.is_paused or self._is_expired(cached_url, now):
                self.cache.delete(short_code)
                self.logger.warning("Short URL expired: %s", short_code)
                return None
            return cached_url

        url = self.repository.get_active_by_short_code(short_code, now=now)
        if url is None:
            self.logger.warning("Short URL not found or expired: %s", short_code)
            return None

        self.cache.set(short_code, RedirectTarget(url.original_url, url.expires_at, url.is_paused), ttl_seconds=self._cache_ttl_seconds(url, now))
        self.logger.debug("Resolved short link")
        return url

    def get_stats(self, short_code: str) -> Any:
        """Return analytics data for a short code without mutating it."""

        url = self.repository.get_active_by_short_code(short_code)
        if url is None:
            self.logger.warning("Stats requested for unknown or expired short code: %s", short_code)
            return None

        return url

    def update_url(self, short_code, payload):
        url = self.repository.get_by_short_code(short_code)
        if url is None:
            return None
        if payload.url is not None:
            if not is_valid_url(payload.url):
                raise ValueError('Please enter a valid HTTP or HTTPS destination without embedded credentials.')
            url.original_url = payload.url.strip()
        if any(getattr(payload, name) is not None for name in ('title', 'tag', 'is_paused')):
            from app.db.models import LinkDetails
            if url.details is None:
                url.details = LinkDetails(title='', tag='', is_paused=False)
            for name in ('title', 'tag', 'is_paused'):
                value = getattr(payload, name)
                if value is not None:
                    setattr(url.details, name, value.strip() if isinstance(value, str) else value)
        if 'ttl_seconds' in payload.model_fields_set:
            url.ttl_seconds = payload.ttl_seconds
            url.expires_at = (datetime.now(timezone.utc) + timedelta(seconds=payload.ttl_seconds)
                              if payload.ttl_seconds is not None else None)
        self.repository.commit()
        self.cache.delete(short_code)
        return url

    def delete_url(self, short_code: str) -> bool:
        """Delete a URL record by its short_code.
        Returns True if a row was deleted, False otherwise.
        """
        # Import Url locally to avoid circular imports
        from app.db.models import Url

        # Find the record
        url_obj = self.repository.session.query(Url).filter(Url.short_code == short_code).first()
        if not url_obj:
            return False
        self.repository.session.delete(url_obj)
        self.repository.session.commit()
        # Invalidate cache entry
        self.cache.delete(short_code)
        return True

    def build_short_url(self, short_code: str) -> str:
        """Construct a public short URL from the configured base URL."""

        base_url = self.settings.normalized_base_url + "/"
        return urljoin(base_url, short_code)

    def _is_expired(self, url: Any, now: datetime | None = None) -> bool:
        """Return True when a URL has an expiry timestamp in the past."""

        if url.expires_at is None:
            return False
        current_time = now or datetime.now(timezone.utc)
        expiry = url.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry <= current_time

    def _cache_ttl_seconds(self, url: Any, now: datetime | None = None) -> int | None:
        """Return a cache TTL that never exceeds the record's lifetime."""

        if url.expires_at is None:
            return None

        current_time = now or datetime.now(timezone.utc)
        expiry = url.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        remaining_seconds = (expiry - current_time).total_seconds()
        if remaining_seconds <= 0:
            return 1
        return max(1, ceil(remaining_seconds))

    def _ttl_to_delta(self, ttl_seconds: int) -> timedelta:
        """Convert a requested TTL to a timedelta."""

        return timedelta(seconds=ttl_seconds)