"""Public request and response contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UrlCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    ttl_seconds: int | None = Field(default=None, ge=1, le=31_536_000, strict=True)


class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    expires_at: datetime | None


class UrlStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    original_url: str
    short_code: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None
    last_accessed: datetime | None


class UrlListItem(UrlStatsResponse):
    short_url: str


class UrlPage(BaseModel):
    items: list[UrlListItem]
    total: int
    limit: int
    offset: int


class SummaryResponse(BaseModel):
    total_links: int
    total_clicks: int
    active_links: int
    expired_links: int


class HealthResponse(BaseModel):
    status: str
