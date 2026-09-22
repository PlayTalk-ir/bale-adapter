"""Outbound messaging: send to one or many recipients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from aiobale.enums import ChatType  # type: ignore[import-untyped]

from bale_platform.phone import normalize_phone_digits
from bale_platform.store import SupportStore


@dataclass
class SendResult:
    target: str
    chat_id: Optional[int]
    ok: bool
    detail: str


async def resolve_private_chat_id(client: Any, target: str) -> Optional[int]:
    """Resolve phone or numeric chat id to a private chat id."""
    target = target.strip()
    if target.isdigit() and len(target) <= 12:
        # Already a Bale user/chat id
        return int(target)
    phone = normalize_phone_digits(target)
    peer = await client.search_contact(phone)
    if peer is None:
        return None
    return int(getattr(peer, "id", 0) or 0)


async def send_to_targets(
    client: Any,
    targets: List[str],
    text: str,
    *,
    store: Optional[SupportStore] = None,
    dry_run: bool = False,
) -> List[SendResult]:
    if not text.strip():
        raise ValueError("message text cannot be empty")

    me = await client.get_me()
    my_id = str(getattr(me, "id", ""))
    results: List[SendResult] = []

    for target in targets:
        target = target.strip()
        if not target:
            continue
        try:
            chat_id = await resolve_private_chat_id(client, target)
            if not chat_id:
                results.append(
                    SendResult(target=target, chat_id=None, ok=False, detail="not found")
                )
                continue
            if dry_run:
                results.append(
                    SendResult(
                        target=target,
                        chat_id=chat_id,
                        ok=True,
                        detail="dry-run — not sent",
                    )
                )
                continue
            msg = await client.send_message(
                text=text,
                chat_id=chat_id,
                chat_type=ChatType.PRIVATE,
            )
            message_id = getattr(msg, "message_id", None)
            if store is not None and message_id is not None:
                store.upsert_message(
                    {
                        "chat_id": str(chat_id),
                        "message_id": message_id,
                        "sender_id": my_id,
                        "text": text,
                        "timestamp": "",
                        "date_ms": getattr(msg, "date", 0),
                    },
                    direction="out",
                )
            results.append(
                SendResult(target=target, chat_id=chat_id, ok=True, detail="sent")
            )
        except Exception as exc:
            results.append(
                SendResult(target=target, chat_id=None, ok=False, detail=str(exc))
            )
    return results
