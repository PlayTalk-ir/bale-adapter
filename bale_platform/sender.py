"""Bale message send abstraction (live, dry_run, resolve_only)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from aiobale.enums import ChatType  # type: ignore[import-untyped]


@dataclass
class SendOutcome:
    bale_message_id: Optional[int]
    dry_run: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class BaleSender(Protocol):
    async def send_private(
        self, chat_id: int, text: str, *, random_id: Optional[int] = None
    ) -> SendOutcome: ...


class LiveBaleSender:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def send_private(
        self, chat_id: int, text: str, *, random_id: Optional[int] = None
    ) -> SendOutcome:
        kwargs: dict[str, Any] = {
            "text": text,
            "chat_id": chat_id,
            "chat_type": ChatType.PRIVATE,
        }
        if random_id is not None:
            kwargs["random_id"] = random_id
        try:
            msg = await self._client.send_message(**kwargs)
            mid = getattr(msg, "message_id", None)
            return SendOutcome(bale_message_id=int(mid) if mid is not None else None, dry_run=False)
        except Exception as exc:
            return SendOutcome(
                bale_message_id=None,
                dry_run=False,
                error_code="bale_error",
                error_message=str(exc),
            )


class DryRunBaleSender:
    async def send_private(
        self, chat_id: int, text: str, *, random_id: Optional[int] = None
    ) -> SendOutcome:
        digest = hashlib.sha256(f"{chat_id}:{text}".encode()).hexdigest()
        fake_id = int(digest[:12], 16) % (10**12)
        return SendOutcome(bale_message_id=fake_id, dry_run=True)


class ResolveOnlySender:
    async def send_private(
        self, chat_id: int, text: str, *, random_id: Optional[int] = None
    ) -> SendOutcome:
        return SendOutcome(bale_message_id=None, dry_run=False)


def make_sender(mode: str, client: Any) -> BaleSender:
    if mode == "dry_run":
        return DryRunBaleSender()
    if mode == "resolve_only":
        return ResolveOnlySender()
    return LiveBaleSender(client)
