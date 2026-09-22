"""Bale userbot adapter — Shape C.

Connects to Bale as the logged-in COMPANY account using aiobale's persistent
session file. Observes all incoming messages, hands text to kb.learn for
fact extraction, and stores ONLY structured facts (never raw text) to the KB.

The aiobale import is lazy-guarded: the skeleton runs without aiobale
installed so the repo can be deployed and CI-tested before a real login.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from bale_platform.config import BaleUserbotConfig
from bale_platform.messages import extract_text as _extract_text
from bale_platform.messages import normalize_message as _normalize_message
from bale_platform.store import DEFAULT_STORE_PATH, SupportStore

logger = logging.getLogger("hermes.bale.userbot")


def _ensure_paths(cfg: BaleUserbotConfig) -> None:
    cfg.session_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cfg.kb_dir.mkdir(parents=True, exist_ok=True)
    cfg.log_file.parent.mkdir(parents=True, exist_ok=True)


class BaleUserbotAdapter:
    """Observes messages on a logged-in Bale account.

    Lifecycle:
        cfg = BaleUserbotConfig.from_env()
        adapter = BaleUserbotAdapter(cfg)
        await adapter.start()    # blocks, listens forever
        ...
        await adapter.stop()
    """

    def __init__(self, cfg: BaleUserbotConfig) -> None:
        self.cfg = cfg
        self._client: Any = None
        self._fact_writer: Any = None  # lazy import kb.learn
        store_path = Path(os.getenv("BALE_STORE_PATH", str(DEFAULT_STORE_PATH)))
        self._store = SupportStore(store_path)
        self._account_user_id: Optional[str] = None

    async def start(self) -> None:
        if not self.cfg.session_path.exists():
            raise RuntimeError(
                f"session file not found at {self.cfg.session_path} — "
                "run scripts/login.py first to authenticate."
            )

        _ensure_paths(self.cfg)
        await self._ensure_fact_writer()

        try:
            from aiobale import Client, Dispatcher  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "aiobale is not installed. Run scripts/bootstrap.sh — it "
                "installs aiobale from https://github.com/mehrad1232/Aiobale "
                "(PyPI's aiobale is an empty shell; the original Enalite/aiobale "
                "repo was taken down)."
            ) from exc

        dp = Dispatcher()
        dp.message()(self._on_message)

        self._client = Client(
            dispatcher=dp,
            session_file=str(self.cfg.session_path),
        )
        try:
            me = await self._client.get_me()
            self._account_user_id = str(getattr(me, "id", "") or "")
        except Exception:
            logger.exception("could not load account id for inbox store")
        logger.info(
            "Bale userbot connecting (session=%s, observe_only=%s)",
            self.cfg.session_path,
            self.cfg.observe_only,
        )
        # client.start() blocks while listening for updates. It raises if the
        # session is invalid/missing (token will be None and PhoneLoginCLI will
        # be invoked — we don't want that in the runner, hence the preflight
        # check above).
        await self._client.start()

    async def stop(self) -> None:
        if self._client is not None:
            try:
                close = getattr(self._client, "close", None) or getattr(
                    self._client, "stop", None
                )
                if close is not None:
                    res = close()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                logger.exception("error closing Bale client")
        logger.info("Bale userbot stopped")

    async def _on_message(self, message: Any) -> None:
        """aiobale dispatcher handler — observe + extract, never store raw."""
        norm = _normalize_message(message)
        text = norm["text"].strip()
        if not text:
            return

        chat_id = norm["chat_id"]
        sender = norm["sender_username"] or norm["sender_id"] or "unknown"

        if self.cfg.allowed_chats and chat_id not in self.cfg.allowed_chats:
            logger.debug("Bale: chat %s not in allowlist — skipping", chat_id)
            return

        logger.info(
            "Bale observed msg chat=%s sender=%s len=%d",
            chat_id, sender, len(text),
        )

        direction = (
            "out"
            if self._account_user_id and norm["sender_id"] == self._account_user_id
            else "in"
        )
        try:
            self._store.upsert_message(norm, direction=direction)
        except Exception:
            logger.exception("failed to persist message to support inbox store")

        # Hand off to kb.learn for fact extraction. Raw text is never written.
        if self._fact_writer is None:
            await self._ensure_fact_writer()
        try:
            fact = self._fact_writer.extract_fact(text, sender=sender)
            if fact:
                self._fact_writer.append_fact(fact)
                logger.debug("Bale: stored 1 fact block (no raw text persisted)")
        except Exception:
            logger.exception("Bale fact extraction failed (text not stored)")

    async def _ensure_fact_writer(self) -> None:
        if self._fact_writer is not None:
            return
        # Defer the import so the adapter skeleton can be imported without kb on the path.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import kb.learn as learn_mod  # type: ignore[import-not-found]

        # Make append_fact point at our KB dir, not the module default.
        learn_mod.FACTS_FILE = self.cfg.kb_dir / "learned_facts.mdl"
        learn_mod.FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._fact_writer = learn_mod
