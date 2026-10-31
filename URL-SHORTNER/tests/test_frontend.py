"""Tests for the tiny frontend."""

from __future__ import annotations


def test_root_serves_html(client) -> None:
    """The root path should serve the browser frontend."""

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "URL Shortener" in response.text


def test_dashboard_assets_and_security_headers(client):
    response = client.get("/")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/styles.css").status_code == 200
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "127.0.0.1" not in script.text and "localhost" not in script.text
    assert "innerHTML" not in script.text
    assert client.get("/openapi.json").status_code == 200
