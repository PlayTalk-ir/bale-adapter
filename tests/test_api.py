"""HTTP API contract tests."""

from __future__ import annotations

import asyncio
import json
import os
import time

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from bale_platform import panel_auth

from bale_platform.api.server import ApiRuntime
from bale_platform.api_config import ApiSettings
from bale_platform.outbox.store import OutboxStore


def _settings(tmp_path, **overrides):
    base = ApiSettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        tokens=["secret-token"],
        outbox_path=tmp_path / "outbox.sqlite",
        phone_pepper="test-pepper",
        send_mode="dry_run",
        docs_user="docs-user",
        docs_password="docs-operator-password",
        docs_token="test-panel-signing-token-minlen",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


@pytest_asyncio.fixture
async def api_client(tmp_path):
    store = OutboxStore(tmp_path / "outbox.sqlite")
    settings = _settings(tmp_path)
    runtime = ApiRuntime(
        settings,
        store,
        session_connected=lambda: True,
        session_reason=lambda: "connected",
        sending_paused=lambda: False,
        resume_breaker=lambda: store.resume_breaker(),
    )
    app = runtime.create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client, store, settings
    await client.close()


def auth_headers(token: str = "secret-token"):
    return {"Authorization": f"Bearer {token}"}


def docs_cookie_headers(token: str = "test-panel-signing-token-minlen"):
    session = panel_auth.make_session(token)
    return {"Cookie": f"{panel_auth.SESSION_COOKIE}={session}"}


@pytest.mark.asyncio
async def test_swagger_docs_shows_password_login(api_client):
    client, _, _ = api_client
    resp = await client.get("/v1/docs")
    assert resp.status == 401
    text = await resp.text()
    assert 'name="password"' in text
    assert "WWW-Authenticate" not in resp.headers


@pytest.mark.asyncio
async def test_swagger_docs_login_and_cookie(api_client):
    client, _, _ = api_client
    resp = await client.post(
        "/v1/docs/login",
        data={"password": "docs-operator-password"},
        allow_redirects=False,
    )
    assert resp.status == 302
    assert resp.headers["Location"] == "/v1/docs"
    assert panel_auth.SESSION_COOKIE in resp.cookies
    resp2 = await client.get("/v1/docs", cookies=resp.cookies)
    assert resp2.status == 200
    assert "swagger-ui" in (await resp2.text()).lower()


@pytest.mark.asyncio
async def test_swagger_docs_ok_with_panel_session(api_client):
    client, _, _ = api_client
    resp = await client.get("/v1/docs", headers=docs_cookie_headers())
    assert resp.status == 200
    assert "swagger-ui" in (await resp.text()).lower()


@pytest.mark.asyncio
async def test_openapi_json(api_client):
    client, _, _ = api_client
    resp = await client.get("/v1/openapi.json", headers=docs_cookie_headers())
    assert resp.status == 200
    body = await resp.json()
    assert body["openapi"].startswith("3.")
    assert "/v1/messages" in body["paths"]


@pytest.mark.asyncio
async def test_healthz_no_auth(api_client):
    client, _, _ = api_client
    resp = await client.get("/healthz")
    assert resp.status == 200
    assert "X-Request-Id" in resp.headers


