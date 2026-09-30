"""HTTP Basic auth for password-protected API docs (panel operator credentials)."""

from __future__ import annotations

import base64
from typing import Optional, Tuple

from aiohttp import web

from bale_platform import panel_auth


def parse_basic(header: Optional[str]) -> Optional[Tuple[str, str]]:
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return None
    try:
        raw = base64.b64decode(parts[1].strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    user, sep, password = raw.partition(":")
    if not sep:
        return None
    return user, password


def operator_credentials_ok(username: str, password: str, supplied_user: str, supplied_password: str) -> bool:
    return panel_auth.compare(username, supplied_user) and panel_auth.compare(password, supplied_password)


def unauthorized() -> web.Response:
    return web.Response(
        status=401,
        text="Authentication required",
        headers={"WWW-Authenticate": 'Basic realm="Bale API Docs", charset="UTF-8"'},
    )


def docs_not_configured() -> web.Response:
    return web.json_response(
        {
            "error": {
                "code": "docs_unavailable",
                "message": "API docs require BALE_PANEL_PASSWORD on the server",
                "details": {},
            }
        },
        status=503,
    )
