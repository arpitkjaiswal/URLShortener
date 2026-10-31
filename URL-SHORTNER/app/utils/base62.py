"""Base62 encoding helpers."""

from __future__ import annotations


ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(ALPHABET)


def encode(number: int) -> str:
    """Encode a non-negative integer into Base62."""

    if number < 0:
        raise ValueError("number must be non-negative")
    if number == 0:
        return ALPHABET[0]

    encoded = []
    current = number
    while current > 0:
        current, remainder = divmod(current, BASE)
        encoded.append(ALPHABET[remainder])
    return "".join(reversed(encoded))


def decode(value: str) -> int:
    """Decode a Base62 string into an integer."""

    if not value:
        raise ValueError("value must not be empty")

    number = 0
    for character in value:
        index = ALPHABET.find(character)
        if index == -1:
            raise ValueError(f"invalid Base62 character: {character}")
        number = number * BASE + index
    return number