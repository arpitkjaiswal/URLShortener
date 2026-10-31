"""URL persistence, with consistent UTC timestamps on both database engines."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Url(Base):
    __tablename__ = "urls"
    __table_args__ = (Index("ix_urls_owner_created", "owner_hash", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    original_url: Mapped[str] = mapped_column(Text)
    # Nullable only for legacy records, which remain redirectable but unclaimed.
    owner_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_accessed: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
