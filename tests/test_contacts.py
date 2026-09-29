"""Tests for saved-contact name resolution (Persian names → Bale chat ids).

aiobale is a git-only dependency, so these tests drive duck-typed fakes and
patch the lazy ``_private_chat_type`` hook — ``bale_platform.contacts`` never
imports aiobale at import time (CI runs without aiobale installed).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform import contacts as contacts_mod
from bale_platform.contacts import (
    ContactIndex,
    NameNotFound,
    NameNotUnique,
    SavedContact,
    build_contact_index,
    normalize_name,
    peer_is_private,
)


@pytest.fixture(autouse=True)
def fake_chat_type(monkeypatch):
    """Stand in for ``aiobale.enums.ChatType.PRIVATE`` (absent in CI)."""
    monkeypatch.setattr(contacts_mod, "_private_chat_type", lambda: "PRIVATE")


def contact(chat_id, name, **kwargs):
    return SavedContact(chat_id=chat_id, name=name, **kwargs)


class TestNormalizeName:
    def test_zero_width_joiner_ignored(self):
        assert normalize_name("نفس\u200cپیروز") == normalize_name("نفس پیروز").replace(" ", "")

    def test_arabic_letter_variants_fold(self):
        assert normalize_name("يكي كوچك") == normalize_name("یکی کوچک")

    def test_persian_digits_to_ascii(self):
        assert normalize_name("کیان ۱۲") == "کیان 12"

    def test_decoration_and_emoji_removed(self):
        assert normalize_name("• محمدمهدی زینعلی(گیمر) 🥲") == "محمدمهدی زینعلی گیمر"

    def test_latin_casefolded(self):
        assert normalize_name("Ali Reza") == "ali reza"

    def test_empty_input(self):
        assert normalize_name(None) == ""


class TestContactIndexResolution:
    def test_saved_local_name(self):
        index = ContactIndex([contact(1311340524, "نفس پیروز", local_name="نفس")])
        assert index.resolve("نفس").chat_id == 1311340524

    def test_space_differences_tolerated(self):
        index = ContactIndex([contact(1858791866, "امیرحافظ سفیدبری")])
        assert index.resolve("امیر حافظ سفیدبری").chat_id == 1858791866

    def test_unique_prefix(self):
        index = ContactIndex([contact(1, "نفس پیروز")])
        assert index.resolve("نفس").chat_id == 1

    def test_unique_substring(self):
        index = ContactIndex([contact(1, "هانیه خدمتی مدرس")])
        assert index.resolve("خدمتی").chat_id == 1

    def test_username_variant(self):
        index = ContactIndex([contact(1, "نفس پیروز", username="nas")])
        assert index.resolve("@nas").chat_id == 1

    def test_profile_name_variant(self):
        index = ContactIndex(
            [contact(1, "بابا", local_name="بابا", profile_name="علی رضایی")]
        )
        assert index.resolve("علی رضایی").chat_id == 1

    def test_ambiguous_name_raises_with_candidates(self):
        index = ContactIndex([contact(1, "نفس پیروز"), contact(2, "نفس خدمتی")])
        with pytest.raises(NameNotUnique) as excinfo:
            index.resolve("نفس")
        assert "2 contacts match" in str(excinfo.value)
        assert "1 (نفس پیروز)" in str(excinfo.value)

    def test_unknown_name_raises(self):
        with pytest.raises(NameNotFound):
            ContactIndex([contact(1, "نفس پیروز")]).resolve("آدم ناموجود")

    def test_blank_query_raises(self):
        with pytest.raises(NameNotFound):
            ContactIndex([contact(1, "نفس")]).resolve("   ")

    def test_duplicate_chat_ids_collapsed(self):
        index = ContactIndex([contact(1, "الف"), contact(1, "الف")])
        assert len(index) == 1

    def test_search_is_fuzzy_and_never_raises(self):
        index = ContactIndex([contact(1, "نفس پیروز"), contact(2, "امیرحافظ")])
        assert [c.chat_id for c in index.search("نفس")] == [1]
        assert index.search("هیچ‌کس") == []


class FakeClient:
    """Duck-typed stand-in for aiobale's Client (only what we call)."""

    def __init__(self, *, address_book=(), users=(), dialogs=(), fail_batch=False):
        self.address_book = list(address_book)
        self.users = {u.id: u for u in users}
        self.dialogs = list(dialogs)
        self.fail_batch = fail_batch
        self.individual_lookups = []
        self.batch_calls = 0

    async def load_contacts(self):
        return list(self.address_book)

    async def load_users(self, peers):
        self.batch_calls += 1
        if self.fail_batch:
            raise RuntimeError("batch lookup failed")
        return [self.users[p.id] for p in peers if p.id in self.users]

    async def load_user(self, chat_id, chat_type=None):
        self.individual_lookups.append(chat_id)
        return self.users[chat_id]

    async def load_dialogs(self, limit=40):
        return list(self.dialogs)


