"""Shared message parsing helpers for Bale content objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def extract_text(content: Any) -> str:
    if content is None:
        return ""
    t = getattr(content, "text", None)
    if t is not None and isinstance(getattr(t, "value", None), str):
        return t.value
    val = getattr(content, "value", None)
    if isinstance(val, str):
        return val
    cap = getattr(content, "caption", None)
    if cap is not None and isinstance(getattr(cap, "content", None), str):
        return cap.content
    doc = getattr(content, "document", None)
    if doc is not None:
        cap = getattr(doc, "caption", None)
        if cap is not None and isinstance(getattr(cap, "content", None), str):
            return cap.content
    return ""


def format_timestamp(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M"
        )
    except Exception:
        return str(ms)


def normalize_message(m: Any, *, sender_username: Optional[str] = None) -> Dict[str, Any]:
    chat = getattr(m, "chat", None) or {}
    chat_id = str(getattr(chat, "id", ""))
    chat_type = getattr(chat, "type", None)
    sender_id = str(getattr(m, "sender_id", "") or "")
    text = extract_text(getattr(m, "content", None))
    message_id = getattr(m, "message_id", None)
    date_ms = getattr(m, "date", 0)

    return {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": str(chat_type) if chat_type is not None else "",
        "sender_id": sender_id,
        "sender_username": sender_username,
        "text": text,
        "date_ms": date_ms,
        "timestamp": format_timestamp(date_ms),
    }
