"""Application entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router, router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.database import create_engine_for_database, create_session_factory, init_db
from app.utils.cache import create_cache
from app.core.security import AccessControl, SecurityMiddleware



def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    active_settings = settings or get_settings()
    configure_logging(active_settings.log_level)

    engine = create_engine_for_database(active_settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    app = FastAPI(
        title="URL Shortener",
        docs_url=None, redoc_url=None, openapi_url=None,
        version="1.0.0",
        description="A clean-architecture URL shortening service.",
    )
    app.add_middleware(SecurityMiddleware)
    app.state.access = AccessControl()
    app.state.settings = active_settings
    app.state.session_factory = session_factory
    app.state.url_cache = create_cache(active_settings.redis_url, ttl_seconds=300)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(router)
    app.include_router(api_router)
    return app


app = create_app()