def user(uid, *, name="", local_name="", username="", is_bot=False):
    return SimpleNamespace(
        id=uid, name=name, local_name=local_name, username=username, is_bot=is_bot
    )


def dialog(peer_id, peer_type=1):
    return SimpleNamespace(
        peer=SimpleNamespace(id=peer_id, type=peer_type), unread_count=0
    )


class TestBuildContactIndex:
    @pytest.mark.asyncio
    async def test_merges_address_book_and_dialogs(self):
        client = FakeClient(
            address_book=[SimpleNamespace(id=1, type=1)],
            users=[
                user(1, name="نفس پیروز", local_name="نفس"),
                user(2, name="گیمر محمدمهدی"),
            ],
            dialogs=[dialog(2), dialog(3, peer_type=2)],
        )
        index = await build_contact_index(client)
        assert len(index) == 2
        assert index.get(1).source == "contacts"
        assert index.get(2).source == "dialog"
        assert index.resolve("نفس").chat_id == 1

    @pytest.mark.asyncio
    async def test_dialogs_can_be_skipped(self):
        client = FakeClient(
            address_book=[SimpleNamespace(id=1, type=1)],
            users=[user(1, name="نفس")],
            dialogs=[dialog(2)],
        )
        index = await build_contact_index(client, include_dialogs=False)
        assert len(index) == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_individual_lookup(self):
        client = FakeClient(
            address_book=[SimpleNamespace(id=1, type=1)],
            users=[user(1, name="نفس")],
            fail_batch=True,
        )
        index = await build_contact_index(client, include_dialogs=False)
        assert client.individual_lookups == [1]
        assert index.resolve("نفس").chat_id == 1

    @pytest.mark.asyncio
    async def test_contacts_api_failure_is_tolerated(self):
        class Broken(FakeClient):
            async def load_contacts(self):
                raise RuntimeError("unsupported")

        client = Broken(users=[user(1, name="نفس")], dialogs=[dialog(1)])
        index = await build_contact_index(client)
        assert index.resolve("نفس").chat_id == 1

    @pytest.mark.asyncio
    async def test_contact_without_name_falls_back_to_id(self):
        client = FakeClient(
            address_book=[SimpleNamespace(id=555, type=1)],
            users=[user(555)],
        )
        index = await build_contact_index(client, include_dialogs=False)
        assert index.get(555).name == "555"

    @pytest.mark.asyncio
    async def test_notes_report_lookup_diagnostics(self):
        client = FakeClient(
            address_book=[SimpleNamespace(id=1, type=1)],
            users=[user(1, name="نفس")],
            dialogs=[dialog(2)],
        )
        index = await build_contact_index(client)
        assert any("address book: 1" in note for note in index.notes)
        assert any("dialogs: 1" in note for note in index.notes)

    @pytest.mark.asyncio
    async def test_failed_lookups_are_visible_not_silent(self):
        class Broken(FakeClient):
            async def load_contacts(self):
                raise RuntimeError("no address book")

            async def load_dialogs(self, limit=40):
                raise RuntimeError("rate limited")

        index = await build_contact_index(Broken())
        assert len(index) == 0
        assert any("address book failed" in note for note in index.notes)
        assert any("dialogs failed" in note for note in index.notes)


class TestPeerHelpers:
    def test_private_peer_int_type(self):
        assert peer_is_private(SimpleNamespace(id=1, type=1)) is True
        assert peer_is_private(SimpleNamespace(id=1, type=2)) is False

    def test_enum_like_value_attribute(self):
        peer = SimpleNamespace(id=1, type=SimpleNamespace(value=1))
        assert peer_is_private(peer) is True

    def test_garbage_type_is_not_private(self):
        assert peer_is_private(SimpleNamespace(id=1, type="private")) is False
        assert peer_is_private(SimpleNamespace(id=1)) is False
