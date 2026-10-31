"""Tests for database initialization and migration behavior."""

from __future__ import annotations

from sqlalchemy import text

from app.db.database import create_engine_for_database, init_db


def test_init_db_adds_missing_ttl_columns(tmp_path) -> None:
    """Older SQLite schemas should be upgraded in place on startup."""

    database_path = tmp_path / "legacy.db"
    engine = create_engine_for_database(f"sqlite:///{database_path}")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_code VARCHAR(32) NOT NULL,
                    original_url TEXT NOT NULL,
                    clicks INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    last_accessed DATETIME
                )
                """
            )
        )

    init_db(engine)

    with engine.connect() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(urls)").fetchall()
        }

    assert "ttl_seconds" in columns
    assert "expires_at" in columns