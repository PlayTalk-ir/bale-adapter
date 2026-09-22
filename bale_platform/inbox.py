"""Inbox operations: list dialogs, sync history, per-agent unread."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from aiobale.enums import ChatType  # type: ignore[import-untyped]
from aiobale.types.peer import PeerType  # type: ignore[import-untyped]

from bale_platform.messages import extract_text, format_timestamp, normalize_message
from bale_platform.store import SupportStore, StoredMessage


@dataclass
class DialogSummary:
    chat_id: str
    chat_type: str
    label: str
    unread_count: int
    last_message: str
    last_timestamp: str
    sender_id: int


async def list_dialogs(
    client: Any, *, limit: int = 40, private_only: bool = False
) -> List[DialogSummary]:
    dialogs = await client.load_dialogs(limit=limit)
    out: List[DialogSummary] = []
    for d in dialogs:
        peer = d.peer
        peer_type = PeerType(getattr(peer, "type", 0))
        if private_only and peer_type != PeerType.PRIVATE:
            continue
        label = str(peer.id)
        if peer_type == PeerType.PRIVATE:
            try:
                u = await client.load_user(chat_id=peer.id, chat_type=ChatType.PRIVATE)
                label = (
                    getattr(u, "local_name", None)
                    or getattr(u, "name", None)
                    or label
                )
            except Exception:
                pass
        out.append(
            DialogSummary(
                chat_id=str(peer.id),
                chat_type=str(peer_type.name if hasattr(peer_type, "name") else peer_type),
                label=str(label),
                unread_count=int(getattr(d, "unread_count", 0) or 0),
                last_message=extract_text(getattr(d, "content", None))[:200],
                last_timestamp=format_timestamp(getattr(d, "date", 0)),
                sender_id=int(getattr(d, "sender_id", 0) or 0),
            )
        )
    return out


async def sync_dialog_history(
    client: Any,
    store: SupportStore,
    *,
    dialog_limit: int = 40,
    history_limit: int = 30,
    private_only: bool = True,
    account_user_id: Optional[str] = None,
) -> int:
    """Pull recent history into the store for FAQ/analysis/per-agent unread."""
    me = await client.get_me()
    my_id = str(getattr(me, "id", account_user_id or ""))
    dialogs = await list_dialogs(client, limit=dialog_limit, private_only=private_only)
    saved = 0
    for d in dialogs:
        chat_type = ChatType.PRIVATE if private_only else ChatType.PRIVATE
        try:
            msgs = await client.load_history(
                chat_id=int(d.chat_id),
                chat_type=chat_type,
                limit=history_limit,
            )
            if not isinstance(msgs, list):
                msgs = msgs.data
        except Exception:
            continue
        for m in msgs:
            norm = normalize_message(m)
            direction = "out" if str(norm["sender_id"]) == my_id else "in"
            store.upsert_message(norm, direction=direction)
            saved += 1
    return saved


def agent_unread(
    store: SupportStore,
    agent_id: str,
    *,
    account_user_id: Optional[str] = None,
) -> List[StoredMessage]:
    return store.unread_for_agent(agent_id, account_user_id=account_user_id)


def account_unread_dialogs(dialogs: List[DialogSummary]) -> List[DialogSummary]:
    return [d for d in dialogs if d.unread_count > 0]
