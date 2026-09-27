"""Tests for bale_platform.adapter and kb.learn.

The userbot adapter delegates message parsing to aiobale, so we test:
    1. _normalize_message: handles aiobale Message and duck-typed objects
    2. _extract_text: handles TextMessage, captioned media, and non-text
    3. BaleUserbotConfig: env vars, defaults, is_configured()
    4. BaleUserbotAdapter.is_configured() preflight
    5. kb.learn: observe-extract pattern (was already tested in the bot shape,
       kept for regression).

Run with:  pytest -q tests
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
# CI: provide a stub for aiobale (the real one is git-only and not on PyPI).
# Locally on the VPS, aiobale is installed in the venv by bootstrap.sh.
try:
    import aiobale  # noqa: F401
except ImportError:
    sys.path.insert(0, str(ROOT / "tests"))
    import _aiobale_stub  # noqa: F401

from bale_platform.adapter import BaleUserbotAdapter, _extract_text, _normalize_message
from bale_platform.config import BaleUserbotConfig, is_configured
from kb import learn  # noqa: E402


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_text_message(self):
        content = SimpleNamespace(value="hello world")
        assert _extract_text(content) == "hello world"

    def test_captioned_media(self):
        content = SimpleNamespace(
            caption=SimpleNamespace(content="see attached image"),
        )
        assert _extract_text(content) == "see attached image"

    def test_non_text_returns_empty(self):
        # Document with no caption
        content = SimpleNamespace(file_id=42, mime_type="image/png")
        assert _extract_text(content) == ""

    def test_none_content(self):
        assert _extract_text(None) == ""

    def test_text_preferred_over_caption(self):
        # If somehow both exist, text wins
        content = SimpleNamespace(value="primary", caption=SimpleNamespace(content="alt"))
        assert _extract_text(content) == "primary"


# ---------------------------------------------------------------------------
# _normalize_message
# ---------------------------------------------------------------------------


class TestNormalizeMessage:
    def test_basic(self):
        m = SimpleNamespace(
            message_id=1,
            sender_id=99,
            chat=SimpleNamespace(id=42, type="private"),
            content=SimpleNamespace(value="hi"),
        )
        norm = _normalize_message(m)
        assert norm["message_id"] == 1
        assert norm["sender_id"] == "99"
        assert norm["chat_id"] == "42"
        assert norm["text"] == "hi"

    def test_empty_text_stripped(self):
        m = SimpleNamespace(
            message_id=2,
            sender_id=99,
            chat=SimpleNamespace(id=42, type="private"),
            content=SimpleNamespace(value="   "),
        )
        norm = _normalize_message(m)
        assert norm["text"].strip() == ""

    def test_non_text_content(self):
        m = SimpleNamespace(
            message_id=3,
            sender_id=99,
            chat=SimpleNamespace(id=42, type="group"),
            content=SimpleNamespace(file_id=1, mime_type="image/png"),
        )
        norm = _normalize_message(m)
        assert norm["text"] == ""


# ---------------------------------------------------------------------------
# BaleUserbotConfig
# ---------------------------------------------------------------------------


class TestBaleUserbotConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("BALE_SESSION_PATH", raising=False)
        monkeypatch.delenv("BALE_OBSERVE_ONLY", raising=False)
        monkeypatch.delenv("BALE_ALLOWED_CHATS", raising=False)
        cfg = BaleUserbotConfig.from_env()
        assert cfg.session_path.name == "session.bale"
        assert cfg.kb_dir.name == "kb"
        assert cfg.observe_only is True
        assert cfg.allowed_chats is None

    def test_env_overrides(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BALE_SESSION_PATH", str(tmp_path / "custom.bale"))
        monkeypatch.setenv("BALE_KB_DIR", str(tmp_path / "kbx"))
        monkeypatch.setenv("BALE_OBSERVE_ONLY", "false")
        monkeypatch.setenv("BALE_ALLOWED_CHATS", "100, 200, 300")
        cfg = BaleUserbotConfig.from_env()
        assert cfg.session_path.name == "custom.bale"
        assert cfg.kb_dir.name == "kbx"
        assert cfg.observe_only is False
        assert cfg.allowed_chats == ["100", "200", "300"]

    def test_is_configured_missing(self, tmp_path, monkeypatch):
        # Point is_configured at a path that doesn't exist
        from bale_platform import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "SESSION_PATH", tmp_path / "nope.bale")
        assert cfg_mod.is_configured() is False

    def test_is_configured_present(self, tmp_path, monkeypatch):
        from bale_platform import config as cfg_mod
        session = tmp_path / "ok.bale"
        session.write_bytes(b"\x00\x01\x02")
        monkeypatch.setattr(cfg_mod, "SESSION_PATH", session)
        assert cfg_mod.is_configured() is True


# ---------------------------------------------------------------------------
# Adapter preflight
# ---------------------------------------------------------------------------


class TestAdapterPreflight:
    def test_start_without_session_raises(self, tmp_path, monkeypatch):
        from bale_platform import config as cfg_mod

        monkeypatch.setattr(cfg_mod, "SESSION_PATH", tmp_path / "missing.bale")
        cfg = BaleUserbotConfig.from_env()
        adapter = BaleUserbotAdapter(cfg)
        with pytest.raises(RuntimeError, match="session file not found"):
            # Run the coroutine to completion — we want the guard to fire
            # inside `async def start()` before aiobale is touched.
            import asyncio
            ev = asyncio.Event()
            asyncio.run(adapter.start(ev))


# ---------------------------------------------------------------------------
# KB learn (observe-extract) — regression from the bot-shape tests
# ---------------------------------------------------------------------------


class TestKbLearn:
    def test_extract_pricing(self):
        fact = learn.extract_fact("قیمت دوره ۲ میلیون تومان", sender="@parent")
        assert fact is not None
        assert "[pricing]" in fact

    def test_extract_age(self):
        fact = learn.extract_fact("child age: 9", sender="@parent")
        assert fact is not None
        assert "[student_age]" in fact
        assert "9" in fact

    def test_extract_level(self):
        fact = learn.extract_fact("level 3 — what are the prerequisites?", sender="@parent")
        assert fact is not None
        assert "[course_level]" in fact
        assert "3" in fact

    def test_no_extract_for_chitchat(self):
        fact = learn.extract_fact("hello there", sender="@anyone")
        assert fact is None

    def test_pii_blocked(self):
        fact = learn.extract_fact("my national id is 1234567890", sender="@anyone")
        assert fact is None

    def test_persian_numerals_normalized(self):
        fact = learn.extract_fact("سن: ۹ سال", sender="@parent")
        assert fact is not None
        assert "[student_age]" in fact
        assert "9" in fact  # ASCII 9, not Persian ۹

    def test_sender_recorded(self):
        fact = learn.extract_fact("level 2 please", sender="@erfan")
        assert fact is not None
        assert "@erfan" in fact
