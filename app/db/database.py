"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base


def _sqlite_connect_args(database_url: str) -> dict[str, bool]:
    """Return SQLite-specific engine arguments when needed."""

    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def create_engine_for_database(database_url: str) -> Engine:
    """Create a SQLAlchemy engine from a database URL."""

    if database_url.startswith(("postgres://", "postgresql://")):
        database_url = "postgresql+psycopg://" + database_url.split("://", 1)[1]
    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=_sqlite_connect_args(database_url),
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine."""

    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all tables for the configured engine."""

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _migrate_sqlite_urls_table(engine)


@dataclass(frozen=True, slots=True)
class _ColumnMigration:
    name: str
    ddl: str


def _migrate_sqlite_urls_table(engine: Engine) -> None:
    """Backfill missing columns for older SQLite databases.

    SQLite does not support the kind of online schema migrations used by a
    dedicated migration tool. For local development, we keep startup resilient
    by adding nullable columns when they are absent.
    """

    required_columns = {
        "ttl_seconds": _ColumnMigration("ttl_seconds", "ALTER TABLE urls ADD COLUMN ttl_seconds INTEGER"),
        "expires_at": _ColumnMigration("expires_at", "ALTER TABLE urls ADD COLUMN expires_at DATETIME"),
    }

    with engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(urls)").fetchall()
        }

        for column_name, migration in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(migration.ddl))


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield a database session from the application state."""

    session_factory = request.app.state.session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()