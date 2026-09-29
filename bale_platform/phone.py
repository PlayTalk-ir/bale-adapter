"""Phone number normalization for Bale auth and outbound lookup."""

from __future__ import annotations

import re

# Persian (۰۱۲۳…) and Arabic-Indic digits → ASCII digits.
_DIGIT_MAP = {ord(ch): str(i) for i, ch in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGIT_MAP.update({ord(ch): str(i) for i, ch in enumerate("٠١٢٣٤٥٦٧٨٩")})

# Iranian mobile after normalization: 989 + 9 digits (12 total)
_IR_MOBILE_RE = re.compile(r"^989\d{9}$")


def to_ascii_digits(raw: str) -> str:
    """Map Persian/Arabic-Indic digits to ASCII; leave other characters alone."""
    return str(raw or "").translate(_DIGIT_MAP)


def normalize_phone_digits(raw: str) -> str:
    """Normalize Iranian/local formats to Bale digits (98XXXXXXXXXX)."""
    digits = to_ascii_digits(raw).replace("+", "").replace(" ", "").replace("-", "")
    if digits.startswith("0098"):
        digits = digits[4:]
    if not digits.isdigit() or len(digits) < 10:
        raise ValueError("invalid phone format — must be digits, optionally prefixed +")
    if digits.startswith("0"):
        digits = "98" + digits[1:]
    elif digits.startswith("9") and not digits.startswith("98"):
        digits = "98" + digits
    elif not digits.startswith("98"):
        digits = "98" + digits
    return digits


def normalize_phone_int(raw: str) -> int:
    return int(normalize_phone_digits(raw))


def is_iranian_mobile_digits(digits: str) -> bool:
    """True if digits are normalized Iranian mobile (989XXXXXXXXX)."""
    return bool(_IR_MOBILE_RE.match(digits))


def try_normalize_iranian_mobile(raw: str) -> str | None:
    """Return normalized mobile digits or None if not a valid Iranian mobile."""
    try:
        digits = normalize_phone_digits(raw.strip())
    except ValueError:
        return None
    if not is_iranian_mobile_digits(digits):
        return None
    return digits


def looks_like_phone_target(target: str) -> bool:
    """Heuristic: target should be resolved via contact search, not as Bale user id."""
    t = to_ascii_digits(target).strip()
    if not t:
        return False
    if t.startswith("+") or t.startswith("00"):
        return True
    if t.startswith("0"):
        return True
    if t.isdigit():
        # Local mobile without leading 0: 9xxxxxxxxx (10 digits)
        if len(t) == 10 and t.startswith("9"):
            return True
        # Normalized or partial international mobile
        if len(t) == 11 and t.startswith("98"):
            return True
        if len(t) == 12 and t.startswith("98"):
            return True
    return False


def mask_phone(digits: str) -> str:
    """Mask normalized phone for API responses and logs (98912***4567)."""
    if len(digits) < 8:
        return "***"
    return digits[:5] + "***" + digits[-4:]
