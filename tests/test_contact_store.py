"""Tests for the persistent local contact book (`data/contacts.sqlite`).

The book is what `send` resolves names against, so these tests pin the two
rules that matter operationally:

1. a refresh from Bale never loses a row a human added;
2. a name a human typed is never overwritten by Bale data.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform import contacts as contacts_mod
from bale_platform.contact_store import SOURCE_MANUAL, ContactBook, refresh_book
from bale_platform.contacts import SavedContact


@pytest.fixture(autouse=True)
def fake_chat_type(monkeypatch):
    monkeypatch.setattr(contacts_mod, "_private_chat_type", lambda: "PRIVATE")


def book(tmp_path) -> ContactBook:
    return ContactBook(tmp_path / "contacts.sqlite")


class TestBookBasics:
    def test_empty_book(self, tmp_path):
        store = book(tmp_path)
        assert len(store) == 0
        assert store.all() == []
        assert store.count() == 0

    def test_add_manual_and_resolve(self, tmp_path):
        store = book(tmp_path)
        entry = store.add_manual("نفس پیروز", 1311340524)
        assert entry.manual is True
        assert entry.source == SOURCE_MANUAL
        assert store.get(1311340524).name == "نفس پیروز"
        assert store.to_index().resolve("نفس").chat_id == 1311340524

    def test_manual_name_defaults_to_id(self, tmp_path):
        store = book(tmp_path)
        assert store.add_manual("   ", 555).name == "555"

    def test_space_insensitive_resolution(self, tmp_path):
        store = book(tmp_path)
        store.add_manual("امیرحافظ سفیدبری", 1858791866)
        assert store.to_index().resolve("امیر حافظ سفیدبری").chat_id == 1858791866

    def test_re_add_keeps_manual_flag(self, tmp_path):
        store = book(tmp_path)
        store.upsert_bale(SavedContact(7, "از بله", source="dialog"))
        entry = store.add_manual("اسم من", 7)
        assert entry.manual is True
        assert store.get(7).name == "اسم من"

    def test_remove(self, tmp_path):
        store = book(tmp_path)
        store.add_manual("x", 1)
        assert store.remove(1) is True
        assert store.remove(1) is False
        assert len(store) == 0

    def test_search(self, tmp_path):
        store = book(tmp_path)
        store.add_manual("نفس پیروز", 1)
        store.add_manual("امیرحافظ", 2)
        assert [e.chat_id for e in store.search("نفس")] == [1]
        assert store.search("ناموجود") == []

    def test_stats(self, tmp_path):
        store = book(tmp_path)
        store.add_manual("دستی", 1)
        store.upsert_bale(SavedContact(2, "از بله", source="dialog"))
        assert store.stats() == {"manual": 1, "dialog": 1}

    def test_json_shape(self, tmp_path):
        store = book(tmp_path)
        payload = store.add_manual("نفس", 1).as_dict()
        assert payload["chat_id"] == 1
        assert payload["manual"] is True
        assert "updated_at" in payload


class TestUpsertPolicy:
    def test_new_row_from_bale(self, tmp_path):
        store = book(tmp_path)
        assert store.upsert_bale(SavedContact(7, "نفس", source="dialog")) == "added"

    def test_non_manual_row_is_updated(self, tmp_path):
        store = book(tmp_path)
        store.upsert_bale(SavedContact(7, "نفس", source="dialog"))
        assert store.upsert_bale(SavedContact(7, "نفس پیروز", source="dialog")) == "updated"
        assert store.get(7).name == "نفس پیروز"

    def test_manual_name_wins_but_bale_fields_refresh(self, tmp_path):
        store = book(tmp_path)
        store.add_manual("اسم دلخواه من", 7)
        action = store.upsert_bale(
            SavedContact(7, "خود بله", local_name="بله", source="dialog")
        )
        assert action == "kept"
        entry = store.get(7)
        assert entry.name == "اسم دلخواه من"
        assert entry.local_name == "بله"
        assert entry.manual is True

    def test_prune_keeps_manual_rows(self, tmp_path):
        store = book(tmp_path)
        store.add_manual("دستی", 1)
        store.upsert_bale(SavedContact(2, "خودکار", source="dialog"))
        assert store.prune([1]) == 1
        assert {e.chat_id for e in store.all()} == {1}


class FakeClient:
    """Duck-typed stand-in for aiobale's Client (only what we call)."""

    def __init__(self, *, address_book=(), users=(), dialogs=()):
        self.address_book = list(address_book)
        self.users = {u.id: u for u in users}
        self.dialogs = list(dialogs)

    async def load_contacts(self):
        return list(self.address_book)

    async def load_users(self, peers):
        return [self.users[p.id] for p in peers if p.id in self.users]

    async def load_user(self, chat_id, chat_type=None):
        return self.users[chat_id]

    async def load_dialogs(self, limit=40):
        return list(self.dialogs)


def user(uid, *, name="", local_name=""):
    return SimpleNamespace(id=uid, name=name, local_name=local_name, username="")


def dialog(peer_id, peer_type=1):
    return SimpleNamespace(peer=SimpleNamespace(id=peer_id, type=peer_type))


class TestRefreshBook:
    @pytest.mark.asyncio
    async def test_first_refresh_adds_then_updates(self, tmp_path):
        client = FakeClient(
            users=[user(1, name="نفس پیروز", local_name="نفس"), user(2, name="گیمر")],
            dialogs=[dialog(1), dialog(2)],
        )
        store = book(tmp_path)
        first = await refresh_book(store, client)
        assert (first["found"], first["added"], first["total"]) == (2, 2, 2)
        second = await refresh_book(store, client)
        assert second["added"] == 0
        assert second["updated"] == 2
        assert len(store) == 2

    @pytest.mark.asyncio
    async def test_refresh_keeps_manual_names(self, tmp_path):
        client = FakeClient(
            users=[user(1, name="نفس پیروز", local_name="نفس")], dialogs=[dialog(1)]
        )
        store = book(tmp_path)
        store.add_manual("اسم دستی", 1)
        counts = await refresh_book(store, client)
        assert counts["kept"] == 1
        assert store.get(1).name == "اسم دستی"

    @pytest.mark.asyncio
    async def test_address_book_only_refresh(self, tmp_path):
        client = FakeClient(
            address_book=[SimpleNamespace(id=1, type=1)],
            users=[user(1, name="نفس")],
            dialogs=[dialog(2)],
        )
        store = book(tmp_path)
        counts = await refresh_book(store, client, dialog_limit=0)
        assert counts["found"] == 1

    @pytest.mark.asyncio
    async def test_prune_removes_stale_auto_rows(self, tmp_path):
        client = FakeClient(users=[user(1, name="نفس")], dialogs=[dialog(1)])
        store = book(tmp_path)
        store.upsert_bale(SavedContact(99, "قدیمی", source="dialog"))
        counts = await refresh_book(store, client, prune=True)
        assert counts["pruned"] == 1
        assert {e.chat_id for e in store.all()} == {1}

    @pytest.mark.asyncio
    async def test_broken_lookups_do_not_crash_and_are_reported(self, tmp_path):
        class Broken(FakeClient):
            async def load_contacts(self):
                raise RuntimeError("no address book")

            async def load_dialogs(self, limit=40):
                raise RuntimeError("rate limited")

        store = book(tmp_path)
        counts = await refresh_book(store, Broken())
        assert counts["found"] == 0
        assert counts["total"] == 0
        assert any("failed" in note for note in counts["notes"])
