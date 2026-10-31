"""Validate redirect destinations without fetching user-provided URLs."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import HttpUrl, TypeAdapter, ValidationError

URL_ADAPTER = TypeAdapter(HttpUrl)


def is_valid_url(url: str) -> bool:
    if not url or len(url) > 2048:
        return False
    value = url.strip()
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        URL_ADAPTER.validate_python(value)
        return bool(
            parsed.hostname
            and parsed.scheme.lower() in {"http", "https"}
            and parsed.username is None
            and parsed.password is None
        )
    except (ValueError, ValidationError):
        return False
