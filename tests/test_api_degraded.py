"""API and worker behaviour without a Bale session."""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from aiohttp import ClientSession

from bale_platform.adapter import BaleUserbotAdapter
from bale_platform.api_config import ApiSettings
from bale_platform.config import BaleUserbotConfig
from bale_platform.outbox.store import OutboxStore
from bale_platform.outbox.worker import OutboxWorker
from bale_platform.sender import LiveBaleSender
from tests.fake_bale import FakeBaleClient


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BALE_API_ENABLED", "true")
    monkeypatch.setenv("BALE_ADAPTER_API_TOKENS", "test-token")
    monkeypatch.setenv("BALE_API_HOST", "127.0.0.1")
    monkeypatch.setenv("BALE_API_PORT", "18787")
    monkeypatch.setenv("BALE_SESSION_PATH", str(tmp_path / "nope/session.bale"))
    monkeypatch.setenv("BALE_OUTBOX_PATH", str(tmp_path / "outbox.sqlite"))
    monkeypatch.setenv("BALE_STORE_PATH", str(tmp_path / "inbox.sqlite"))
    monkeypatch.setenv("BALE_KB_DIR", str(tmp_path / "kb"))
    monkeypatch.setenv("BALE_LOG_FILE", str(tmp_path / "logs/userbot.log"))
    monkeypatch.setenv("BALE_SEND_MODE", "dry_run")
    monkeypatch.setenv("BALE_SENDING_PAUSED", "false")
    monkeypatch.setenv("BALE_PHONE_PEPPER", "pepper")


@pytest.mark.asyncio
async def test_api_up_without_session_healthz_and_readyz(api_env):
    cfg = BaleUserbotConfig.from_env()
    adapter = BaleUserbotAdapter(cfg)
    stop = asyncio.Event()
    runner = asyncio.create_task(adapter.start(stop))
    try:
        await asyncio.sleep(0.3)
        async with ClientSession() as session:
            async with session.get("http://127.0.0.1:18787/healthz") as resp:
                assert resp.status == 200
            async with session.get(
                "http://127.0.0.1:18787/readyz",
                headers={"Authorization": "Bearer test-token"},
            ) as resp:
                assert resp.status == 200
                body = await resp.json()
                assert body["session_connected"] is False
                assert body["session_reason"] == "session_file_missing"
            async with session.post(
                "http://127.0.0.1:18787/v1/messages",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "recipient": {"bale_user_id": "99"},
                    "text": "queued offline",
                    "idempotency_key": "offline:1",
                },
            ) as resp:
                assert resp.status == 202
    finally:
        stop.set()
        await runner
        await adapter.stop()


@pytest.mark.asyncio
async def test_worker_live_waits_while_disconnected(tmp_path):
    clock = type("C", (), {"t": 1_000_000.0, "now": lambda s: s.t})()
    store = OutboxStore(tmp_path / "o.sqlite")
    settings = ApiSettings(
        enabled=True,
        tokens=["t"],
        outbox_path=tmp_path / "o.sqlite",
        send_mode="live",
        phone_pepper="p",
    )
    store.insert_message(
        message_id="live1",
        idempotency_key="k",
        payload_hash="h",
        text="x",
        meta=None,
        recipient_type="bale_user_id",
        recipient_masked="42",
        recipient_secret=json.dumps({"type": "bale_user_id", "bale_user_id": "42"}),
        expires_at=clock.t + 3600,
        now=clock.t,
    )
    client = FakeBaleClient()
    worker = OutboxWorker(
        store,
        settings,
        get_client=lambda: client,
        get_sender=lambda: LiveBaleSender(client),
        get_resolver=lambda: None,
        session_connected=lambda: False,
        sending_paused=lambda: False,
        clock=clock.now,
        sleep=lambda s: asyncio.sleep(0),
    )
    worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()
    row = store.get_by_message_id("live1")
    assert row["status"] == "queued"
    assert client.send_calls == []


@pytest.mark.asyncio
async def test_worker_dry_run_without_session_completes(tmp_path):
    clock = type("C", (), {"t": 1_000_000.0, "now": lambda s: s.t})()
    store = OutboxStore(tmp_path / "o.sqlite")
    settings = ApiSettings(
        enabled=True,
        tokens=["t"],
        outbox_path=tmp_path / "o.sqlite",
        send_mode="dry_run",
        phone_pepper="p",
    )
    store.insert_message(
        message_id="dry1",
        idempotency_key="k2",
        payload_hash="h2",
        text="dry",
        meta=None,
        recipient_type="bale_user_id",
        recipient_masked="7",
        recipient_secret=json.dumps({"type": "bale_user_id", "bale_user_id": "7"}),
        expires_at=clock.t + 3600,
        now=clock.t,
    )
    client = FakeBaleClient()
    from bale_platform.sender import DryRunBaleSender

    worker = OutboxWorker(
        store,
        settings,
        get_client=lambda: None,
        get_sender=lambda: DryRunBaleSender(),
        get_resolver=lambda: None,
        session_connected=lambda: False,
        sending_paused=lambda: False,
        clock=clock.now,
        sleep=lambda s: asyncio.sleep(0),
    )
    worker.start()
    for _ in range(30):
        row = store.get_by_message_id("dry1")
        if row and row["status"] == "sent":
            break
        await asyncio.sleep(0.02)
    await worker.stop()
    assert store.get_by_message_id("dry1")["status"] == "sent"
    assert store.get_by_message_id("dry1")["dry_run"] == 1
    assert client.send_calls == []
