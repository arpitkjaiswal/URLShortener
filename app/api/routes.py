"""HTTP routes for the URL shortener API."""

from __future__ import annotations

from pathlib import Path
from secrets import compare_digest
from io import BytesIO

import qrcode
import qrcode.image.svg
from sqlalchemy import text
from typing import Any, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import COOKIE_NAME, SESSION_TTL, check_origin, client_key
from app.schemas.url import BulkCreate, BulkResult, LibraryPage, LibraryQuery, LoginRequest, UrlUpdate
from app.services.library import analytics, library_page, list_item
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


def require_management(request: Request) -> None:
    """Fail closed without configuration; accept API keys or an expiring session."""
    expected = request.app.state.settings.admin_token
    if not expected:
        raise HTTPException(503, 'Management is locked. Configure ADMIN_TOKEN on the server.')
    access = request.app.state.access
    supplied = request.headers.get("X-Admin-Token", "")
    if supplied and compare_digest(supplied.encode(), expected.encode()):
        return
    token = request.cookies.get(COOKIE_NAME, '')
    if token and access.valid(token, expected):
        if request.method not in {'GET', 'HEAD'}:
            check_origin(request, required=True)
        return
    access.limit(('auth', client_key(request)), 10)
    raise HTTPException(401, 'Unlock your dashboard to continue.')


@api_router.post('/auth/login')
def login(payload: LoginRequest, request: Request, response: Response):
    check_origin(request)
    request.app.state.access.limit(('login', client_key(request)), 5)
    expected = request.app.state.settings.admin_token
    if not expected:
        raise HTTPException(503, 'Management is locked. Configure ADMIN_TOKEN on the server.')
    if not compare_digest(payload.key.encode(), expected.encode()):
        raise HTTPException(401, 'That access key is not correct. Please try again.')
    token = request.app.state.access.issue(expected)
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_TTL, httponly=True,
                        secure=request.app.state.settings.base_url.startswith('https://'),
                        samesite='strict', path='/api/v1')
    return {'status': 'unlocked', 'expires_in': SESSION_TTL}


@api_router.get('/auth/session', dependencies=[Depends(require_management)])
def session_status(request: Request):
    return {'expires_in': request.app.state.access.remaining(request.cookies.get(COOKIE_NAME, ''))}


@api_router.post('/auth/logout')
def logout(request: Request, response: Response):
    check_origin(request, required=True)
    request.app.state.access.revoke(request.cookies.get(COOKIE_NAME, ''))
    response.delete_cookie(COOKIE_NAME, path='/api/v1')
    return {'status': 'locked'}


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health_check(session: Session = Depends(get_db)) -> HealthResponse:
    """Return the service status."""

    session.execute(text("SELECT 1"))
    return HealthResponse(status="healthy")


@api_router.post(
    "/shorten",
    response_model=ShortenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Shorten a URL",
    responses={400: {"model": ErrorResponse}},
)
def shorten_url(payload: UrlCreate, request: Request, service: ShortenerService = Depends(get_shortener_service)) -> ShortenResponse:
    """Create a new shortened URL."""

    request.app.state.access.limit(('create', client_key(request)), 20)
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
    dependencies=[Depends(require_management)],
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


@api_router.get('/library', dependencies=[Depends(require_management)], response_model=LibraryPage)
def get_library(query: LibraryQuery = Depends(), service: ShortenerService = Depends(get_shortener_service)):
    return library_page(service, query)


@api_router.get('/analytics/{short_code}', dependencies=[Depends(require_management)])
def get_analytics(short_code: str, service: ShortenerService = Depends(get_shortener_service)):
    result = analytics(service, short_code)
    if result is None:
        raise HTTPException(404, 'Short URL not found')
    return result


@api_router.post('/bulk', dependencies=[Depends(require_management)], response_model=list[BulkResult])
def bulk_shorten(payload: BulkCreate, request: Request, service: ShortenerService = Depends(get_shortener_service)):
    results = []
    for index, destination in enumerate(payload.urls):
        try:
            request.app.state.access.limit(('create', client_key(request)), 20)
            url = service.shorten_url(UrlCreate(url=destination))
            results.append(BulkResult(index=index, url=destination, short_url=service.build_short_url(url.short_code)))
        except (ValueError, HTTPException) as error:
            results.append(BulkResult(index=index, url=destination,
                                      error=error.detail if isinstance(error, HTTPException) else str(error)))
    return results


# New endpoint: list recent URLs (default limit 20)
@api_router.get(
    "/urls",
    dependencies=[Depends(require_management)],
    response_model=List[UrlListItem],
    summary="List recent shortened URLs",
    description="Returns the most recent URLs ordered by creation time, limited to 20 by default.",
)
def list_urls(
    limit: int = Query(20, ge=1, le=50),
    service: ShortenerService = Depends(get_shortener_service),
) -> List[UrlListItem]:
    recent = service.repository.list_recent(limit)
    return [list_item(url, service) for url in recent]


@api_router.patch('/urls/{short_code}', dependencies=[Depends(require_management)], response_model=UrlListItem)
def update_url(short_code: str, payload: UrlUpdate, service: ShortenerService = Depends(get_shortener_service)):
    try:
        url = service.update_url(short_code, payload)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if url is None:
        raise HTTPException(404, 'Short URL not found')
    return list_item(url, service)


@api_router.get("/qr/{short_code}", summary="Download a QR code")
def qr_code(short_code: str, request: Request, service: ShortenerService = Depends(get_shortener_service)) -> Response:
    request.app.state.access.limit(('qr', client_key(request)), 60)
    if service.resolve_url(short_code) is None:
        raise HTTPException(status_code=404, detail="Short URL not found")
    image = qrcode.make(service.build_short_url(short_code), image_factory=qrcode.image.svg.SvgPathImage)
    output = BytesIO()
    image.save(output)
    return Response(output.getvalue(), media_type="image/svg+xml", headers={
        "Content-Disposition": f'attachment; filename="link-qr.svg"',
        "X-Content-Type-Options": "nosniff",
    })


# DELETE endpoint to remove a short URL
@api_router.delete(
    "/urls/{short_code}",
    dependencies=[Depends(require_management)],
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
    request: Request,
    background_tasks: BackgroundTasks,
    service: ShortenerService = Depends(get_shortener_service),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> Response:
    """Redirect a short code to its original destination."""

    url = service.resolve_url(short_code)
    if url is None:
        if "text/html" in request.headers.get("accept", ""):
            return FileResponse(STATIC_DIR / "not-found.html", status_code=404)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")

    background_tasks.add_task(record_click_task, session_factory, short_code)
    return RedirectResponse(url=url.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)