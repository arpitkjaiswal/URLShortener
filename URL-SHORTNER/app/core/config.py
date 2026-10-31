"""Environment configuration for local development and Render."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    base_url: str
    log_level: str = "INFO"
    create_limit_per_minute: int = 30

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("BASE_URL must be an http(s) origin without a path or credentials")
        if self.create_limit_per_minute < 1:
            raise ValueError("CREATE_LIMIT_PER_MINUTE must be positive")

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL") or "sqlite:///./url_shortener.db"
    if os.getenv("RENDER") == "true" and not database_url.startswith(
        ("postgres://", "postgresql://", "postgresql+psycopg://")
    ):
        raise ValueError(
            "Set DATABASE_URL to a PostgreSQL connection string on Render; SQLite storage is ephemeral"
        )
    return Settings(
        database_url=database_url,
        base_url=os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8000",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        create_limit_per_minute=int(os.getenv("CREATE_LIMIT_PER_MINUTE", "30")),
    )
