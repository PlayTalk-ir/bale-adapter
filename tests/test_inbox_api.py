"""Inbox feed, store seq migration and reply mode."""

from __future__ import annotations

import sqlite3
import time

import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from bale_platform.api.server import ApiRuntime
from bale_platform.api_config import ApiSettings
from bale_platform.contact_store import ContactBook
from bale_platform.outbox.rate_limit import RateLimitConfig, SendRateLimiter
from bale_platform.outbox.store import OutboxStore
from bale_platform.store import SupportStore

AUTH = {"Authorization": "Bearer secret-token"}


def _msg(chat_id, message_id, text, *, date_ms=None, kind="text", chat_type=""):
    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "sender_id": chat_id,
        "text": text,
        "kind": kind,
        "chat_type": chat_type,
        "date_ms": date_ms if date_ms is not None else int(time.time() * 1000),
        "timestamp": "",
    }


@pytest_asyncio.fixture
async def inbox_client(tmp_path):
    outbox = OutboxStore(tmp_path / "outbox.sqlite")
    inbox = SupportStore(tmp_path / "inbox.sqlite")
    contacts = ContactBook(tmp_path / "contacts.sqlite")
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
        resume_breaker=outbox.resume_breaker,
        inbox=inbox,
        contacts=contacts,
    )
    client = TestClient(TestServer(runtime.create_app()))
    await client.start_server()
    yield client, inbox, outbox, contacts
    await client.close()


def test_upsert_assigns_seq_once(tmp_path):
    store = SupportStore(tmp_path / "s.sqlite")
    assert store.upsert_message(_msg("10", 1, "salam")) is True
    assert store.upsert_message(_msg("10", 2, "hi")) is True
    assert store.upsert_message(_msg("10", 1, "salam (edited)")) is False
    events = store.events_after(0)
    assert [e.seq for e in events] == [1, 2]
    assert events[0].text == "salam (edited)"
    assert store.events_after(1)[0].message_id == 2


def test_media_without_caption_gets_placeholder(tmp_path):
    store = SupportStore(tmp_path / "s.sqlite")
    store.upsert_message(_msg("10", 1, "", kind="voice"))
    store.upsert_message(_msg("10", 2, "see this", kind="photo"))
    store.upsert_message(_msg("10", 3, "", kind="service"))
    events = store.events_after(0)
    assert [(e.kind, e.text) for e in events] == [
        ("voice", "[پیام صوتی]"),
        ("photo", "[عکس] see this"),
    ]


