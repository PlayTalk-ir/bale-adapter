"""Ensure logs do not contain message text or full phones."""

from __future__ import annotations

import logging

import pytest

from bale_platform.outbox.worker import OutboxWorker
from bale_platform.api_config import ApiSettings
from bale_platform.outbox.store import OutboxStore
from bale_platform.resolver import RecipientResolver
from bale_platform.sender import DryRunBaleSender
from tests.fake_bale import FakeBaleClient
import asyncio
import json


@pytest.mark.asyncio
async def test_worker_logs_no_plaintext(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="bale.outbox.worker")
    store = OutboxStore(tmp_path / "o.sqlite")
    client = FakeBaleClient()
    settings = ApiSettings(enabled=True, tokens=["t"], outbox_path=tmp_path / "o.sqlite", send_mode="dry_run", phone_pepper="p")
    secret = json.dumps({"type": "phone", "phone": "989924466793"})
    store.insert_message(
        message_id="log1",
        idempotency_key="lk",
        payload_hash="h",
        text="super secret message body",
        meta=None,
        recipient_type="phone",
        recipient_masked="98912***6793",
        recipient_secret=secret,
        expires_at=1_000_000_000,
        now=1_000_000.0,
    )
    worker = OutboxWorker(
        store,
        settings,
        get_client=lambda: client,
        get_sender=lambda: DryRunBaleSender(),
        get_resolver=lambda: RecipientResolver(client, store, phone_pepper="p"),
        session_connected=lambda: True,
        sending_paused=lambda: False,
        sleep=lambda s: asyncio.sleep(0),
    )
    worker.start()
    await asyncio.sleep(0.1)
    await worker.stop()
    combined = caplog.text
    assert "super secret message body" not in combined
    assert "989924466793" not in combined
