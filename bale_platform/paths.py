"""Shared on-disk paths for local stores, logs and the KB.

Every path is overridable with a ``BALE_*`` env var (see ``.ai/setup/env-vars.md``),
so the CLI, the runner and the admin panel all agree on where data lives.
"""

from __future__ import annotations

import os
from pathlib import Path

from bale_platform.contact_store import DEFAULT_CONTACTS_PATH
from bale_platform.store import DEFAULT_STORE_PATH


def store_path() -> Path:
    """Support inbox DB (messages + agent acks)."""
    return Path(os.getenv("BALE_STORE_PATH", str(DEFAULT_STORE_PATH)))


def contacts_path() -> Path:
    """Persistent local contact book."""
    return Path(os.getenv("BALE_CONTACTS_PATH", str(DEFAULT_CONTACTS_PATH)))


def log_path() -> Path:
    """Runner log file."""
    return Path(os.getenv("BALE_LOG_FILE", "logs/userbot.log"))


def kb_dir() -> Path:
    return Path(os.getenv("BALE_KB_DIR", "kb"))


def facts_path() -> Path:
    """Structured facts written by ``kb.learn`` (no raw text)."""
    return kb_dir() / "learned_facts.mdl"
