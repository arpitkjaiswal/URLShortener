"""Request and response schemas for URLs."""

from __future__ import annotations

from datetime import datetime

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