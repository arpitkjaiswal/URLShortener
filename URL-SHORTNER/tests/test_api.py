"""Behavioral API tests covering the complete link lifecycle."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from app.core.security import COOKIE_NAME
from app.db.models import Url
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError


def create_link(client, **extra):
    response = client.post("/api/v1/shorten", json={"url": "https://example.com/path?q=1#section", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_health_check(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_complete_lifecycle(client):
    link = create_link(client)
    assert len(link["short_code"]) == 7
    assert link["short_url"] == f"http://testserver/{link['short_code']}"
    response = client.get(f"/{link['short_code']}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://example.com/path?q=1#section"
    assert response.headers["cache-control"] == "no-store"
    stats = client.get(f"/api/v1/stats/{link['short_code']}").json()
    assert stats["clicks"] == 1
    assert stats["created_at"].endswith("Z")
    assert stats["last_accessed"].endswith("Z")
    assert client.get("/api/v1/urls").json()["items"][0]["short_code"] == link["short_code"]
    assert client.get("/api/v1/summary").json() == {
        "total_links": 1,
        "total_clicks": 1,
        "active_links": 1,
        "expired_links": 0,
    }
    assert client.delete(f"/api/v1/urls/{link['short_code']}").status_code == 204
    assert client.get(f"/{link['short_code']}").status_code == 404
    assert client.get(f"/api/v1/stats/{link['short_code']}").status_code == 404
    assert client.delete(f"/api/v1/urls/{link['short_code']}").status_code == 404
    assert client.get("/api/v1/summary").json()["total_links"] == 0


def test_expiry_preserves_owner_analytics(client, db_session):
    link = create_link(client, ttl_seconds=60)
    assert link["expires_at"].endswith("Z")
    # Read the persisted timestamp: SQLite must not return a naive datetime.
    record = db_session.scalar(select(Url).where(Url.short_code == link["short_code"]))
    assert record.expires_at.tzinfo is not None
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/{link['short_code']}").status_code == 404
    assert client.head(f"/{link['short_code']}").status_code == 404
    stats = client.get(f"/api/v1/stats/{link['short_code']}").json()
    assert stats["clicks"] == 0
    assert client.get("/api/v1/summary").json()["expired_links"] == 1
    assert client.delete(f"/api/v1/urls/{link['short_code']}").status_code == 204


def test_head_does_not_count_as_a_click(client):
    link = create_link(client)
    assert client.head(f"/{link['short_code']}", follow_redirects=False).status_code == 307
    assert client.get(f"/api/v1/stats/{link['short_code']}").json()["clicks"] == 0


def test_concurrent_clicks_are_not_lost(client):
    link = create_link(client)
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(
            executor.map(
                lambda _: client.get(f"/{link['short_code']}", follow_redirects=False).status_code, range(40)
            )
        )
    assert responses == [307] * 40
    assert client.get(f"/api/v1/stats/{link['short_code']}").json()["clicks"] == 40


def test_workspace_isolation_and_public_redirects(client, app):
    link = create_link(client)
    with TestClient(app) as stranger:
        assert stranger.get("/api/v1/urls").status_code == 401
        assert stranger.post("/api/v1/shorten", json={"url": "https://example.com"}).status_code == 401
        assert stranger.get(f"/{link['short_code']}", follow_redirects=False).status_code == 307
        stranger.get("/api/v1/session")
        assert stranger.get("/api/v1/urls").json()["total"] == 0
        assert stranger.get("/api/v1/summary").json()["total_links"] == 0
        assert stranger.get(f"/api/v1/stats/{link['short_code']}").status_code == 404
        assert stranger.delete(f"/api/v1/urls/{link['short_code']}").status_code == 404
    assert client.get(f"/api/v1/stats/{link['short_code']}").status_code == 200


def test_cookie_is_httponly_and_stable(client):
    original = client.cookies.get(COOKIE_NAME)
    response = client.get("/api/v1/session")
    assert client.cookies.get(COOKIE_NAME) == original
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"


def test_pagination_search_and_literal_wildcards(client):
    for i in range(12):
        create_link(client, url=f"https://example.com/page/{i}")
    first = client.get("/api/v1/urls?limit=5").json()
    second = client.get("/api/v1/urls?limit=5&offset=5").json()
    assert first["total"] == second["total"] == 12
    assert len(first["items"]) == len(second["items"]) == 5
    assert set(i["short_code"] for i in first["items"]).isdisjoint(i["short_code"] for i in second["items"])
    assert first["items"][0]["original_url"].endswith("/11")
    assert client.get("/api/v1/urls?q=page/11").json()["total"] == 1
    assert client.get("/api/v1/urls?q=%25").json()["total"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"ttl_seconds": 0},
        {"ttl_seconds": -1},
        {"ttl_seconds": 31536001},
        {"ttl_seconds": 1.5},
        {"ttl_seconds": True},
        {"ttl_seconds": "60"},
        {"url": "a" * 2049},
        {"unexpected": "field"},
    ],
)
def test_invalid_payload_is_rejected(client, payload):
    assert client.post("/api/v1/shorten", json={"url": "https://example.com", **payload}).status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "javascript:alert(1)",
        "https://user:password@example.com",
        "https://example.com:99999",
        "https://bad host.com",
        "https://example.com/\nheader",
        "http://testserver/loop",
        "https://[invalid",
    ],
)
def test_invalid_destinations(client, url):
    assert client.post("/api/v1/shorten", json={"url": url}).status_code == 400


def test_rate_limit(client, app):
    app.state.creation_limiter.limit = 2
    create_link(client)
    create_link(client)
    response = client.post("/api/v1/shorten", json={"url": "https://example.com"})
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60


def test_cross_origin_mutations_are_rejected(client):
    response = client.post(
        "/api/v1/shorten", json={"url": "https://example.com"}, headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert (
        client.post(
            "/api/v1/shorten", json={"url": "https://example.com"}, headers={"origin": "http://testserver"}
        ).status_code
        == 201
    )


def test_database_failure_returns_safe_error(client, monkeypatch):
    from app.repositories.url_repository import UrlRepository

    def broken(*args, **kwargs):
        raise OperationalError("SELECT secret", {}, Exception("private connection details"))

    monkeypatch.setattr(UrlRepository, "summary", broken)
    response = client.get("/api/v1/summary")
    assert response.status_code == 503
    assert "secret" not in response.text and "private" not in response.text


def test_restart_persistence_and_cross_instance_delete(client, settings):
    link = create_link(client)
    with TestClient(create_app(settings)) as second:
        second.cookies.update(client.cookies)
        assert second.get(f"/{link['short_code']}", follow_redirects=False).status_code == 307
        assert second.get(f"/api/v1/stats/{link['short_code']}").json()["clicks"] == 1
        assert second.delete(f"/api/v1/urls/{link['short_code']}").status_code == 204
    assert client.get(f"/{link['short_code']}").status_code == 404


def test_unknown_links_and_browser_error_page(client):
    assert client.get("/missing").json() == {"detail": "Short URL not found"}
    response = client.get("/missing", headers={"accept": "text/html"})
    assert response.status_code == 404
    assert "A little lost?" in response.text
    assert client.get("/api/v1/stats/missing").status_code == 404
