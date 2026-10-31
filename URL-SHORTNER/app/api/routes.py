"""HTTP routes for the URL shortener API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.database import get_db
from app.schemas.url import ErrorResponse, HealthResponse, ShortenResponse, UrlCreate, UrlStatsResponse, UrlListItem
from app.services.shortener import ShortenerService, record_click_task
from app.utils.cache import InMemoryCache

router = APIRouter()
api_router = APIRouter(prefix="/api/v1")
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the tiny browser frontend."""

    return FileResponse(STATIC_DIR / "index.html")


def get_settings_dependency(request: Request) -> Settings:
    """Resolve the application settings from the current request."""

    return request.app.state.settings


def get_cache_dependency(request: Request) -> InMemoryCache:
    """Resolve the shared cache from the current request."""

    return request.app.state.url_cache


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Resolve the session factory from the current request."""

    return request.app.state.session_factory


def get_shortener_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dependency),
    cache: InMemoryCache = Depends(get_cache_dependency),
) -> ShortenerService:
    """Build a request-scoped service instance."""

    return ShortenerService(session=session, settings=settings, cache=cache)


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health_check() -> HealthResponse:
    """Return the service status."""

    return HealthResponse(status="healthy")


@api_router.post(
    "/shorten",
    response_model=ShortenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Shorten a URL",
    responses={400: {"model": ErrorResponse}},
)
def shorten_url(payload: UrlCreate, service: ShortenerService = Depends(get_shortener_service)) -> ShortenResponse:
    """Create a new shortened URL."""

    try:
        url = service.shorten_url(payload)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return ShortenResponse(
        short_code=url.short_code,
        short_url=service.build_short_url(url.short_code),
        expires_at=url.expires_at,
    )


@api_router.get(
    "/stats/{short_code}",
    response_model=UrlStatsResponse,
    summary="Get URL analytics",
    responses={404: {"model": ErrorResponse}},
)
def get_stats(short_code: str, service: ShortenerService = Depends(get_shortener_service)) -> UrlStatsResponse:
    """Return analytics for a given short code."""

    url = service.get_stats(short_code)
    if url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")

    return UrlStatsResponse(
        original_url=url.original_url,
        short_code=url.short_code,
        clicks=url.clicks,
        created_at=url.created_at,
        expires_at=url.expires_at,
        last_accessed=url.last_accessed,
    )


# New endpoint: list recent URLs (default limit 20)
@api_router.get(
    "/urls",
    response_model=List[UrlListItem],
    summary="List recent shortened URLs",
    description="Returns the most recent URLs ordered by creation time, limited to 20 by default.",
)
def list_urls(
    limit: int = Query(20, ge=1, le=50),
    service: ShortenerService = Depends(get_shortener_service),
) -> List[UrlListItem]:
    recent = service.repository.list_recent(limit)
    return [
        UrlListItem(
            short_code=u.short_code,
            original_url=u.original_url,
            short_url=service.build_short_url(u.short_code),
            created_at=u.created_at,
            expires_at=u.expires_at,
            clicks=u.clicks,
        )
        for u in recent
    ]

# DELETE endpoint to remove a short URL
@api_router.delete(
    "/urls/{short_code}",
    summary="Delete a shortened URL",
    response_model=None,
    responses={404: {"model": ErrorResponse}},
)
def delete_url_endpoint(
    short_code: str,
    service: ShortenerService = Depends(get_shortener_service),
) -> None:
    """Delete a URL by its short code. Returns 404 if not found."""
    success = service.delete_url(short_code)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")
    return None


@router.get(
    "/{short_code}",
    include_in_schema=False,
)
def redirect_short_code(
    short_code: str,
    background_tasks: BackgroundTasks,
    service: ShortenerService = Depends(get_shortener_service),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> Response:
    """Redirect a short code to its original destination."""

    url = service.resolve_url(short_code)
    if url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")

    background_tasks.add_task(record_click_task, session_factory, short_code)
    return RedirectResponse(url=url.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)