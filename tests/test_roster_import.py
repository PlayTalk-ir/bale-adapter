"""POST /v1/contacts/import-roster"""

from __future__ import annotations

import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from bale_platform.api.server import ApiRuntime
from bale_platform.api_config import ApiSettings
from bale_platform.contact_store import ContactBook
from bale_platform.outbox.store import OutboxStore
from bale_platform.resolver import RecipientResolver
from tests.fake_bale import FakeBaleClient

AUTH = {"Authorization": "Bearer secret-token"}


@pytest_asyncio.fixture
async def roster_client(tmp_path):
    outbox = OutboxStore(tmp_path / "outbox.sqlite")
    contacts = ContactBook(tmp_path / "contacts.sqlite")
    client = FakeBaleClient()
    client.contacts["989121234567"] = 555
    resolver = RecipientResolver(
        client,
        outbox,
        phone_pepper="test",
        new_peer_max_per_day=50,
        lookup_min_interval_s=0,
    )
    settings = ApiSettings(
        enabled=True,
        tokens=["secret-token"],
        outbox_path=tmp_path / "outbox.sqlite",
        send_mode="dry_run",
    )
    runtime = ApiRuntime(
        settings,
        outbox,
        session_connected=lambda: True,
        session_reason=lambda: "connected",
        sending_paused=lambda: False,
        resume_breaker=lambda: None,
        contacts=contacts,
        get_resolver=lambda: resolver,
    )
    app = runtime.create_app()
    async with TestClient(TestServer(app)) as http:
        yield http, contacts, outbox


async def test_import_roster_matches_and_caches(roster_client):
    http, contacts, outbox = roster_client
    r = await http.post(
        "/v1/contacts/import-roster",
        headers=AUTH,
        json={"contacts": [{"phone": "09121234567", "name": "Sara Test"}]},
    )
    assert r.status == 200
    body = await r.json()
    assert body["stats"]["matched"] == 1
    assert body["results"][0]["chat_id"] == "555"
    assert outbox.get_inbox_chat_phone(555) == "989121234567"
    entry = contacts.get(555)
    assert entry is not None
    assert entry.phone_digits == "989121234567"
    assert entry.name == "Sara Test"
