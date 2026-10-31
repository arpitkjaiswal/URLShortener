"""Request and response schemas for URLs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class UrlCreate(BaseModel):
    """Incoming payload for URL shortening."""

    url: str = Field(..., max_length=8192, description="Original URL to shorten")
    custom_alias: str | None = Field(default=None, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    ttl_seconds: int | None = Field(
        default=None,
        ge=1,
        le=315360000,
        description="Optional time to live in seconds; omit for no expiry",
    )


class ShortenResponse(BaseModel):
    """Response payload for URL creation."""

    short_code: str
    short_url: str
    expires_at: datetime | None = None


class UrlStatsResponse(BaseModel):
    """Analytics payload for a shortened URL."""

    original_url: str
    short_code: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None
    last_accessed: datetime | None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str

class UrlListItem(BaseModel):
    """Item representing a shortened URL in the recent URLs list."""

    short_code: str
    original_url: str
    short_url: str
    created_at: datetime
    expires_at: datetime | None = None
    clicks: int
    title: str = ""
    tag: str = ""
    is_paused: bool = False

class LoginRequest(BaseModel):
    key: str = Field(min_length=1, max_length=512)


class UrlUpdate(BaseModel):
    url: str | None = Field(default=None, min_length=1, max_length=8192)
    title: str | None = Field(default=None, max_length=120)
    tag: str | None = Field(default=None, max_length=40)
    is_paused: bool | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=315360000)


class BulkCreate(BaseModel):
    urls: list[Annotated[str, Field(min_length=1, max_length=8192)]] = Field(min_length=1, max_length=20)


class BulkResult(BaseModel):
    index: int
    url: str
    short_url: str | None = None
    error: str | None = None


class LibrarySummary(BaseModel):
    links: int
    clicks: int
    active: int
    paused: int
    expired: int


class LibraryPage(BaseModel):
    items: list[UrlListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    summary: LibrarySummary
    tags: list[str]


class LibraryQuery(BaseModel):
    q: str = Field(default="", max_length=200)
    state: Literal["all", "active", "paused", "expired"] = "all"
    sort: Literal["newest", "oldest", "clicks"] = "newest"
    tag: str = Field(default="", max_length=40)
    page: int = Field(default=1, ge=1, le=50000)
    page_size: int = Field(default=20, ge=1, le=50)
