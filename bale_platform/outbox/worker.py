"""Async worker: claim outbox rows and send via shared Bale client."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable, Optional

from bale_platform.api_config import ApiSettings
from bale_platform.outbox.rate_limit import RateLimitConfig, SendRateLimiter
from bale_platform.outbox.store import OutboxStore
from bale_platform.privacy import text_log_fingerprint
from bale_platform.resolver import RecipientResolver, ResolvedRecipient
from bale_platform.sender import BaleSender

logger = logging.getLogger("bale.outbox.worker")

MAX_ATTEMPTS = 5


class OutboxWorker:
    def __init__(
        self,
        store: OutboxStore,
        settings: ApiSettings,
        get_client: Callable[[], Any],
        get_sender: Callable[[], BaleSender],
        get_resolver: Callable[[], Optional[RecipientResolver]],
        *,
        session_connected: Callable[[], bool],
        sending_paused: Callable[[], bool],
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], Any]] = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._get_client = get_client
        self._get_sender = get_sender
        self._get_resolver = get_resolver
        self._session_connected = session_connected
        self._sending_paused = sending_paused
        self._clock = clock or time.time
        self._sleep = sleep or asyncio.sleep
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._limiter = SendRateLimiter(
            store,
            RateLimitConfig(
                send_min_interval_s=settings.send_min_interval_s,
                send_jitter_s=settings.send_jitter_s,
                send_max_per_hour=settings.send_max_per_hour,
                send_max_per_day=settings.send_max_per_day,
                recipient_min_interval_s=settings.recipient_min_interval_s,
                recipient_max_per_hour=settings.recipient_max_per_hour,
                recipient_max_per_day=settings.recipient_max_per_day,
                quiet_hours=settings.quiet_hours,
            ),
            self._clock,
        )

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._run(), name="bale-outbox-worker")
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        n = self._store.recover_stuck_sending()
        if n:
            logger.warning("marked %d stuck sending rows as delivery_unknown", n)
        while not self._stop.is_set():
            now = self._clock()
            self._store.expire_due(now)
            if self._sending_paused() or self._store.breaker_open():
                await self._sleep(1.0)
                continue
            row = self._store.claim_next(now)
            if not row:
                await self._sleep(0.25)
                continue
            await self._process_row(row)
        logger.info("outbox worker stopped")

    def _requeue(self, mid: str, now: float, delay: float = 5.0) -> None:
        self._store.update_row(
            mid,
            status="queued",
            next_attempt_at=now + delay,
            updated_at=now,
        )

    async def _process_row(self, row: dict) -> None:
        mid = row["message_id"]
        now = self._clock()
        try:
            secret = json.loads(row["recipient_secret"] or "{}")
        except json.JSONDecodeError:
            secret = {}

        connected = self._session_connected()
        needs_network = secret.get("type") in ("phone", "username")
        if not connected:
            if self._settings.send_mode == "live":
                self._requeue(mid, now)
                return
            if needs_network:
                self._requeue(mid, now)
                return

        resolver = self._get_resolver()
        rec = None
        err_code = None
        self._store.update_row(mid, status="resolving", updated_at=now)
        if secret.get("type") == "phone":
            if resolver is None:
                self._requeue(mid, now)
                return
            rec, err_code = await resolver.resolve_phone(secret.get("phone", ""))
        elif secret.get("type") == "username":
            if resolver is None:
                self._requeue(mid, now)
                return
            rec, err_code = await resolver.resolve_username(secret.get("username", ""))
        elif secret.get("type") == "bale_user_id":
            uid_raw = str(secret.get("bale_user_id", "")).strip()
            if not uid_raw.isdigit():
                err_code = "recipient_invalid"
            else:
                rec = ResolvedRecipient(int(uid_raw), "bale_user_id", uid_raw)
        else:
            err_code = "recipient_invalid"

        if err_code == "rate_limited":
            self._store.update_row(
                mid,
                status="queued",
                next_attempt_at=now + 10,
                updated_at=now,
            )
            return

        if rec is None:
            self._fail(mid, err_code or "recipient_not_found", "resolution failed", now)
            return

        defer = self._limiter.defer_seconds(rec.bale_user_id)
        if defer > 0:
            self._store.update_row(
                mid,
                status="queued",
                bale_user_id=rec.bale_user_id,
                recipient_masked=rec.masked,
                next_attempt_at=now + defer,
                updated_at=now,
            )
            return

        text = row["text"]
        logger.info(
            "sending message_id=%s len=%d hash=%s",
            mid,
            len(text),
            text_log_fingerprint(text),
        )

        if self._settings.send_mode == "resolve_only":
            self._store.finalize_terminal(
                mid,
                status="sent",
                bale_user_id=rec.bale_user_id,
                recipient_masked=rec.masked,
                sent_at=now,
                updated_at=now,
                recipient_secret=None,
                dry_run=0,
            )
            self._limiter.record_send(rec.bale_user_id)
            self._store.record_bale_success()
            return

        self._store.mark_sending(mid, now)
        sender = self._get_sender()
        outcome = await sender.send_private(rec.bale_user_id, text)
        now = self._clock()

        if outcome.error_code:
            await self._handle_send_error(mid, row, outcome, now)
            return

        self._store.finalize_terminal(
            mid,
            status="sent",
            bale_user_id=rec.bale_user_id,
            bale_message_id=outcome.bale_message_id,
            recipient_masked=rec.masked,
            sent_at=now,
            updated_at=now,
            recipient_secret=None,
            dry_run=1 if outcome.dry_run else 0,
            error_code=None,
            error_message=None,
        )
        self._limiter.record_send(rec.bale_user_id)
        self._store.record_bale_success()

    async def _handle_send_error(self, mid: str, row: dict, outcome: Any, now: float) -> None:
        msg = outcome.error_message or ""
        is_session = "session" in msg.lower() or "auth" in msg.lower() or "token" in msg.lower()
        self._store.record_bale_error(is_session, self._settings.breaker_errors)
        attempts = int(row["attempts"]) + 1
        transient = not is_session and attempts < MAX_ATTEMPTS
        if transient:
            backoff = min(300, (2 ** attempts) + random.uniform(0, 2))
            self._store.update_row(
                mid,
                status="queued",
                attempts=attempts,
                next_attempt_at=now + backoff,
                updated_at=now,
                error_code=outcome.error_code,
                error_message=msg[:500],
            )
            return
        code = "session_invalid" if is_session else (outcome.error_code or "bale_error")
        self._fail(mid, code, msg, now, attempts=attempts)

    def _fail(self, mid: str, code: str, message: str, now: float, attempts: Optional[int] = None) -> None:
        fields = {
            "status": "failed",
            "error_code": code,
            "error_message": message[:500],
            "updated_at": now,
            "recipient_secret": None,
        }
        if attempts is not None:
            fields["attempts"] = attempts
        self._store.finalize_terminal(mid, **fields)
