"""Tests for support-agent inbox store and analysis."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform.analysis import analyze_concerns, classify_text, collect_for_faq
from bale_platform.phone import normalize_phone_int
from bale_platform.store import StoredMessage, SupportStore


class TestPhone:
    def test_local_09(self):
        assert normalize_phone_int("09924466793") == 989924466793


class TestAnalysis:
    def test_classify_sales(self):
        assert classify_text("قیمت دوره چقدره؟") == "sales"

    def test_classify_technical(self):
        assert classify_text("cannot login to minecraft server") == "technical"

    def test_analyze_buckets(self):
        msgs = [
            StoredMessage("1", 1, "9", "قیمت چقدره", "t", 1, "in"),
            StoredMessage("2", 2, "8", "server lag", "t", 2, "in"),
            StoredMessage("3", 3, "7", "level 3 class", "t", 3, "in"),
        ]
        summary = analyze_concerns(msgs)
        assert summary["total_messages"] == 3
        cats = {b["category"] for b in summary["categories"]}
        assert "sales" in cats
        assert "technical" in cats


class TestStore:
    def test_agent_unread(self, tmp_path):
        store = SupportStore(tmp_path / "inbox.sqlite")
        store.upsert_message(
            {
                "chat_id": "100",
                "message_id": 10,
                "sender_id": "9",
                "text": "hello",
                "timestamp": "t",
                "date_ms": 1,
            },
            direction="in",
        )
        unread = store.unread_for_agent("sara")
        assert len(unread) == 1
        store.ack_chat("sara", "100", 10)
        assert store.unread_for_agent("sara") == []

    def test_collect_for_faq(self, tmp_path):
        store = SupportStore(tmp_path / "inbox.sqlite")
        store.upsert_message(
            {
                "chat_id": "100",
                "message_id": 1,
                "sender_id": "9",
                "text": "register please",
                "timestamp": "t",
                "date_ms": 1,
            },
            direction="in",
        )
        rows = collect_for_faq(store.recent_messages())
        assert rows[0]["category"] == "sales"

    def test_events_cursor_keeps_seq_on_update(self, tmp_path):
        store = SupportStore(tmp_path / "inbox.sqlite")
        first = {
            "chat_id": "100",
            "message_id": 1,
            "sender_id": "9",
            "text": "hello",
            "timestamp": "t",
            "date_ms": 10,
        }
        store.upsert_message(first, direction="in")
        store.upsert_message(
            {
                "chat_id": "100",
                "message_id": 2,
                "sender_id": "9",
                "text": "again",
                "timestamp": "t",
                "date_ms": 20,
            },
            direction="in",
        )
        store.upsert_message({**first, "text": "hello edited"}, direction="in")
        page = store.events_after(0, limit=1)
        assert len(page) == 1
        assert page[0].seq == 1
        assert page[0].text == "hello edited"
        rest = store.events_after(page[0].seq, limit=10)
        assert [row.message_id for row in rest] == [2]
        history = store.history("100", limit=10)
        assert [row.message_id for row in history] == [1, 2]

    def test_old_inbox_gains_seq(self, tmp_path):
        path = tmp_path / "old.sqlite"
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE messages (
                chat_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                sender_id TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                date_ms INTEGER NOT NULL,
                direction TEXT NOT NULL DEFAULT 'in',
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO messages VALUES ('1', 5, '9', 'old', 't', 1, 'in')"
        )
        conn.commit()
        conn.close()
        store = SupportStore(path)
        rows = store.events_after(0)
        assert rows[0].seq == 1
        assert rows[0].kind == "text"
        assert rows[0].text == "old"