@pytest.mark.asyncio
async def test_unauthorized(api_client):
    client, _, _ = api_client
    resp = await client.post("/v1/messages", json={})
    assert resp.status == 401
    body = await resp.json()
    assert body["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_recipient_invalid_422(api_client):
    client, _, _ = api_client
    resp = await client.post(
        "/v1/messages",
        headers=auth_headers(),
        json={
            "recipient": {"phone": "123"},
            "text": "hi",
            "idempotency_key": "k1",
        },
    )
    assert resp.status == 422


@pytest.mark.asyncio
async def test_two_recipient_fields_422(api_client):
    client, _, _ = api_client
    resp = await client.post(
        "/v1/messages",
        headers=auth_headers(),
        json={
            "recipient": {"phone": "09924466793", "username": "x"},
            "text": "hi",
            "idempotency_key": "k2",
        },
    )
    assert resp.status == 422


@pytest.mark.asyncio
async def test_text_too_long_413(api_client):
    client, _, _ = api_client
    resp = await client.post(
        "/v1/messages",
        headers=auth_headers(),
        json={
            "recipient": {"bale_user_id": "42"},
            "text": "x" * 4001,
            "idempotency_key": "k3",
        },
    )
    assert resp.status == 413
    assert (await resp.json())["error"]["code"] == "text_too_long"


@pytest.mark.asyncio
async def test_accept_202_then_200_idempotent(api_client):
    client, _, _ = api_client
    payload = {
        "recipient": {"bale_user_id": "42"},
        "text": "hello",
        "idempotency_key": "rule_bale:12:34",
    }
    r1 = await client.post("/v1/messages", headers=auth_headers(), json=payload)
    assert r1.status == 202
    b1 = await r1.json()
    assert b1["status"] == "queued"
    r2 = await client.post("/v1/messages", headers=auth_headers(), json=payload)
    assert r2.status == 200
    b2 = await r2.json()
    assert b2["message_id"] == b1["message_id"]


@pytest.mark.asyncio
async def test_idempotency_conflict_409(api_client):
    client, _, _ = api_client
    key = "rule_bale:99:1"
    await client.post(
        "/v1/messages",
        headers=auth_headers(),
        json={"recipient": {"bale_user_id": "1"}, "text": "a", "idempotency_key": key},
    )
    resp = await client.post(
        "/v1/messages",
        headers=auth_headers(),
        json={"recipient": {"bale_user_id": "1"}, "text": "b", "idempotency_key": key},
    )
    assert resp.status == 409


@pytest.mark.asyncio
async def test_rate_limit_429(tmp_path):
    store = OutboxStore(tmp_path / "o.sqlite")
    settings = _settings(tmp_path, rate_per_min=1, queue_max=500)
    runtime = ApiRuntime(
        settings,
        store,
        session_connected=lambda: True,
        session_reason=lambda: "connected",
        sending_paused=lambda: False,
        resume_breaker=store.resume_breaker,
    )
    app = runtime.create_app()
    async with TestClient(TestServer(app)) as client:
        await client.start_server()
        payload = {
            "recipient": {"bale_user_id": "5"},
            "text": "x",
            "idempotency_key": "a",
        }
        assert (await client.post("/v1/messages", headers=auth_headers(), json=payload)).status == 202
        payload["idempotency_key"] = "b"
        r = await client.post("/v1/messages", headers=auth_headers(), json=payload)
        assert r.status == 429
        assert r.headers.get("Retry-After")


@pytest.mark.asyncio
async def test_sending_paused_503(tmp_path):
    store = OutboxStore(tmp_path / "o2.sqlite")
    settings = _settings(tmp_path)
    runtime = ApiRuntime(
        settings,
        store,
        session_connected=lambda: True,
        session_reason=lambda: "connected",
        sending_paused=lambda: True,
        resume_breaker=store.resume_breaker,
    )
    app = runtime.create_app()
    async with TestClient(TestServer(app)) as client:
        await client.start_server()
        r = await client.post(
            "/v1/messages",
            headers=auth_headers(),
            json={
                "recipient": {"bale_user_id": "1"},
                "text": "t",
                "idempotency_key": "p1",
            },
        )
        assert r.status == 503
        assert (await r.json())["error"]["code"] == "sending_paused"


@pytest.mark.asyncio
async def test_get_by_id_and_key(api_client):
    client, store, _ = api_client
    payload = {
        "recipient": {"phone": "09924466793"},
        "text": "salam",
        "idempotency_key": "lookup-key",
    }
    r = await client.post("/v1/messages", headers=auth_headers(), json=payload)
    mid = (await r.json())["message_id"]
    g1 = await client.get(f"/v1/messages/{mid}", headers=auth_headers())
    assert g1.status == 200
    body = await g1.json()
    assert body["idempotency_key"] == "lookup-key"
    g2 = await client.get("/v1/messages?idempotency_key=lookup-key", headers=auth_headers())
    assert (await g2.json())["message_id"] == mid


@pytest.mark.asyncio
async def test_readyz(api_client):
    client, _, _ = api_client
    r = await client.get("/readyz", headers=auth_headers())
    assert r.status == 200
    data = await r.json()
    assert "queue_depth" in data
