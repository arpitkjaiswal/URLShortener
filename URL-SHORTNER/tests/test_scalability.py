"""Real uniqueness collisions and database failure handling."""

from itertools import chain, repeat

from app.repositories.url_repository import UrlRepository
from app.services import shortener
from sqlalchemy.exc import OperationalError


def test_short_code_collision_retries(client, monkeypatch):
    choices = iter(chain(repeat("a", 14), repeat("b", 7)))
    monkeypatch.setattr(shortener.secrets, "choice", lambda _: next(choices))
    first = client.post("/api/v1/shorten", json={"url": "https://example.com/first"})
    second = client.post("/api/v1/shorten", json={"url": "https://example.com/second"})
    assert first.json()["short_code"] == "aaaaaaa"
    assert second.status_code == 201
    assert second.json()["short_code"] == "bbbbbbb"
    assert client.get("/api/v1/urls").json()["total"] == 2


def test_exhausted_collisions_leave_session_usable(client, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(shortener.secrets, "choice", lambda _: "a")
        assert client.post("/api/v1/shorten", json={"url": "https://example.com"}).status_code == 201
        assert client.post("/api/v1/shorten", json={"url": "https://example.com"}).status_code == 503
    assert client.post("/api/v1/shorten", json={"url": "https://example.com/next"}).status_code == 201
    assert client.get("/api/v1/urls").json()["total"] == 2


def test_database_failure_is_not_retried_as_a_collision(client, monkeypatch):
    calls = []

    def broken(*args, **kwargs):
        calls.append(True)
        raise OperationalError("insert", {}, Exception("unavailable"))

    monkeypatch.setattr(UrlRepository, "create", broken)
    assert client.post("/api/v1/shorten", json={"url": "https://example.com"}).status_code == 503
    assert len(calls) == 1
