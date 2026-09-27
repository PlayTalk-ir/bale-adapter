"""Logging helpers — never log secrets or full PII."""

from __future__ import annotations

import hashlib


def text_log_fingerprint(text: str) -> str:
    """Short hash of message body for logs (not reversible)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
