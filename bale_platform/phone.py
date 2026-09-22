"""Phone number normalization for Bale auth and outbound lookup."""

from __future__ import annotations


def normalize_phone_digits(raw: str) -> str:
    """Normalize Iranian/local formats to Bale digits (98XXXXXXXXXX)."""
    digits = raw.replace("+", "").replace(" ", "").replace("-", "")
    if not digits.isdigit() or len(digits) < 10:
        raise ValueError("invalid phone format — must be digits, optionally prefixed +")
    if digits.startswith("0"):
        digits = "98" + digits[1:]
    elif not digits.startswith("98"):
        digits = "98" + digits
    return digits


def normalize_phone_int(raw: str) -> int:
    return int(normalize_phone_digits(raw))