def test_migration_backfills_seq(tmp_path):
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE messages (
            chat_id TEXT NOT NULL, message_id INTEGER NOT NULL, sender_id TEXT NOT NULL,
            text TEXT NOT NULL, timestamp TEXT NOT NULL, date_ms INTEGER NOT NULL,
            direction TEXT NOT NULL DEFAULT 'in', PRIMARY KEY (chat_id, message_id)
        );
        INSERT INTO messages VALUES ('5', 2, '5', 'second', '', 200, 'in');
        INSERT INTO messages VALUES ('5', 1, '5', 'first', '', 100, 'in');
        """
    )
    conn.commit()
    conn.close()
    store = SupportStore(path)
    events = store.events_after(0)
    assert [(e.seq, e.text) for e in events] == [(1, "first"), (2, "second")]
    store.upsert_message(_msg("5", 3, "third"))
    assert store.events_after(2)[0].seq == 3


async def test_events_use_contact_book_display_name(inbox_client):
    from bale_platform.contacts import SavedContact

    client, inbox, _, contacts = inbox_client
    contacts.upsert_bale(
        SavedContact(99, "99", local_name="نفس پیروز", source="contacts")
    )
    inbox.upsert_message(_msg("99", 1, "salam"))
    r = await client.get("/v1/inbox/events?after=0", headers=AUTH)
    body = await r.json()
    assert body["events"][0]["chat"]["name"] == "نفس پیروز"


async def test_get_contacts_lists_book_with_phone(inbox_client):
    client, inbox, outbox, contacts = inbox_client
    contacts.set_phone_digits(77, "989121234567")
    contacts.upsert_bale(
        __import__("bale_platform.contacts", fromlist=["SavedContact"]).SavedContact(
            77, "Sara", source="dialog", local_name="Sara"
        )
    )
    r = await client.get("/v1/contacts", headers=AUTH)
    body = await r.json()
    assert r.status == 200
    row = next(c for c in body["contacts"] if c["chat_id"] == "77")
    assert row["phone"] == "09121234567"
    assert row["name"] == "Sara"


async def test_events_include_outreach_phone_on_chat(inbox_client):
    client, inbox, outbox, _ = inbox_client
    outbox.set_inbox_chat_phone(42, "989121234567")
    inbox.upsert_message(_msg("42", 1, "salam"))
    r = await client.get("/v1/inbox/events?after=0", headers=AUTH)
    body = await r.json()
    assert body["events"][0]["chat"]["phone"] == "09121234567"


async def test_events_feed_with_cursor_and_labels(inbox_client):
    client, inbox, _, _ = inbox_client
    inbox.upsert_message(_msg("42", 1, "salam"))
    inbox.upsert_message(_msg("-77", 1, "group noise", chat_type="ChatType.GROUP"))
    inbox.upsert_message(_msg("42", 2, "kelas kei?"))
    inbox.set_label("42", "Sara Ahmadi")

    r = await client.get("/v1/inbox/events?after=0", headers=AUTH)
    assert r.status == 200
    body = await r.json()
    assert [e["text"] for e in body["events"]] == ["salam", "kelas kei?"]
    assert body["events"][0]["chat"]["name"] == "Sara Ahmadi"
    assert body["next_after"] == 3
    assert body["has_more"] is False

    r2 = await client.get(f"/v1/inbox/events?after={body['next_after']}", headers=AUTH)
    assert (await r2.json())["events"] == []


async def test_events_requires_auth(inbox_client):
    client, *_ = inbox_client
    r = await client.get("/v1/inbox/events")
    assert r.status == 401


async def test_history_oldest_first(inbox_client):
    client, inbox, *_ = inbox_client
    inbox.upsert_message(_msg("42", 1, "a", date_ms=1000))
    inbox.upsert_message(_msg("42", 2, "b", date_ms=2000))
    r = await client.get("/v1/inbox/chats/42/history", headers=AUTH)
    assert [e["text"] for e in (await r.json())["events"]] == ["a", "b"]


async def test_reply_needs_recent_inbound(inbox_client):
    client, inbox, outbox, _ = inbox_client
    payload = {
        "recipient": {"bale_user_id": "42"},
        "text": "salam, khoob hastid?",
        "idempotency_key": "inbox:r1",
        "mode": "reply",
    }
    r = await client.post("/v1/messages", headers=AUTH, json=payload)
    assert r.status == 422
    assert (await r.json())["error"]["code"] == "reply_window_closed"

    inbox.upsert_message(_msg("42", 1, "salam"))
    r = await client.post("/v1/messages", headers=AUTH, json=payload)
    assert r.status == 202
    row = outbox.get_by_message_id((await r.json())["message_id"])
    assert row["mode"] == "reply"


async def test_reply_mode_rejects_phone_recipient(inbox_client):
    client, *_ = inbox_client
    r = await client.post(
        "/v1/messages",
        headers=AUTH,
        json={
            "recipient": {"phone": "09924466793"},
            "text": "x",
            "idempotency_key": "inbox:r2",
            "mode": "reply",
        },
    )
    assert r.status == 422


def test_reply_pacing_is_relaxed(tmp_path):
    store = OutboxStore(tmp_path / "o.sqlite")
    now = [1_000_000.0]
    limiter = SendRateLimiter(
        store,
        RateLimitConfig(send_jitter_s=0, reply_jitter_s=0),
        lambda: now[0],
    )
    limiter.record_send(42)
    now[0] += 5
    assert limiter.defer_seconds(42) > 0
    assert limiter.defer_seconds(42, reply=True) == 0
