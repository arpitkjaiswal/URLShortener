import pytest
from app.core.config import Settings, get_settings
from app.db.database import normalize_database_url
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_render_configuration(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://shortener.onrender.com")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    assert get_settings().base_url == "https://shortener.onrender.com"
    monkeypatch.setenv("BASE_URL", "https://links.example.com")
    get_settings.cache_clear()
    assert get_settings().base_url == "https://links.example.com"


@pytest.mark.parametrize("url", ["", "sqlite:///./data.db"])
def test_render_rejects_ephemeral_database(monkeypatch, url):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    with pytest.raises(ValueError, match="PostgreSQL"):
        get_settings()


@pytest.mark.parametrize("prefix", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_postgres_driver_url(prefix):
    assert (
        normalize_database_url(prefix + "user:pass@host/db?sslmode=require")
        == "postgresql+psycopg://user:pass@host/db?sslmode=require"
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "javascript:bad",
        "https://user:pass@example.com",
        "https://example.com/path",
        "https://example.com?q=1",
    ],
)
def test_invalid_base_url(base_url):
    with pytest.raises(ValueError, match="BASE_URL"):
        Settings(database_url="sqlite://", base_url=base_url)


def test_https_cookie_and_short_url(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'secure.db'}", base_url="https://app.onrender.com"
    )
    with TestClient(create_app(settings), base_url=settings.base_url) as client:
        assert "Secure" in client.get("/api/v1/session").headers["set-cookie"]
        response = client.post("/api/v1/shorten", json={"url": "https://example.com"})
        assert response.json()["short_url"].startswith("https://app.onrender.com/")
