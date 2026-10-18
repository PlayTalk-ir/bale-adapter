"""MCP server tests. The adapter HTTP API is mocked; no session file is opened."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from bale_platform.mcp_server.cli import main, resolve_run
from bale_platform.mcp_server.client import AdapterApiClient, AdapterApiError
from bale_platform.mcp_server.config import McpConfigError, load_settings
from bale_platform.mcp_server.search import filter_contacts
from bale_platform.mcp_server.server import INSTRUCTIONS, build_server
from mcp.server.mcpserver.exceptions import ToolError

TOKEN = "test-token-not-a-secret"


def _client(handler) -> AdapterApiClient:
    return AdapterApiClient(
        "http://adapter.test",
        TOKEN,
        transport=httpx.MockTransport(handler),
    )


def _server(handler):
    return build_server(_client(handler))


def _fn(server, name: str):
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, name
    return tool.fn


def test_mcp_package_does_not_touch_the_session_or_stores():
    root = Path(__file__).resolve().parents[1] / "bale_platform" / "mcp_server"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for banned in (
        "aiobale",
        "session.bale",
        ".session",
        "SupportStore",
        "OutboxStore",
        "BaleUserbotAdapter",
    ):
        assert banned not in text


def test_settings_require_token_and_default_loopback():
    with pytest.raises(McpConfigError, match="BALE_MCP_API_TOKEN"):
        load_settings({})
    settings = load_settings({"BALE_MCP_API_TOKEN": "one-token"})
    assert settings.api_base_url == "http://127.0.0.1:8787"
    assert settings.http_host == "127.0.0.1"
    assert settings.http_port == 8790
    assert settings.allow_remote_bind is False


def test_settings_reject_token_in_url_and_whitespace():
    with pytest.raises(McpConfigError, match="BALE_MCP_API_TOKEN"):
        load_settings(
            {
                "BALE_MCP_API_TOKEN": "abc",
                "BALE_MCP_API_BASE_URL": "http://user:secret@127.0.0.1:8787",
            }
        )
    with pytest.raises(McpConfigError, match="whitespace"):
        load_settings({"BALE_MCP_API_TOKEN": "a b"})


def test_http_transport_defaults_and_refuses_public_bind():
    settings, transport = resolve_run(["http"], {"BALE_MCP_API_TOKEN": "t"})
    assert transport == "http"
    assert settings.http_host == "127.0.0.1"
    assert settings.http_port == 8790
    with pytest.raises(McpConfigError, match="Refusing"):
        resolve_run(["http", "--host", "0.0.0.0"], {"BALE_MCP_API_TOKEN": "t"})
    allowed, _ = resolve_run(
        ["http", "--host", "0.0.0.0"],
        {"BALE_MCP_API_TOKEN": "t", "BALE_MCP_HTTP_ALLOW_REMOTE": "true"},
    )
    assert allowed.http_host == "0.0.0.0"


def test_stdio_is_the_default_transport():
    _settings, transport = resolve_run([], {"BALE_MCP_API_TOKEN": "t"})
    assert transport == "stdio"


def test_main_exits_on_missing_token_without_binding(monkeypatch, capsys):
    monkeypatch.delenv("BALE_MCP_API_TOKEN", raising=False)
    assert main(["http"]) == 2
    assert "BALE_MCP_API_TOKEN" in capsys.readouterr().err


def test_main_refuses_public_bind_without_listening(monkeypatch, capsys):
    monkeypatch.setenv("BALE_MCP_API_TOKEN", "t")
    monkeypatch.delenv("BALE_MCP_HTTP_ALLOW_REMOTE", raising=False)
    assert main(["http", "--host", "0.0.0.0"]) == 2
    assert "Refusing" in capsys.readouterr().err


def test_client_sends_bearer_token_and_hides_it_from_logs(caplog):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(
            401,
            json={
                "error": {
                    "code": "unauthorized",
                    "message": "missing or invalid token",
                    "details": {},
                }
            },
        )

    client = _client(handler)
    body_text = "customer body must not be logged"
    with caplog.at_level(logging.DEBUG, logger="bale.mcp"):
        with pytest.raises(AdapterApiError, match="unauthorized") as caught:
            client.post_json("/v1/messages", {"text": body_text, "idempotency_key": "k"})
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert TOKEN not in seen["url"]
    assert TOKEN not in caplog.text
    assert body_text not in caplog.text
    assert "unauthorized" in str(caught.value)
    client.close()


def test_client_reports_retry_after_without_response_body_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"Retry-After": "60"},
            json={
                "error": {
                    "code": "sending_paused",
                    "message": "sending is paused",
                    "details": {},
                }
            },
        )

    err = AdapterApiError.from_response(handler(httpx.Request("POST", "http://adapter.test/v1/messages")))
    assert err.code == "sending_paused"
    assert err.retry_after == "60"
    assert "retry_after=60" in str(err)


def test_list_inbox_and_read_chat_pass_through_api_json():
    event = {
        "seq": 4,
        "chat_id": "100",
        "message_id": 9,
        "direction": "in",
        "kind": "text",
        "text": "hello from the fixture",
        "date_ms": 1,
        "sender_id": "100",
        "chat": {"name": "Ada Example", "username": "", "phone": None},
    }
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, dict(request.url.params)))
        if request.url.path == "/v1/inbox/events":
            return httpx.Response(
                200,
                json={"events": [event], "next_after": 4, "has_more": False},
            )
        return httpx.Response(200, json={"events": [event]})

    server = _server(handler)
    listed = _fn(server, "list_inbox")(after=3, limit=10)
    assert listed["events"] == [event]
    assert listed["next_after"] == 4
    assert calls[0] == ("/v1/inbox/events", {"after": "3", "limit": "10"})
    history = _fn(server, "read_chat")(chat_id="100", limit=5)
    assert history == {"events": [event]}
    assert calls[1] == ("/v1/inbox/chats/100/history", {"limit": "5"})


def test_read_chat_rejects_non_numeric_id_without_calling_api():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("API should not be called")

    server = _server(handler)
    with pytest.raises(ToolError, match="chat_id"):
        _fn(server, "read_chat")(chat_id="../secrets")


def test_search_contacts_filters_api_rows_and_keeps_phones():
    rows = [
        {
            "chat_id": "1",
            "name": "Ada Example",
            "username": None,
            "phone": "09120000000",
            "source": "manual",
            "manual": True,
        },
        {
            "chat_id": "2",
            "name": "Bea Example",
            "username": "bea",
            "phone": None,
            "source": "dialog",
            "manual": False,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/contacts"
        return httpx.Response(200, json={"contacts": rows})

    server = _server(handler)
    found = _fn(server, "search_contacts")(query="ada", limit=10)
    assert found["count"] == 1
    assert found["contacts"] == [rows[0]]
    assert found["contacts"][0]["phone"] == "09120000000"
    everyone = _fn(server, "search_contacts")(query="", limit=1)
    assert everyone["count"] == 1
    assert everyone["contacts"] == [rows[0]]


def test_filter_contacts_folds_spacing():
    rows = [{"chat_id": "9", "name": "Ada  Example", "username": "", "phone": None}]
    assert filter_contacts(rows, "ada example") == rows


def test_message_status_returns_masked_recipient():
    payload = {
        "message_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "idempotency_key": "mcp:1",
        "status": "queued",
        "attempts": 0,
        "recipient": {"type": "phone", "masked": "98912***0000"},
        "bale_user_id": None,
        "bale_message_id": None,
        "error": None,
        "dry_run": False,
        "created_at": "2026-10-18T00:00:00+00:00",
        "sent_at": None,
        "updated_at": "2026-10-18T00:00:00+00:00",
    }
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, request.url.params.get("idempotency_key")))
        return httpx.Response(200, json=payload)

    server = _server(handler)
    by_id = _fn(server, "message_status")(message_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert by_id == payload
    assert by_id["recipient"]["masked"] == "98912***0000"
    by_key = _fn(server, "message_status")(idempotency_key="mcp:1")
    assert by_key == payload
    assert calls == [
        ("/v1/messages/01ARZ3NDEKTSV4RRFFQ69G5FAV", None),
        ("/v1/messages", "mcp:1"),
    ]
    with pytest.raises(ToolError, match="exactly one"):
        _fn(server, "message_status")(message_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", idempotency_key="mcp:1")


def test_send_message_posts_single_recipient_and_returns_api_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(
            202,
            json={"message_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "status": "queued", "idempotency_key": "mcp:1"},
        )

    server = _server(handler)
    result = _fn(server, "send_message")(
        text="سلام",
        idempotency_key="mcp:1",
        phone="09120000000",
    )
    assert result == {
        "message_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "status": "queued",
        "idempotency_key": "mcp:1",
    }
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert seen["body"] == {
        "recipient": {"phone": "09120000000"},
        "text": "سلام",
        "idempotency_key": "mcp:1",
        "mode": "send",
    }


def test_send_message_reply_mode_uses_user_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(
            202,
            json={"message_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "status": "queued", "idempotency_key": "mcp:reply"},
        )

    server = _server(handler)
    _fn(server, "send_message")(
        text="answer",
        idempotency_key="mcp:reply",
        bale_user_id="42",
        mode="reply",
        ttl_seconds=3600,
    )
    assert seen["body"]["recipient"] == {"bale_user_id": "42"}
    assert seen["body"]["mode"] == "reply"
    assert seen["body"]["ttl_seconds"] == 3600


def test_send_message_does_not_call_api_for_local_rejections():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("API should not be called")

    server = _server(handler)
    send = _fn(server, "send_message")
    with pytest.raises(ToolError, match="exactly one"):
        send(text="hi", idempotency_key="mcp:1", phone="09120000000", username="ada")
    with pytest.raises(ToolError, match="idempotency_key"):
        send(text="hi", idempotency_key="", phone="09120000000")
    with pytest.raises(ToolError, match="reply mode"):
        send(text="hi", idempotency_key="mcp:1", phone="09120000000", mode="reply")
    with pytest.raises(ToolError, match="4000"):
        send(text="x" * 4001, idempotency_key="mcp:1", bale_user_id="1")


def test_send_message_surfaces_api_conflict_and_pause():
    def conflict(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "idempotency_conflict",
                    "message": "idempotency key reused with different payload",
                    "details": {},
                }
            },
        )

    server = _server(conflict)
    with pytest.raises(ToolError, match="idempotency_conflict"):
        _fn(server, "send_message")(text="hi", idempotency_key="mcp:1", username="ada")

    def paused(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"Retry-After": "60"},
            json={"error": {"code": "sending_paused", "message": "sending is paused", "details": {}}},
        )

    server = _server(paused)
    with pytest.raises(ToolError, match="retry_after=60"):
        _fn(server, "send_message")(text="hi", idempotency_key="mcp:1", bale_user_id="7")


def test_client_does_not_follow_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "adapter.test"
        return httpx.Response(302, headers={"Location": "http://evil.example/collect"})

    client = _client(handler)
    with pytest.raises(AdapterApiError) as caught:
        client.post_json("/v1/messages", {"text": "secret body"})
    assert "evil.example" not in str(caught.value)
    assert TOKEN not in str(caught.value)
    client.close()


def test_unread_ack_facts_and_faq_call_the_api():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params), request.content))
        if request.url.path == "/v1/inbox/unread":
            return httpx.Response(200, json={"agent": "sara", "events": [], "count": 0, "truncated": False})
        if request.url.path == "/v1/inbox/ack":
            return httpx.Response(
                200,
                json={
                    "agent": "sara",
                    "chat_id": "42",
                    "message_id": 9,
                    "requested_message_id": 9,
                    "acked_at": "2026-10-18T00:00:00+00:00",
                    "unchanged": True,
                },
            )
        if request.url.path == "/v1/kb/facts":
            return httpx.Response(
                200,
                json={"facts": [{"items": [{"category": "phone", "value": "98912***0000"}]}], "count": 1},
            )
        if request.url.path == "/v1/analysis/faq":
            return httpx.Response(
                200,
                json={"source": "inbox_store", "live_bale": False, "categories": [], "faq_topic_hints": []},
            )
        raise AssertionError(request.url.path)

    server = _server(handler)
    assert _fn(server, "list_unread")(agent="sara", limit=10)["count"] == 0
    acked = _fn(server, "ack_chat")(agent="sara", chat_id="42", message_id=9)
    assert acked["unchanged"] is True
    facts = _fn(server, "kb_facts")(query="phone", limit=5)
    assert facts["facts"][0]["items"][0]["value"] == "98912***0000"
    faq = _fn(server, "faq_topics")(limit=20, since_ms=0)
    assert faq["live_bale"] is False
    assert seen[0][0:3] == ("GET", "/v1/inbox/unread", {"agent": "sara", "limit": "10"})
    assert seen[1][0:2] == ("POST", "/v1/inbox/ack")
    assert json.loads(seen[1][3]) == {"agent": "sara", "chat_id": "42", "message_id": 9}
    assert seen[2][0:3] == ("GET", "/v1/kb/facts", {"limit": "5", "q": "phone"})
    assert seen[3][0:3] == ("GET", "/v1/analysis/faq", {"limit": "20", "since_ms": "0"})

    with pytest.raises(ToolError, match="agent"):
        _fn(server, "ack_chat")(agent=" ", chat_id="42", message_id=1)


def test_unreachable_adapter_is_a_tool_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    server = _server(handler)
    with pytest.raises(ToolError, match="unreachable") as caught:
        _fn(server, "adapter_health")()
    assert TOKEN not in str(caught.value)


@pytest.mark.asyncio
async def test_tool_annotations_mark_send_as_side_effect():
    server = _server(lambda _request: httpx.Response(200, json={"ok": True}))
    tools = {tool.name: tool for tool in await server.list_tools()}
    expected = {
        "adapter_health",
        "adapter_ready",
        "session_status",
        "list_inbox",
        "read_chat",
        "list_unread",
        "ack_chat",
        "kb_facts",
        "faq_topics",
        "search_contacts",
        "message_status",
        "send_message",
    }
    assert set(tools) == expected
    send = tools["send_message"]
    assert send.annotations is not None
    assert send.annotations.read_only_hint is False
    assert send.annotations.destructive_hint is True
    assert send.annotations.idempotent_hint is False
    assert send.annotations.open_world_hint is True
    wire = send.annotations.model_dump(by_alias=True, exclude_none=True)
    assert wire["readOnlyHint"] is False
    assert wire["destructiveHint"] is True
    assert wire["idempotentHint"] is False
    description = (send.description or "").lower()
    assert "outbox" in description
    assert "confirm" in description
    assert "side effect" in description
    ack = tools["ack_chat"]
    assert ack.annotations is not None
    ack_wire = ack.annotations.model_dump(by_alias=True, exclude_none=True)
    assert ack_wire["readOnlyHint"] is False
    assert ack_wire["destructiveHint"] is False
    assert ack_wire["idempotentHint"] is True
    assert "idempotent" in (ack.description or "").lower()
    for name in expected - {"send_message", "ack_chat"}:
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
    assert "OTP" in INSTRUCTIONS
    assert "list_unread" in INSTRUCTIONS
    assert "ack_chat" in INSTRUCTIONS
    assert server._lowlevel_server.instructions == INSTRUCTIONS


@pytest.mark.asyncio
async def test_call_tool_returns_api_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(200, json={"ok": True})

    server = _server(handler)
    result = await server.call_tool("adapter_health", {})
    assert result.is_error is False
    assert json.loads(result.content[0].text) == {"ok": True}
