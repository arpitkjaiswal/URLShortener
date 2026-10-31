"""Persistence operations for URL mappings."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select, update, delete
from sqlalchemy.orm import Session

from app.db.models import Url, LinkDetails, DailyClick


class UrlRepository:
    """Encapsulate URL persistence concerns."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        original_url: str,
        short_code: str = "",
        ttl_seconds: int | None = None,
        expires_at: datetime | None = None,
    ) -> Url:
        """Insert a URL record and flush to obtain its numeric ID."""

        url = Url(
            original_url=original_url,
            short_code=short_code,
            clicks=0,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
        )
        self.session.add(url)
        self.session.flush()
        return url

    def set_short_code(self, url: Url, short_code: str) -> Url:
        """Persist the generated short code for an existing record."""

        url.short_code = short_code
        self.session.flush()
        return url

    def get_by_short_code(self, short_code: str) -> Url | None:
        """Return the URL record that matches the provided code."""

        statement = select(Url).where(Url.short_code == short_code)
        return self.session.execute(statement).scalar_one_or_none()

    def get_active_by_short_code(self, short_code: str, now: datetime | None = None) -> Url | None:
        """Return a short code only if it has not expired."""

        current_time = now or datetime.now(timezone.utc)
        statement = select(Url).where(
            Url.short_code == short_code,
            ~Url.details.has(LinkDetails.is_paused.is_(True)),
            or_(Url.expires_at.is_(None), Url.expires_at > current_time),
        )
        return self.session.execute(statement).scalar_one_or_none()

    def record_access(self, url: Url, accessed_at: datetime | None = None) -> Url:
        """Update click analytics after a redirect."""

        url.clicks += 1
        url.last_accessed = accessed_at or datetime.now(timezone.utc)
        self.session.flush()
        return url

    def list_recent(self, limit: int = 20) -> list[Url]:
        """Return the most recent URLs ordered by creation time, limited by `limit`."""
        stmt = select(Url).order_by(Url.created_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def delete_by_short_code(self, short_code: str) -> bool:
        """Delete a URL record by its short_code. Returns True if a row was deleted."""
        stmt = (delete(Url).where(Url.short_code == short_code))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount > 0

    def record_access_by_short_code(self, short_code: str, accessed_at: datetime | None = None) -> bool:
        """Update analytics for a short code without fetching the full row first."""

        updated_at = accessed_at or datetime.now(timezone.utc)
        statement = (
            update(Url)
            .where(
                Url.short_code == short_code,
                ~Url.details.has(LinkDetails.is_paused.is_(True)),
                or_(Url.expires_at.is_(None), Url.expires_at > updated_at),
            )
            .values(clicks=Url.clicks + 1, last_accessed=updated_at)
            .returning(Url.id)
        )
        url_id = self.session.execute(statement).scalar_one_or_none()
        if url_id is None:
            return False
        # Both supported databases provide atomic UPSERT: concurrent clicks cannot lose daily increments.
        if self.session.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        stmt = insert(DailyClick).values(url_id=url_id, day=updated_at.date(), clicks=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=[DailyClick.url_id, DailyClick.day],
            set_={"clicks": DailyClick.clicks + 1},
        )
        self.session.execute(stmt)
        self.session.flush()
        return True

    def commit(self) -> None:
        """Commit the current transaction."""

        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""

        self.session.rollback()