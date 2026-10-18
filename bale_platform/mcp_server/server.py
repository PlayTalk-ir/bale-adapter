"""MCP tools over the adapter HTTP API.

Official SDK: ``MCPServer`` (the mcp 2.x name of FastMCP). Tools return the
API JSON unchanged so phone masking and other response rules stay in the
adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from bale_platform.api.validation import validate_idempotency_key
from bale_platform.mcp_server.client import AdapterApiClient, AdapterApiError
from bale_platform.mcp_server.search import filter_contacts

INSTRUCTIONS = """\
You are connected to the shared PlayTalk Bale support account only through the \
bale-adapter HTTP API. You do not have the userbot session. Do not ask for an \
OTP, a phone login code, or the session file.

Read tools return the API JSON as-is. Message status masks phone numbers. \
Contact rows include a phone only when the API already stored one. Do not copy \
customer message text into git, tickets, or public docs unless a human asks.

list_inbox is the shared private-chat event feed (a seq cursor). It is not \
per-agent unread. Per-agent unread, mark-read/ack, KB facts, and FAQ topic \
mining are not HTTP endpoints, so they are not tools here.

send_message is a side effect. It queues one message in the outbox; the worker \
delivers it under the adapter rate limits, quiet hours, and send mode. Confirm \
the recipient and the exact text with the human before calling it. Do not call \
it to draft or preview.
"""

_READ = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

_SEND = ToolAnnotations(
    title="Send Bale message (queues through outbox)",
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)

_INBOX_LIMIT_MAX = 1000
_HISTORY_LIMIT_MAX = 500
_CONTACT_LIMIT_MAX = 100
_TEXT_MAX = 4000


def build_server(client: AdapterApiClient) -> MCPServer:
    """Register tools that call ``client``. Nothing is sent at registration time."""
    server = MCPServer(
        "bale-adapter",
        title="PlayTalk Bale adapter",
        instructions=INSTRUCTIONS,
    )

    def run(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return call()
        except AdapterApiError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        title="Adapter health",
        annotations=_READ,
        description=(
            "Liveness of the adapter HTTP API (GET /healthz). "
            "Does not show whether the Bale session is connected or whether sending is paused."
        ),
    )
    def adapter_health() -> dict[str, Any]:
        return run(lambda: client.get_json("/healthz"))

    @server.tool(
        title="Adapter readiness",
        annotations=_READ,
        description=(
            "Session, outbox queue depth, pause flag, and send mode (GET /readyz). "
            "send_mode is live, dry_run, or resolve_only. paused true means new sends "
            "are rejected until an operator resumes the worker. Read this before send_message."
        ),
    )
    def adapter_ready() -> dict[str, Any]:
        return run(lambda: client.get_json("/readyz"))

    @server.tool(
        title="Session status",
        annotations=_READ,
        description=(
            "Userbot session state (GET /v1/session). Bale uses a phone session file, "
            "so qr and qr_data_url are always null. state is open when the userbot is connected. "
            "This tool does not return a login QR or a session secret."
        ),
    )
    def session_status() -> dict[str, Any]:
        return run(lambda: client.get_json("/v1/session"))

    @server.tool(
        title="List inbox events",
        annotations=_READ,
        description=(
            "Stored private-chat messages after a seq cursor (GET /v1/inbox/events), oldest first. "
            "Pass next_after back in as after to page. This is the shared inbox feed, not "
            "per-agent unread: the HTTP API has no agent ack state. Message text is included "
            "because the API returns it; do not commit that text. "
            "limit default 50, max 1000."
        ),
    )
    def list_inbox(after: int = 0, limit: int = 50) -> dict[str, Any]:
        cursor = _non_negative(after, "after")
        capped = _clamp(limit, default=50, maximum=_INBOX_LIMIT_MAX)
        return run(
            lambda: client.get_json(
                "/v1/inbox/events",
                params={"after": cursor, "limit": capped},
            )
        )

    @server.tool(
        title="Read chat",
        annotations=_READ,
        description=(
            "Recent stored messages for one private chat (GET /v1/inbox/chats/{chat_id}/history), "
            "oldest first, same event shape as list_inbox. chat_id is the numeric Bale peer id. "
            "limit default 50, max 500. Does not mark the chat read."
        ),
    )
    def read_chat(chat_id: str, limit: int = 50) -> dict[str, Any]:
        peer = _chat_id(chat_id)
        capped = _clamp(limit, default=50, maximum=_HISTORY_LIMIT_MAX)
        return run(
            lambda: client.get_json(
                f"/v1/inbox/chats/{peer}/history",
                params={"limit": capped},
            )
        )

    @server.tool(
        title="Search contacts",
        annotations=_READ,
        description=(
            "Search the adapter contact book. The API only offers GET /v1/contacts (the full book); "
            "this tool downloads that list and filters it locally on name, username, phone, and "
            "chat_id, using the same name folding as the support CLI. An empty query returns the "
            "first matches up to limit (default 20, max 100). "
            "Phones are present only when the API stored them (outreach, roster, or manual entry). "
            "Results are the API rows, not a live Bale directory lookup."
        ),
    )
    def search_contacts(query: str = "", limit: int = 20) -> dict[str, Any]:
        capped = _clamp(limit, default=20, maximum=_CONTACT_LIMIT_MAX)
        payload = run(lambda: client.get_json("/v1/contacts"))
        rows = payload.get("contacts")
        if not isinstance(rows, list):
            rows = []
        contacts = [row for row in rows if isinstance(row, dict)]
        matched = filter_contacts(contacts, query, limit=capped)
        return {"contacts": matched, "count": len(matched)}

    @server.tool(
        title="Outbox message status",
        annotations=_READ,
        description=(
            "Status of one queued or sent message. Pass message_id (the outbox ULID) or "
            "idempotency_key, not both. Phone recipients are masked in the API response "
            "(recipient.masked); this tool does not unmask them. "
            "status is queued, resolving, sending, sent, failed, expired, cancelled, "
            "or delivery_unknown."
        ),
    )
    def message_status(message_id: str = "", idempotency_key: str = "") -> dict[str, Any]:
        mid = _blank(message_id)
        key = _blank(idempotency_key)
        if bool(mid) == bool(key):
            raise ToolError("Pass exactly one of message_id or idempotency_key.")
        if mid:
            if not _ascii_id(mid):
                raise ToolError("message_id has an unexpected shape.")
            return run(lambda: client.get_json(f"/v1/messages/{mid}"))
        if not validate_idempotency_key(key):
            raise ToolError("idempotency_key must be 1–128 characters from [A-Za-z0-9:_.-].")
        return run(lambda: client.get_json("/v1/messages", params={"idempotency_key": key}))

    @server.tool(
        name="send_message",
        title="Send Bale message (queues through outbox)",
        annotations=_SEND,
        description=(
            "SIDE EFFECT. Queue one outbound message on the shared PlayTalk Bale account "
            "by POSTing /v1/messages. The HTTP API inserts an outbox row; the outbox worker "
            "sends it later, under rate limits, per-recipient caps, quiet hours, the circuit "
            "breaker, and BALE_SEND_MODE (live, dry_run, or resolve_only). This tool does not "
            "talk to Bale itself and does not bypass those controls.\n\n"
            "Confirm the recipient and the exact text with the human before calling. "
            "Do not call this to draft, preview, or test.\n\n"
            "Pass exactly one of phone (Iranian mobile), bale_user_id (digits), or username "
            "(leading @ is stripped by the API). One recipient only; bulk sends are not this tool.\n\n"
            "idempotency_key is required: 1–128 characters from [A-Za-z0-9:_.-], chosen by you "
            "and stable for this send. Reuse that same key when retrying after a network error "
            "so the API returns the existing row instead of queueing another message. A new key "
            "queues another message. The same key with different text or recipient is a conflict.\n\n"
            "mode is send (default) or reply. reply is only for bale_user_id, and only when that "
            "user wrote to support inside the adapter reply window; otherwise the API returns "
            "reply_window_closed. text is 1–4000 characters. Optional ttl_seconds overrides the "
            "adapter default (max 7 days).\n\n"
            "On success the body is the API queue result (message_id, status, idempotency_key). "
            "status queued means waiting on the worker, not already delivered. Check message_status "
            "for the later outcome."
        ),
    )
    def send_message(
        text: str,
        idempotency_key: str,
        phone: str = "",
        bale_user_id: str = "",
        username: str = "",
        mode: str = "send",
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        body = _send_body(
            text=text,
            idempotency_key=idempotency_key,
            phone=phone,
            bale_user_id=bale_user_id,
            username=username,
            mode=mode,
            ttl_seconds=ttl_seconds,
        )
        return run(lambda: client.post_json("/v1/messages", body))

    return server


def _send_body(
    *,
    text: str,
    idempotency_key: str,
    phone: str,
    bale_user_id: str,
    username: str,
    mode: str,
    ttl_seconds: int | None,
) -> dict[str, Any]:
    message = text if isinstance(text, str) else ""
    if not message.strip():
        raise ToolError("text is required.")
    if len(message) > _TEXT_MAX:
        raise ToolError("text exceeds 4000 characters.")
    key = idempotency_key.strip() if isinstance(idempotency_key, str) else ""
    if not validate_idempotency_key(key):
        raise ToolError(
            "idempotency_key is required: 1–128 characters from [A-Za-z0-9:_.-]. "
            "Reuse the same key when retrying this exact send."
        )
    send_mode = (mode or "send").strip()
    if send_mode not in {"send", "reply"}:
        raise ToolError("mode must be send or reply.")
    recipient = _one_recipient(phone, bale_user_id, username)
    if send_mode == "reply" and "bale_user_id" not in recipient:
        raise ToolError("reply mode needs bale_user_id (a phone or username cannot be a reply).")
    body: dict[str, Any] = {
        "recipient": recipient,
        "text": message,
        "idempotency_key": key,
        "mode": send_mode,
    }
    if ttl_seconds is not None:
        try:
            ttl = int(ttl_seconds)
        except (TypeError, ValueError) as exc:
            raise ToolError("ttl_seconds must be an integer.") from exc
        if ttl < 1 or ttl > 604800:
            raise ToolError("ttl_seconds must be between 1 and 604800 (7 days).")
        body["ttl_seconds"] = ttl
    return body


def _one_recipient(phone: str, bale_user_id: str, username: str) -> dict[str, str]:
    fields = {
        "phone": _blank(phone),
        "bale_user_id": _blank(bale_user_id),
        "username": _blank(username),
    }
    chosen = {name: value for name, value in fields.items() if value}
    if len(chosen) != 1:
        raise ToolError("Pass exactly one of phone, bale_user_id, or username.")
    name, value = next(iter(chosen.items()))
    if name == "bale_user_id" and not _ascii_digits(value):
        raise ToolError("bale_user_id must be decimal digits.")
    return {name: value}


def _blank(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _non_negative(value: int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{name} must be an integer.") from exc
    if number < 0:
        raise ToolError(f"{name} must be >= 0.")
    return number


def _clamp(value: int, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _ascii_digits(value: str) -> bool:
    return bool(value) and value.isascii() and value.isdigit()


def _ascii_id(value: str) -> bool:
    return bool(value) and value.isascii() and all(ch.isalnum() or ch in "-_" for ch in value)


def _chat_id(raw: str) -> str:
    chat_id = _blank(raw)
    if not _ascii_digits(chat_id):
        raise ToolError("chat_id must be the numeric Bale peer id.")
    return chat_id
