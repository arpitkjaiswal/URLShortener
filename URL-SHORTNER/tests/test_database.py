"""Tests for database initialization and migration behavior."""

from __future__ import annotations

from app.db.database import create_engine_for_database, init_db
from sqlalchemy import text


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
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(urls)").fetchall()}

    assert "ttl_seconds" in columns
    assert "expires_at" in columns


def test_legacy_migration_preserves_links_and_is_repeatable(settings):
    """Exercise additive migration on whichever database the suite is using."""
    from sqlalchemy import inspect

    engine = create_engine_for_database(settings.database_url)
    identifier = (
        "SERIAL PRIMARY KEY" if engine.dialect.name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    )
    timestamp = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE TABLE urls (id {identifier}, short_code VARCHAR(32) NOT NULL, original_url TEXT NOT NULL, clicks INTEGER NOT NULL DEFAULT 0, created_at {timestamp} NOT NULL, last_accessed {timestamp})"
            )
        )
        connection.execute(
            text(
                "INSERT INTO urls (short_code, original_url, clicks, created_at) VALUES ('legacy1', 'https://example.com', 4, CURRENT_TIMESTAMP)"
            )
        )
    init_db(engine)
    init_db(engine)
    with engine.connect() as connection:
        record = connection.execute(text("SELECT short_code, clicks, owner_hash FROM urls")).one()
        assert tuple(record) == ("legacy1", 4, None)
        assert {i["name"] for i in inspect(connection).get_indexes("urls")} >= {
            "ix_urls_short_code",
            "ix_urls_owner_created",
        }
    engine.dispose()
