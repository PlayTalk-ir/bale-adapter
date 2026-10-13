"""Outbox row → API JSON."""

from __future__ import annotations

import json
from typing import Any, Dict


def row_to_status(row: Dict[str, Any]) -> dict:
    err = None
    if row.get("error_code"):
        err = {"code": row["error_code"], "message": row.get("error_message") or ""}
    return {
        "message_id": row["message_id"],
        "idempotency_key": row["idempotency_key"],
        "status": row["status"],
        "mode": row.get("mode") or "send",
        "attempts": int(row["attempts"]),
        "recipient": {
            "type": row.get("recipient_type"),
            "masked": row.get("recipient_masked"),
        },
        "bale_user_id": row.get("bale_user_id"),
        "bale_message_id": row.get("bale_message_id"),
        "error": err,
        "dry_run": bool(row.get("dry_run")),
        "created_at": _iso(row.get("created_at")),
        "sent_at": _iso(row.get("sent_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def inbox_event(msg: Any, *, label: str = "", username: str = "") -> dict:
    """One support-inbox message as a feed event (see docs/api.md).

    ``chat`` describes the customer side of the private chat, whichever way the
    message went.
    """
    return {
        "seq": msg.seq,
        "chat_id": msg.chat_id,
        "message_id": msg.message_id,
        "direction": msg.direction,
        "kind": msg.kind,
        "text": msg.text,
        "date_ms": msg.date_ms,
        "sender_id": msg.sender_id,
        "chat": {"name": label, "username": username, "phone": None},
    }


def _iso(ts: Any) -> str | None:
    if ts is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
