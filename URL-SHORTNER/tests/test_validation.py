"""Tests for URL validation."""

from __future__ import annotations

import pytest

from app.utils.validators import is_valid_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path?q=1",
        "https://sub.domain.example.com",
    ],
)
def test_accepts_valid_urls(url: str) -> None:
    """Accept well-formed HTTP and HTTPS URLs."""

    assert is_valid_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "ftp://example.com",
        "example.com",
        "http:/example.com",
        "mailto:test@example.com",
    ],
)
def test_rejects_invalid_urls(url: str) -> None:
    """Reject malformed or unsupported URLs."""

    assert not is_valid_url(url)