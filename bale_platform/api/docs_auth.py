"""Session cookie + password gate for API docs (panel operator credentials)."""

from __future__ import annotations

from aiohttp import web

from bale_platform import panel_auth


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


def docs_session_ok(signing_secret: str, request: web.Request) -> bool:
    if not signing_secret or not panel_auth.token_ok(signing_secret):
        return False
    cookie = request.cookies.get(panel_auth.SESSION_COOKIE, "")
    return panel_auth.verify_session(signing_secret, cookie)


def docs_password_ok(configured_password: str, supplied_password: str) -> bool:
    if not configured_password or not panel_auth.password_ok(configured_password):
        return False
    if not supplied_password:
        return False
    return panel_auth.compare(configured_password, supplied_password)


def set_docs_session_cookie(
    response: web.Response,
    request: web.Request,
    signing_secret: str,
) -> None:
    secure = request.secure or str(request.headers.get("X-Forwarded-Proto", "")).lower() == "https"
    response.set_cookie(
        panel_auth.SESSION_COOKIE,
        panel_auth.make_session(signing_secret),
        httponly=True,
        samesite="Strict",
        path="/",
        secure=secure,
    )


def docs_json_unauthorized() -> web.Response:
    return web.json_response(
        {
            "error": {
                "code": "unauthorized",
                "message": "Sign in at /v1/docs with the panel operator password",
                "details": {},
            }
        },
        status=401,
    )
