"""HTTP interface for the dashboard and public redirects."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import get_owner, initialize_workspace, limit_creation
from app.db.database import get_db
from app.schemas.url import (
    HealthResponse,
    ShortenResponse,
    SummaryResponse,
    UrlCreate,
    UrlListItem,
    UrlPage,
    UrlStatsResponse,
)
from app.services.shortener import CodeGenerationError, ShortenerService

router = APIRouter()
api_router = APIRouter(prefix="/api/v1")
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def get_service(request: Request, session: Session = Depends(get_db)) -> ShortenerService:
    return ShortenerService(session, request.app.state.settings)


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/health", response_model=HealthResponse)
def health_check(session: Session = Depends(get_db)) -> HealthResponse:
    session.execute(text("SELECT 1"))
    return HealthResponse(status="healthy")


@api_router.get("/session")
def session(request: Request, response: Response) -> dict[str, str]:
    """Initialize/renew an anonymous workspace. Keep the returned HTTP-only cookie."""
    initialize_workspace(request, response)
    return {"status": "ready"}


@api_router.post(
    "/shorten", response_model=ShortenResponse, status_code=201, dependencies=[Depends(limit_creation)]
)
def shorten_url(
    payload: UrlCreate, owner: str = Depends(get_owner), service: ShortenerService = Depends(get_service)
) -> ShortenResponse:
    try:
        url = service.shorten_url(payload, owner)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except CodeGenerationError as error:
        raise HTTPException(503, str(error)) from error
    return ShortenResponse(
        short_code=url.short_code,
        short_url=service.build_short_url(url.short_code),
        expires_at=url.expires_at,
    )


@api_router.get("/stats/{short_code}", response_model=UrlStatsResponse)
def get_stats(
    short_code: str, owner: str = Depends(get_owner), service: ShortenerService = Depends(get_service)
):
    url = service.repository.get_owned(short_code, owner)
    if url is None:
        raise HTTPException(404, "Short URL not found")
    return url


@api_router.get("/summary", response_model=SummaryResponse)
def summary(owner: str = Depends(get_owner), service: ShortenerService = Depends(get_service)):
    return service.repository.summary(owner)


@api_router.get("/urls", response_model=UrlPage)
def list_urls(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=200),
    owner: str = Depends(get_owner),
    service: ShortenerService = Depends(get_service),
) -> UrlPage:
    items, total = service.repository.list_recent(owner, limit, offset, q.strip())
    return UrlPage(
        items=[
            UrlListItem(
                **UrlStatsResponse.model_validate(item).model_dump(),
                short_url=service.build_short_url(item.short_code),
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@api_router.delete("/urls/{short_code}", status_code=204)
def delete_url(
    short_code: str, owner: str = Depends(get_owner), service: ShortenerService = Depends(get_service)
) -> Response:
    if not service.repository.delete_owned(short_code, owner):
        raise HTTPException(404, "Short URL not found")
    return Response(status_code=204)


@router.api_route("/{short_code}", methods=["GET", "HEAD"], include_in_schema=False)
def redirect_short_code(
    short_code: str, request: Request, service: ShortenerService = Depends(get_service)
) -> Response:
    destination = service.repository.resolve(short_code, count_click=request.method == "GET")
    if destination is None:
        if "text/html" in request.headers.get("accept", ""):
            return FileResponse(STATIC_DIR / "not-found.html", status_code=404)
        raise HTTPException(404, "Short URL not found")
    return RedirectResponse(destination, status_code=307, headers={"Cache-Control": "no-store"})
