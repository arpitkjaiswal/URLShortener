"""Validation helpers."""

from __future__ import annotations

from urllib.parse import urlsplit


ALLOWED_SCHEMES = {"http", "https"}


def is_valid_url(url: str) -> bool:
    """Return True when the URL is a well-formed HTTP or HTTPS URL."""

    if not url or not url.strip():
        return False

    candidate = url.strip()
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in candidate) or "\\" in candidate:
        return False
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port
        if parsed.username is not None or parsed.password is not None:
            return False
    except ValueError:
        return False

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return False
    if not parsed.netloc:
        return False
    if parsed.hostname is None:
        return False
    return True