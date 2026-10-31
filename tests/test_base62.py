"""Tests for Base62 encoding."""

from __future__ import annotations

import pytest

from app.utils.base62 import decode, encode


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "0"),
        (1, "1"),
        (61, "z"),
        (62, "10"),
        (12345, encode(12345)),
    ],
)
def test_encode(number: int, expected: str) -> None:
    """Encode integers into Base62 strings."""

    assert encode(number) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        ("1", 1),
        ("z", 61),
        ("10", 62),
        (encode(12345), 12345),
    ],
)
def test_decode(value: str, expected: int) -> None:
    """Decode Base62 strings into integers."""

    assert decode(value) == expected


def test_decode_rejects_invalid_characters() -> None:
    """Reject characters outside the Base62 alphabet."""

    with pytest.raises(ValueError):
        decode("abc$")