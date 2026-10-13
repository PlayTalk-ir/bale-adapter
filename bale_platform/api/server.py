"""aiohttp application for Bale adapter HTTP API."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from aiohttp import web
from ulid import ULID

from bale_platform.api.auth import extract_bearer, token_valid
from bale_platform.api_token_store import verification_sets
from bale_platform.api.docs_auth import (
    docs_json_unauthorized,
    docs_not_configured,
    docs_operator_ok,
    docs_session_ok,
    set_docs_session_cookie,
)
from bale_platform.api.docs_login import login_page
from bale_platform.api.openapi_spec import build_openapi
from bale_platform.api.serializers import row_to_status
from bale_platform.api.swagger_ui import SWAGGER_UI_HTML
from bale_platform.api.validation import validate_post_body
from bale_platform.api_config import ApiSettings
from bale_platform import panel_auth
from bale_platform.contact_store import ContactBook, merge_outbox_phones_into_book
from bale_platform.outbox.store import OutboxStore
from bale_platform.phone import panel_mobile_from_bale_digits
from bale_platform.store import StoredMessage, SupportStore, is_private_chat_type

logger = logging.getLogger("bale.api")


class ApiRuntime:
    def __init__(
        self,
        settings: ApiSettings,
        store: OutboxStore,
        *,
        session_connected: Callable[[], bool],
        session_reason: Callable[[], str],
        sending_paused: Callable[[], bool],
        resume_breaker: Callable[[], None],
        clock: Optional[Callable[[], float]] = None,
        inbox: Optional[SupportStore] = None,
        contacts: Optional[ContactBook] = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.session_connected = session_connected
        self.session_reason = session_reason
        self.sending_paused = sending_paused
        self.resume_breaker = resume_breaker
        self.clock = clock or time.time
        self.inbox = inbox
        self.contacts = contacts

    def _error(self, code: str, message: str, details: dict | None = None, status: int = 400) -> web.Response:
        return web.json_response(
            {"error": {"code": code, "message": message, "details": details or {}}},
            status=status,
        )

    def _auth(self, request: web.Request) -> Optional[str]:
        header = request.headers.get("Authorization")
        if header and header.lower().startswith("basic "):
            return None
        token = extract_bearer(header)
        plain, hashed = verification_sets()
        if self.settings.tokens:
            plain = plain + [t for t in self.settings.tokens if t not in plain]
        if not token or not token_valid(token, plain, hashed):
            return None
        return token

    def _docs_allowed(self, request: web.Request) -> bool:
        if not self.settings.docs_password or not panel_auth.password_ok(self.settings.docs_password):
            return False
        if docs_session_ok(self.settings.docs_token, request):
            return True
        return False

    def _require_docs(self, request: web.Request) -> Optional[web.Response]:
        if not self.settings.docs_password or not panel_auth.password_ok(self.settings.docs_password):
            return docs_not_configured()
        if self._docs_allowed(request):
            return None
        return None

    def _require_docs_or_json_401(self, request: web.Request) -> Optional[web.Response]:
        if not self.settings.docs_password or not panel_auth.password_ok(self.settings.docs_password):
            return docs_not_configured()
        if self._docs_allowed(request):
            return None
        return docs_json_unauthorized()

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
        app.router.add_get("/v1/docs", self.swagger_docs)
        app.router.add_post("/v1/docs/login", self.swagger_docs_login)
        app.router.add_get("/v1/openapi.json", self.openapi_json)
        app.router.add_get("/v1/session", self.get_session)
        app.router.add_get("/v1/inbox/events", self.get_inbox_events)
        app.router.add_get("/v1/contacts", self.get_contacts)
        app.router.add_get(
            "/v1/inbox/chats/{chat_id}/history", self.get_inbox_history
        )
        app.router.add_post("/v1/messages", self.post_messages)
        app.router.add_get("/v1/messages", self.get_messages_query)
        app.router.add_get("/v1/messages/{message_id}", self.get_message)
        app.router.add_post("/v1/admin/resume", self.admin_resume)
        return app

    async def healthz(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def swagger_docs(self, request: web.Request) -> web.Response:
        blocked = self._require_docs(request)
        if blocked:
            return blocked
        if not self._docs_allowed(request):
            return web.Response(
                text=login_page(default_username=self.settings.docs_user),
                content_type="text/html",
                status=401,
            )
        return web.Response(text=SWAGGER_UI_HTML, content_type="text/html")

    async def swagger_docs_login(self, request: web.Request) -> web.Response:
        blocked = self._require_docs(request)
        if blocked:
            return blocked
        if not panel_auth.token_ok(self.settings.docs_token):
            return web.Response(
                text=login_page(
                    default_username=self.settings.docs_user,
                    error="Docs login is not configured (BALE_PANEL_TOKEN missing on server).",
                ),
                content_type="text/html",
                status=503,
            )
        form = await request.post()
        user = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))
        if not docs_operator_ok(
            self.settings.docs_user,
            self.settings.docs_password,
            user,
            password,
        ):
            return web.Response(
                text=login_page(
                    default_username=self.settings.docs_user,
                    error="Incorrect username or password.",
                ),
                content_type="text/html",
                status=401,
            )
        response = web.HTTPFound("/v1/docs")
        set_docs_session_cookie(response, request, self.settings.docs_token)
        raise response

    async def openapi_json(self, request: web.Request) -> web.Response:
        denied = self._require_docs_or_json_401(request)
        if denied:
            return denied
        base = request.headers.get("X-Forwarded-Prefix", "").rstrip("/")
        if not base and request.host:
            scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
            base = f"{scheme}://{request.host}"
        spec = build_openapi(base)
        return web.json_response(spec)

    async def readyz(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        return web.json_response(
            {
                "session_connected": self.session_connected(),
                "session_reason": self.session_reason(),
                "queue_depth": self.store.queue_depth(),
                "paused": self.sending_paused() or self.store.breaker_open(),
                "send_mode": self.settings.send_mode,
            }
        )

    async def get_session(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        connected = bool(self.session_connected())
        reason = self.session_reason() or ""
        if connected:
            state = "open"
            last_error = None
        elif reason == "connecting":
            state = "connecting"
            last_error = None
        elif reason == "session_file_missing":
            state = "logged_out"
            last_error = None
        elif reason.startswith("connect_failed"):
            state = "closed"
            last_error = reason
        else:
            state = reason or "closed"
            last_error = None
        return web.json_response(
            {
                "state": state,
                "connected": connected,
                "qr": None,
                "qr_data_url": None,
                "me": None,
                "last_error": last_error,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _limit(self, request: web.Request, default: int, maximum: int) -> int:
        raw = request.query.get("limit")
        if raw is None or not str(raw).strip():
            value = default
        else:
            try:
                value = int(raw)
            except ValueError:
                value = default
        if not value:
            value = default
        return max(1, min(value, maximum))

    def _reply_window_open(self, bale_user_id: str) -> bool:
        if self.inbox is None:
            return False
        last_ms = self.inbox.last_incoming_ms(str(bale_user_id))
        if last_ms is None:
            return False
        return self.clock() * 1000 - last_ms <= self.settings.reply_window_h * 3600 * 1000

    def _chat_blob(self, chat_id: str) -> dict:
        from bale_platform.contact_store import entry_display_name

        name = ""
        username = ""
        if self.inbox is not None:
            label = self.inbox.get_label(str(chat_id))
            if label and label.strip() and label.strip() != str(chat_id):
                name = label.strip()
        phone = None
        if self.contacts is not None:
            try:
                entry = self.contacts.get(chat_id)
            except (TypeError, ValueError):
                entry = None
            if entry is not None:
                if not name:
                    name = entry_display_name(entry)
                username = entry.username or ""
                if entry.phone_digits:
                    phone = panel_mobile_from_bale_digits(entry.phone_digits)
        if phone is None:
            try:
                uid = int(chat_id)
            except (TypeError, ValueError):
                uid = None
            if uid is not None:
                digits = self.store.get_inbox_chat_phone(uid)
                if digits:
                    phone = panel_mobile_from_bale_digits(digits)
        return {"name": name, "username": username, "phone": phone}

    async def get_contacts(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        if self.contacts is not None:
            merge_outbox_phones_into_book(self.contacts, self.store)
            payload = {"contacts": self.contacts.list_for_api()}
        else:
            payload = {"contacts": []}
        return web.json_response(payload)

    def _events_payload(self, rows: list[StoredMessage]) -> list[dict]:
        blobs = {row.chat_id: self._chat_blob(row.chat_id) for row in rows}
        return [
            {
                "seq": row.seq,
                "chat_id": row.chat_id,
                "message_id": row.message_id,
                "direction": row.direction,
                "kind": row.kind,
                "text": row.text,
                "date_ms": row.date_ms,
                "sender_id": row.sender_id,
                "chat": blobs[row.chat_id],
            }
            for row in rows
        ]

    async def get_inbox_events(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        raw_after = request.query.get("after")
        try:
            after = int(raw_after) if raw_after else 0
        except ValueError:
            after = 0
        limit = self._limit(request, 200, 1000)
        rows = self.inbox.events_after(after, limit) if self.inbox is not None else []
        rows = [r for r in rows if is_private_chat_type(r.chat_type)]
        return web.json_response(
            {
                "events": self._events_payload(rows),
                "next_after": rows[-1].seq if rows else after,
                "has_more": len(rows) == limit,
            }
        )

    async def get_inbox_history(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return self._error("unauthorized", "missing or invalid token", status=401)
        chat_id = request.match_info["chat_id"]
        limit = self._limit(request, 100, 500)
        rows = self.inbox.history(chat_id, limit) if self.inbox is not None else []
        return web.json_response({"events": self._events_payload(rows)})

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
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return self._error("recipient_invalid", "invalid JSON body", status=422)
        if not isinstance(body, dict):
            return self._error("recipient_invalid", "body must be object", status=422)
        norm, err = validate_post_body(body, self.settings.default_ttl_s, self.settings.max_ttl_s)
        if err:
            return web.json_response({"error": err["error"]}, status=err["status"])
        if norm.get("mode") == "reply":
            uid = norm["items"][0]["recipient"]["secret"]["bale_user_id"]
            if not self._reply_window_open(str(uid)):
                return self._error(
                    "reply_window_closed",
                    "recipient has not messaged us recently; reply mode is not allowed",
                    {"window_hours": self.settings.reply_window_h},
                    status=422,
                )
        from bale_platform.outbox.store import OutboxStore as OS

        items = norm["items"]
        now = self.clock()
        planned_new = 0
        replay: list[dict] = []
        for item in items:
            phash = OS.payload_hash(item["recipient"]["norm_key"], norm["text"])
            existing = self.store.get_by_idempotency(item["idempotency_key"])
            if existing:
                if existing["payload_hash"] != phash:
                    return self._error(
                        "idempotency_conflict",
                        "idempotency key reused with different payload",
                        status=409,
                    )
                replay.append(
                    {
                        "message_id": existing["message_id"],
                        "status": existing["status"],
                        "idempotency_key": existing["idempotency_key"],
                        "recipient": {
                            "type": existing.get("recipient_type"),
                            "masked": existing.get("recipient_masked"),
                        },
                    }
                )
            else:
                planned_new += 1
                item["payload_hash"] = phash

        if planned_new == 0:
            return self._messages_response(norm, replay, status=200)

        allowed, retry = self.store.intake_allowed(
            token,
            self.settings.rate_per_min,
            self.settings.queue_max,
            slots=planned_new,
        )
        if not allowed:
            return web.json_response(
                {"error": {"code": "rate_limited", "message": "too many requests", "details": {}}},
                status=429,
                headers={"Retry-After": str(retry or 60)},
            )

        expires_at = now + norm["ttl_seconds"]
        created: list[dict] = []
        for item in items:
            if "payload_hash" not in item:
                continue
            message_id = str(ULID())
            rec = item["recipient"]
            self.store.insert_message(
                message_id=message_id,
                idempotency_key=item["idempotency_key"],
                payload_hash=item["payload_hash"],
                text=norm["text"],
                meta=norm.get("meta"),
                recipient_type=rec["type"],
                recipient_masked=rec["masked"],
                recipient_secret=json.dumps(rec["secret"]),
                expires_at=expires_at,
                now=now,
                mode=norm.get("mode", "send"),
            )
            logger.info(
                "queued message_id=%s idempotency_key=%s text_len=%d",
                message_id,
                item["idempotency_key"],
                len(norm["text"]),
            )
            created.append(
                {
                    "message_id": message_id,
                    "status": "queued",
                    "idempotency_key": item["idempotency_key"],
                    "recipient": {"type": rec["type"], "masked": rec["masked"]},
                }
            )

        return self._messages_response(norm, replay + created, status=202)

    def _messages_response(self, norm: dict, rows: list[dict], *, status: int) -> web.Response:
        if norm.get("multi"):
            return web.json_response(
                {
                    "idempotency_key": norm["idempotency_key"],
                    "messages": rows,
                },
                status=status,
            )
        row = rows[0]
        return web.json_response(
            {
                "message_id": row["message_id"],
                "status": row["status"],
                "idempotency_key": row["idempotency_key"],
            },
            status=status,
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
