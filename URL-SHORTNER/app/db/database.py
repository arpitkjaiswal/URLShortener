"""Database connections and additive migration from the original schema."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Url


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://") :]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def create_engine_for_database(database_url: str) -> Engine:
    database_url = normalize_database_url(database_url)
    url = make_url(database_url)
    options = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if url.database in {None, "", ":memory:"}:
            options["poolclass"] = StaticPool
    else:
        options.update(pool_size=5, max_overflow=5, pool_timeout=10, connect_args={"connect_timeout": 10})
    return create_engine(database_url, **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create fresh tables or preserve and upgrade an existing URLs table.

    A PostgreSQL transaction advisory lock serializes rolling-deploy startup.
    This migration only adds nullable columns and indexes; it never deletes data.
    """
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(73421918)"))
        if inspect(connection).has_table("urls"):
            columns = {column["name"] for column in inspect(connection).get_columns("urls")}
            timestamp = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
            additions = {"ttl_seconds": "INTEGER", "expires_at": timestamp, "owner_hash": "VARCHAR(64)"}
            for name, ddl_type in additions.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE urls ADD COLUMN {name} {ddl_type}"))
        Base.metadata.create_all(connection)
        for index in Url.__table__.indexes:
            index.create(connection, checkfirst=True)


def get_db(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session
