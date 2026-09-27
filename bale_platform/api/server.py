"""aiohttp application for Bale adapter HTTP API."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable, Optional

from aiohttp import web
from ulid import ULID

from bale_platform.api.auth import extract_bearer, token_valid
from bale_platform.api.serializers import row_to_status
from bale_platform.api.validation import validate_post_body
from bale_platform.api_config import ApiSettings
from bale_platform.outbox.store import OutboxStore

logger = logging.getLogger("bale.api")


class ApiRuntime:
    def __init__(
        self,
        settings: ApiSettings,
        store: OutboxStore,
        *,
        session_connected: Callable[[], bool],
        sending_paused: Callable[[], bool],
        resume_breaker: Callable[[], None],
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.session_connected = session_connected
        self.sending_paused = sending_paused
        self.resume_breaker = resume_breaker
        self.clock = clock or time.time

    def _error(self, code: str, message: str, details: dict | None = None, status: int = 400) -> web.Response:
        return web.json_response(
            {"error": {"code": code, "message": message, "details": details or {}}},
            status=status,
        )

    def _auth(self, request: web.Request) -> Optional[str]:
        token = extract_bearer(request.headers.get("Authorization"))
        if not token or not token_valid(token, self.settings.tokens):
            return None
        return token

    def create_app(self) -> web.Application:
        @web.middleware
        async def request_id_middleware(request: web.Request, handler):
            rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
            request["request_id"] = rid
            try:
                response = await handler(request)
            except web.HTTPException as exc:
                exc.headers["X-Request-Id"] = rid
                raise
            except Exception:
                logger.exception("unhandled API error")
                response = web.json_response(
                    {"error": {"code": "internal", "message": "internal error", "details": {}}},
                    status=500,
                )
            response.headers["X-Request-Id"] = rid
            return response

        app = web.Application(middlewares=[request_id_middleware])
        app.router.add_get("/healthz", self.healthz)
        app.router.add_get("/readyz", self.readyz)
        app.router.add_post("/v1/messages", self.post_messages)
        app.router.add_get("/v1/messages", self.get_messages_query)
        app.router.add_get("/v1/messages/{message_id}", self.get_message)
        app.router.add_post("/v1/admin/resume", self.admin_resume)
        return app

    async def healthz(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def readyz(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        return web.json_response(
            {
                "session_connected": self.session_connected(),
                "queue_depth": self.store.queue_depth(),
                "paused": self.sending_paused() or self.store.breaker_open(),
                "send_mode": self.settings.send_mode,
            }
        )

    async def post_messages(self, request: web.Request) -> web.Response:
        token = self._auth(request)
        if not token:
            return self._error("unauthorized", "missing or invalid token", status=401)
        if self.sending_paused() or self.store.breaker_open():
            return web.json_response(
                {"error": {"code": "sending_paused", "message": "sending is paused", "details": {}}},
                status=503,
                headers={"Retry-After": "60"},
            )
        allowed, retry = self.store.intake_allowed(
            token, self.settings.rate_per_min, self.settings.queue_max
        )
        if not allowed:
            return web.json_response(
                {"error": {"code": "rate_limited", "message": "too many requests", "details": {}}},
                status=429,
                headers={"Retry-After": str(retry or 60)},
            )
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return self._error("recipient_invalid", "invalid JSON body", status=422)
        if not isinstance(body, dict):
            return self._error("recipient_invalid", "body must be object", status=422)
        norm, err = validate_post_body(body, self.settings.default_ttl_s, self.settings.max_ttl_s)
        if err:
            return web.json_response({"error": err["error"]}, status=err["status"])
        from bale_platform.outbox.store import OutboxStore as OS

        phash = OS.payload_hash(norm["recipient"]["norm_key"], norm["text"])
        existing = self.store.get_by_idempotency(norm["idempotency_key"])
        now = self.clock()
        if existing:
            if existing["payload_hash"] != phash:
                return self._error(
                    "idempotency_conflict",
                    "idempotency key reused with different payload",
                    status=409,
                )
            return web.json_response(
                {
                    "message_id": existing["message_id"],
                    "status": existing["status"],
                    "idempotency_key": existing["idempotency_key"],
                },
                status=200,
            )
        message_id = str(ULID())
        expires_at = now + norm["ttl_seconds"]
        self.store.insert_message(
            message_id=message_id,
            idempotency_key=norm["idempotency_key"],
            payload_hash=phash,
            text=norm["text"],
            meta=norm.get("meta"),
            recipient_type=norm["recipient"]["type"],
            recipient_masked=norm["recipient"]["masked"],
            recipient_secret=json.dumps(norm["recipient"]["secret"]),
            expires_at=expires_at,
            now=now,
        )
        logger.info(
            "queued message_id=%s idempotency_key=%s text_len=%d",
            message_id,
            norm["idempotency_key"],
            len(norm["text"]),
        )
        return web.json_response(
            {
                "message_id": message_id,
                "status": "queued",
                "idempotency_key": norm["idempotency_key"],
            },
            status=202,
        )

    async def get_message(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        mid = request.match_info["message_id"]
        row = self.store.get_by_message_id(mid)
        if not row:
            return self._error("not_found", "message not found", status=404)
        return web.json_response(row_to_status(row))

    async def get_messages_query(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        key = request.query.get("idempotency_key")
        if not key:
            return self._error("not_found", "idempotency_key query required", status=404)
        row = self.store.get_by_idempotency(key)
        if not row:
            return self._error("not_found", "message not found", status=404)
        return web.json_response(row_to_status(row))

    async def admin_resume(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        self.resume_breaker()
        return web.json_response({"ok": True})


def create_app(runtime: ApiRuntime) -> web.Application:
    return runtime.create_app()


async def run_api_server(
    runtime: ApiRuntime,
    host: str,
    port: int,
) -> web.AppRunner:
    app = create_app(runtime)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Bale API listening on %s:%s", host, port)
    return runner
