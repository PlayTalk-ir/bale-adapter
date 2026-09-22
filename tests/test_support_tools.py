"""Tests for support-agent inbox store and analysis."""

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
