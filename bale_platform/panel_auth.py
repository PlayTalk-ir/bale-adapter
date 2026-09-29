"""Session cookie + CSRF helpers for the admin panel (stdlib only).

The panel can send messages as the company Bale account, so it is gated by a
single operator token (``BALE_PANEL_TOKEN``). A successful login stores a
signed, expiring cookie; every state-changing POST must also carry a CSRF
token derived from that cookie.

Pure functions — no aiohttp import — so they are unit-testable in CI.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional, Union

SESSION_COOKIE = "bale_panel"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600
MIN_TOKEN_LENGTH = 12
MIN_PASSWORD_LENGTH = 8
DEFAULT_PANEL_USER = "admin"


def _sign(secret: str, message: str) -> str:
    digest = hmac.new(
        str(secret).encode("utf-8"), str(message).encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def compare(configured: str, supplied: str) -> bool:
    """Constant-time token comparison."""
    if not configured or not supplied:
        return False
    return hmac.compare_digest(
        str(configured).encode("utf-8"), str(supplied).encode("utf-8")
    )


def make_session(
    secret: str,
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
    now: Optional[float] = None,
) -> str:
    """``<expiry>.<hmac>`` cookie value."""
    expires = int((time.time() if now is None else now) + int(ttl))
    return f"{expires}.{_sign(secret, f'session:{expires}')}"


def verify_session(
    secret: str, value: str, *, now: Optional[float] = None
) -> bool:
    """True when the cookie is well-formed, unexpired and correctly signed."""
    if not value or "." not in str(value):
        return False
    expires_text, _, signature = str(value).partition(".")
    if not expires_text.isdigit():
        return False
    current = time.time() if now is None else now
    if int(expires_text) < current:
        return False
    return hmac.compare_digest(signature, _sign(secret, f"session:{expires_text}"))


def csrf_token(secret: str, session_value: str) -> str:
    """Per-session token embedded in every form."""
    return _sign(secret, f"csrf:{session_value}")


def verify_csrf(
    secret: str, session_value: str, supplied: str
) -> bool:
    if not supplied or not session_value:
        return False
    return hmac.compare_digest(
        csrf_token(secret, session_value), str(supplied)
    )


def generate_token(length: int = 32) -> str:
    """Random operator token (used when none is configured)."""
    raw = base64.urlsafe_b64encode(__import__("os").urandom(48)).decode("ascii")
    return raw.rstrip("=")[: max(MIN_TOKEN_LENGTH, length)]


def token_ok(token: str) -> bool:
    """Reject dangerously short signing secrets."""
    return len(str(token or "")) >= MIN_TOKEN_LENGTH


def password_ok(password: str) -> bool:
    """Reject dangerously short operator passwords."""
    return len(str(password or "")) >= MIN_PASSWORD_LENGTH
