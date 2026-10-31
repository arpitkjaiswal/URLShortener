"""Tests for the tiny frontend."""

from __future__ import annotations


def test_root_serves_html(client) -> None:
    """The root path should serve the browser frontend."""

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "URL Shortener" in response.text