"""SQLAlchemy models."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all database models."""


class Url(Base):
    """Persisted URL mapping."""

    __tablename__ = "urls"
    __table_args__ = (
        Index("ix_urls_created_at", "created_at"),
        Index("ix_urls_last_accessed", "last_accessed"),
        Index("ix_urls_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    details: Mapped["LinkDetails | None"] = relationship(
        back_populates="url", cascade="all, delete-orphan", uselist=False, lazy="joined"
    )
    daily_clicks: Mapped[list["DailyClick"]] = relationship(cascade="all, delete-orphan")

    @property
    def title(self) -> str:
        return self.details.title if self.details else ""

    @property
    def tag(self) -> str:
        return self.details.tag if self.details else ""

    @property
    def is_paused(self) -> bool:
        return self.details.is_paused if self.details else False


class LinkDetails(Base):
    """Optional metadata in a separate table: existing links need no migration."""
    __tablename__ = "link_details"

    url_id: Mapped[int] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    tag: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    url: Mapped["Url"] = relationship(back_populates="details")


class DailyClick(Base):
    """UTC daily aggregates; no visitor identifiers, IPs, or raw referrers."""
    __tablename__ = "daily_clicks"

    url_id: Mapped[int] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
