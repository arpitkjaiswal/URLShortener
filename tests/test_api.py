"""Integration tests for the HTTP API."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Health endpoint should confirm the service is running."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_url_and_redirect_and_stats(client: TestClient) -> None:
    """Shorten a URL, redirect it, and verify analytics update."""

    shorten_response = client.post("/api/v1/shorten", json={"url": "https://example.com"})

    assert shorten_response.status_code == 201
    body = shorten_response.json()
    assert body["short_code"]
    assert body["short_url"].endswith(f"/{body['short_code']}")

    redirect_response = client.get(f"/{body['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == "https://example.com"

    stats_response = client.get(f"/api/v1/stats/{body['short_code']}")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["original_url"] == "https://example.com"
    assert stats["short_code"] == body["short_code"]
    assert stats["clicks"] == 1
    assert stats["created_at"]
    assert stats["expires_at"] is None
    assert stats["last_accessed"]


def test_create_url_with_ttl_and_expire_it(client: TestClient, db_session) -> None:
    """Shortening with a TTL should persist an expiry timestamp and stop working after expiry."""

    shorten_response = client.post("/api/v1/shorten", json={"url": "https://example.com", "ttl_seconds": 60})

    assert shorten_response.status_code == 201
    body = shorten_response.json()
    assert body["expires_at"] is not None

    from datetime import datetime, timezone, timedelta

    from app.db.models import Url

    record = db_session.query(Url).filter(Url.short_code == body["short_code"]).one()
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    # Clear application cache to force database lookup of modified TTL
    client.app.state.url_cache.clear()

    redirect_response = client.get(f"/{body['short_code']}", follow_redirects=False)
    stats_response = client.get(f"/api/v1/stats/{body['short_code']}")

    assert redirect_response.status_code == 404
    assert redirect_response.json() == {"detail": "Short URL not found"}
    assert stats_response.status_code == 404
    assert stats_response.json() == {"detail": "Short URL not found"}


def test_rejects_invalid_url(client: TestClient) -> None:
    """Invalid URLs should return a 400 response."""

    response = client.post("/api/v1/shorten", json={"url": "ftp://example.com"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid URL"}


def test_missing_short_code_returns_404(client: TestClient) -> None:
    """Unknown short codes should return 404 on redirect and analytics."""

    redirect_response = client.get("/missing", follow_redirects=False)
    stats_response = client.get("/api/v1/stats/missing")

    assert redirect_response.status_code == 404
    assert redirect_response.json() == {"detail": "Short URL not found"}
    assert stats_response.status_code == 404
    assert stats_response.json() == {"detail": "Short URL not found"}