"""Bale userbot adapter — Shape C.

Connects to Bale as the logged-in COMPANY account using aiobale's persistent
session file. Observes all incoming messages, hands text to kb.learn for
fact extraction, and stores ONLY structured facts (never raw text) to the KB.

The aiobale import is lazy-guarded: the skeleton runs without aiobale
installed so the repo can be deployed and CI-tested before a real login.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from bale_platform.api.server import ApiRuntime, run_api_server
from bale_platform.api_config import ApiSettings
from bale_platform.config import BaleUserbotConfig
from bale_platform.messages import extract_text as _extract_text
from bale_platform.messages import normalize_message as _normalize_message
from bale_platform.outbox.store import OutboxStore
from bale_platform.outbox.worker import OutboxWorker
from bale_platform.resolver import RecipientResolver
from bale_platform.sender import BaleSender, DryRunBaleSender, make_sender
from bale_platform.session_state import session_file_ready
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
        self._api_settings = ApiSettings.from_env()
        self._outbox: Optional[OutboxStore] = None
        self._worker: Optional[OutboxWorker] = None
        self._api_runner: Any = None
        self._session_ok = False
        self._session_reason: str = "disconnected"
        self._paused_flag = self._api_settings.sending_paused
        self._connect_task: Optional[asyncio.Task] = None
        self._dispatcher: Any = None

    def session_reason(self) -> str:
        return self._session_reason

    def _sending_paused(self) -> bool:
        env_pause = os.getenv("BALE_SENDING_PAUSED", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return env_pause or self._paused_flag or (
            self._outbox is not None and self._outbox.breaker_open()
        )

    def _resume_breaker(self) -> None:
        self._paused_flag = False
        if self._outbox:
            self._outbox.resume_breaker()

    def _get_sender(self) -> BaleSender:
        if self._api_settings.send_mode == "dry_run":
            return DryRunBaleSender()
        if self._client is None:
            raise RuntimeError("Bale client not connected")
        return make_sender(self._api_settings.send_mode, self._client)

    def _get_resolver(self) -> Optional[RecipientResolver]:
        if self._outbox is None or self._client is None:
            return None
        return RecipientResolver(
            self._client,
            self._outbox,
            phone_pepper=self._api_settings.phone_pepper or "local-dev",
            allow_contact_import=self._api_settings.allow_contact_import,
            new_peer_max_per_day=self._api_settings.new_peer_max_per_day,
            lookup_min_interval_s=self._api_settings.lookup_min_interval_s,
        )

    async def _start_api_and_worker(self) -> None:
        self._outbox = OutboxStore(self._api_settings.outbox_path)
        runtime = ApiRuntime(
            self._api_settings,
            self._outbox,
            session_connected=lambda: self._session_ok,
            session_reason=self.session_reason,
            sending_paused=self._sending_paused,
            resume_breaker=self._resume_breaker,
        )
        self._api_runner = await run_api_server(
            runtime, self._api_settings.host, self._api_settings.port
        )
        self._worker = OutboxWorker(
            self._outbox,
            self._api_settings,
            get_client=lambda: self._client,
            get_sender=self._get_sender,
            get_resolver=self._get_resolver,
            session_connected=lambda: self._session_ok,
            sending_paused=self._sending_paused,
        )
        self._worker.start()
        logger.info("Bale HTTP API and outbox worker started")

    async def _connect_client(self) -> None:
        try:
            from aiobale import Client, Dispatcher  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "aiobale is not installed. Run scripts/bootstrap.sh — it "
                "installs aiobale from https://github.com/mehrad1232/Aiobale "
                "(PyPI's aiobale is an empty shell; the original Enalite/aiobale "
                "repo was taken down)."
            ) from exc

        if self._dispatcher is None:
            self._dispatcher = Dispatcher()
            self._dispatcher.message()(self._on_message)

        if self._client is None:
            self._client = Client(
                dispatcher=self._dispatcher,
                session_file=str(self.cfg.session_path),
            )
        try:
            me = await self._client.get_me()
            self._account_user_id = str(getattr(me, "id", "") or "")
        except Exception:
            logger.exception("could not load account id for inbox store")
        logger.info(
            "Bale userbot connecting (session=%s, observe_only=%s, api=%s)",
            self.cfg.session_path,
            self.cfg.observe_only,
            self._api_settings.enabled,
        )
        await self._client.start(run_in_background=True)

    async def _disconnect_client(self) -> None:
        if self._client is None:
            return
        try:
            close = getattr(self._client, "close", None) or getattr(self._client, "stop", None)
            if close is not None:
                res = close()
                if asyncio.iscoroutine(res):
                    await res
        except Exception:
            logger.exception("error closing Bale client")
        self._client = None
        self._session_ok = False

    async def _session_connect_loop(self, stop_event: asyncio.Event) -> None:
        backoff = self.cfg.reconnect_min_seconds
        while not stop_event.is_set():
            if not session_file_ready(self.cfg.session_path):
                self._session_ok = False
                self._session_reason = "session_file_missing"
                await self._disconnect_client()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, self.cfg.reconnect_max_seconds)
                continue
            if self._session_ok and self._client is not None:
                await asyncio.sleep(5.0)
                continue
            self._session_reason = "connecting"
            try:
                await self._connect_client()
                self._session_ok = True
                self._session_reason = "connected"
                backoff = self.cfg.reconnect_min_seconds
                logger.info("Bale session connected")
            except Exception as exc:
                self._session_ok = False
                self._session_reason = f"connect_failed: {exc}"
                logger.warning("Bale session connect failed: %s", exc)
                await self._disconnect_client()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, self.cfg.reconnect_max_seconds)

    async def start(self, stop_event: asyncio.Event) -> None:
        _ensure_paths(self.cfg)

        if self._api_settings.enabled:
            self._api_settings.validate_startup()
            if not session_file_ready(self.cfg.session_path):
                self._session_reason = "session_file_missing"
            await self._ensure_fact_writer()
            await self._start_api_and_worker()
            self._connect_task = asyncio.create_task(
                self._session_connect_loop(stop_event), name="bale-session-connect"
            )
            await stop_event.wait()
            return

        if not session_file_ready(self.cfg.session_path):
            raise RuntimeError(
                f"session file not found at {self.cfg.session_path} — "
                "run scripts/login.py first to authenticate."
            )

        await self._ensure_fact_writer()
        await self._connect_client()
        self._session_ok = True
        self._session_reason = "connected"
        await stop_event.wait()

    async def stop(self) -> None:
        self._session_ok = False
        if self._connect_task:
            self._connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connect_task
        if self._worker:
            await self._worker.stop()
        if self._api_runner:
            await self._api_runner.cleanup()
        if self._outbox:
            self._outbox.close()
        await self._disconnect_client()
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
