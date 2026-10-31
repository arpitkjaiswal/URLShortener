"""Run the same API tests against isolated SQLite or PostgreSQL databases."""

import os
import uuid

import pytest
from app.core.config import Settings
from app.db.database import normalize_database_url
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


@pytest.fixture()
def settings(tmp_path):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        yield Settings(
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            base_url="http://testserver",
            log_level="WARNING",
        )
        return
    # Each test gets a dedicated schema; never drop a user's public schema.
    from sqlalchemy.engine import make_url

    schema = "test_" + uuid.uuid4().hex
    engine = create_engine(normalize_database_url(database_url))
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(normalize_database_url(database_url)).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    try:
        yield Settings(
            database_url=url.render_as_string(hide_password=False),
            base_url="http://testserver",
            log_level="WARNING",
        )
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    with TestClient(app) as client:
        assert client.get("/api/v1/session").status_code == 200
        yield client


@pytest.fixture()
def db_session(client, app):
    with app.state.session_factory() as session:
        yield session
