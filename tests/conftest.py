"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.database import create_engine_for_database, create_session_factory, init_db
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Provide isolated application settings for tests."""

    database_path = tmp_path / "test.db"
    return Settings(
        database_url=f"sqlite:///{database_path}",
        base_url="http://testserver",
        log_level="WARNING",
    )


@pytest.fixture()
def app(settings: Settings):
    """Create a FastAPI app backed by a temporary SQLite database."""

    return create_app(settings)


@pytest.fixture()
def client(app):
    """Create a test client for API calls."""

    return TestClient(app)


@pytest.fixture()
def session_factory(settings: Settings):
    """Create a session factory for direct database access in tests."""

    engine = create_engine_for_database(settings.database_url)
    init_db(engine)
    return create_session_factory(engine)


@pytest.fixture()
def db_session(session_factory) -> Session:
    """Provide a database session for assertions."""

    session = session_factory()
    try:
        yield session
    finally:
        session.close()