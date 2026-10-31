"""Application factory with lifespan-managed database resources."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.routes import api_router, router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.security import CreationLimiter
from app.db.database import create_engine_for_database, create_session_factory, init_db


def create_app(settings: Settings | None = None) -> FastAPI:
    active = settings or get_settings()
    configure_logging(active.log_level)
    engine = create_engine_for_database(active.database_url)

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(init_db, engine)
        try:
            yield
        finally:
            await run_in_threadpool(engine.dispose)

    app = FastAPI(
        title="URL Shortener",
        version="2.0.0",
        description="Short links with browser-private management and click analytics.",
        lifespan=lifespan,
    )
    app.state.settings = active
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.creation_limiter = CreationLimiter(active.create_limit_per_minute)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {"POST", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin != active.normalized_base_url:
                return JSONResponse({"detail": "Cross-origin changes are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/") or request.url.path == "/health":
            response.headers["Cache-Control"] = "no-store"
        if request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        # Avoid logging query parameters, destination URLs, or connection secrets.
        logging.getLogger(__name__).error("Database operation failed (%s)", type(error).__name__)
        return JSONResponse({"detail": "Database unavailable. Please try again shortly."}, status_code=503)

    app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
    app.include_router(api_router)
    app.include_router(router)
    return app


app = create_app()
