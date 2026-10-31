"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str
    base_url: str
    log_level: str
    redis_url: str | None = None
    admin_token: str | None = None

    @property
    def normalized_base_url(self) -> str:
        """Return the public base URL without a trailing slash."""

        return self.base_url.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load application settings from the environment."""

    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "sqlite:///./url_shortener.db")
    if os.getenv("RENDER") == "true":
        if not database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            raise ValueError("Set DATABASE_URL in Render to your external PostgreSQL connection string (for example, Neon Free). Local SQLite files are not persistent on Render Free.")
        if not os.getenv("ADMIN_TOKEN"):
            raise ValueError("Set a private ADMIN_TOKEN in Render to protect link management.")
    return Settings(
        database_url=database_url,
        base_url=os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        redis_url=os.getenv("REDIS_URL"),
        admin_token=os.getenv("ADMIN_TOKEN"),
    )
