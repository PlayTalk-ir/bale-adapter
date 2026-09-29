"""Tests for outbound target classification, name resolution and dry-run sends."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform import outbound as outbound_mod
from bale_platform.contacts import ContactIndex, SavedContact
from bale_platform.outbound import (
    TARGET_CHAT_ID,
    TARGET_NAME,
    TARGET_PHONE,
    classify_target,
    resolve_target,
    send_to_targets,
)
from bale_platform.store import SupportStore


class TestClassifyTarget:
    def test_numeric_chat_id(self):
        assert classify_target("1858791866") == TARGET_CHAT_ID

    def test_local_phone_is_not_a_chat_id(self):
        # Regression: 11-digit 09… used to be treated as a chat id.
        assert classify_target("09924466793") == TARGET_PHONE

    def test_international_forms(self):
        assert classify_target("989924466793") == TARGET_PHONE
        assert classify_target("+98 992 446 6793") == TARGET_PHONE

    def test_persian_digits_phone(self):
        assert classify_target("۰۹۹۲۴۴۶۶۷۹۳") == TARGET_PHONE

    def test_persian_name(self):
        assert classify_target("نفس پیروز") == TARGET_NAME

    def test_username_is_name(self):
        assert classify_target("@nas") == TARGET_NAME

    def test_blank_is_name(self):
        assert classify_target("") == TARGET_NAME


class FakeClient:
    def __init__(self, phones=None, me_id=999):
        self.phones = dict(phones or {})
        self.me_id = me_id
        self.sent = []
        self.searches = []

    async def get_me(self):
        return SimpleNamespace(id=self.me_id)

    async def search_contact(self, phone_number):
        self.searches.append(phone_number)
        chat_id = self.phones.get(phone_number)
        return SimpleNamespace(id=chat_id) if chat_id else None

    async def send_message(self, *, text, chat_id, chat_type=None):
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=len(self.sent), date=1234)


class TestResolveTarget:
    @pytest.mark.asyncio
    async def test_phone_lookup_normalizes(self):
        client = FakeClient({"989924466793": 42})
        resolved = await resolve_target(client, "09924466793")
        assert resolved.chat_id == 42
        assert resolved.kind == TARGET_PHONE
        assert client.searches == ["989924466793"]

    @pytest.mark.asyncio
    async def test_phone_not_found_reports_error(self):
        resolved = await resolve_target(FakeClient(), "09924466793")
        assert resolved.chat_id is None
        assert "not found" in resolved.error

    @pytest.mark.asyncio
    async def test_chat_id_passthrough(self):
        resolved = await resolve_target(FakeClient(), "12345")
        assert resolved.chat_id == 12345
        assert resolved.kind == TARGET_CHAT_ID

    @pytest.mark.asyncio
    async def test_name_uses_contact_index(self):
        index = ContactIndex([SavedContact(7, "نفس پیروز", local_name="نفس")])
        resolved = await resolve_target(FakeClient(), "نفس", index=index)
        assert resolved.chat_id == 7
        assert resolved.matched_name == "نفس پیروز"

    @pytest.mark.asyncio
    async def test_ambiguous_name_reports_candidates(self):
        index = ContactIndex([SavedContact(1, "نفس پیروز"), SavedContact(2, "نفس خدمتی")])
        resolved = await resolve_target(FakeClient(), "نفس", index=index)
        assert resolved.chat_id is None
        assert "2 contacts match" in resolved.error

    @pytest.mark.asyncio
    async def test_name_without_index(self):
        resolved = await resolve_target(FakeClient(), "نفس")
        assert "no contact index" in resolved.error


class TestSendToTargets:
    @pytest.mark.asyncio
    async def test_dry_run_sends_nothing(self):
        client = FakeClient({"989924466793": 42})
        index = ContactIndex([SavedContact(7, "نفس")])
        results = await send_to_targets(
            client, ["09924466793", "نفس", "12345"], "سلام", dry_run=True, index=index
        )
        assert [r.ok for r in results] == [True, True, True]
        assert client.sent == []
        assert results[1].chat_id == 7
        assert "matches نفس" in results[1].detail

    @pytest.mark.asyncio
    async def test_real_send_stores_outgoing_message(self, tmp_path, monkeypatch):
        monkeypatch.setattr(outbound_mod, "_private_chat_type", lambda: "PRIVATE")
        store = SupportStore(tmp_path / "inbox.sqlite")
        client = FakeClient({"989924466793": 42})
        results = await send_to_targets(
            client, ["09924466793"], "سلام", store=store
        )
        assert client.sent == [(42, "سلام")]
        assert results[0].ok is True
        rows = store.recent_messages()
        assert len(rows) == 1
        assert rows[0].direction == "out"
        assert rows[0].chat_id == "42"

    @pytest.mark.asyncio
    async def test_failure_is_isolated_per_target(self):
        client = FakeClient()
        seen = []
        results = await send_to_targets(
            client,
            ["09924466793", "111"],
            "hi",
            dry_run=True,
            on_progress=lambda pos, total, target: seen.append((pos, total, target)),
        )
        assert [r.ok for r in results] == [False, True]
        assert seen == [(1, 2, "09924466793"), (2, 2, "111")]

    @pytest.mark.asyncio
    async def test_empty_text_rejected(self):
        with pytest.raises(ValueError):
            await send_to_targets(FakeClient(), ["111"], "   ")

    @pytest.mark.asyncio
    async def test_blank_targets_skipped(self):
        results = await send_to_targets(FakeClient(), ["", "  "], "hi", dry_run=True)
        assert results == []
