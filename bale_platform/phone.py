"""Phone number normalization for Bale auth and outbound lookup."""

from __future__ import annotations

# Persian (۰۱۲۳٤۵۶۷۸۹) and Arabic-Indic (٠١٢٣٤٥٦٧٨٩) digits -> ASCII digits.
# Support staff routinely paste numbers from Persian keyboards/Excel.
_DIGIT_MAP = {ord(ch): str(i) for i, ch in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGIT_MAP.update({ord(ch): str(i) for i, ch in enumerate("٠١٢٣٤٥٦٧٨٩")})


def to_ascii_digits(raw: str) -> str:
    """Map Persian/Arabic-Indic digits to ASCII; leave other characters alone."""
    return str(raw or "").translate(_DIGIT_MAP)


def normalize_phone_digits(raw: str) -> str:
    """Normalize Iranian/local formats to Bale digits (98XXXXXXXXXX)."""
    digits = to_ascii_digits(raw).replace("+", "").replace(" ", "").replace("-", "")
    if not digits.isdigit() or len(digits) < 10:
        raise ValueError("invalid phone format — must be digits, optionally prefixed +")
    if digits.startswith("0"):
        digits = "98" + digits[1:]
    elif not digits.startswith("98"):
        digits = "98" + digits
    return digits


def normalize_phone_int(raw: str) -> int:
    return int(normalize_phone_digits(raw))
