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


MEDIA_PLACEHOLDERS = {
    "photo": "[عکس]",
    "video": "[ویدیو]",
    "voice": "[پیام صوتی]",
    "audio": "[فایل صوتی]",
    "file": "[فایل]",
    "sticker": "[استیکر]",
    "gift": "[هدیه]",
    "other": "[پیام پشتیبانی‌نشده]",
}


def message_kind(content: Any) -> str:
    """``text``, a media kind from :data:`MEDIA_PLACEHOLDERS`, ``service`` or ``empty``."""
    if content is None:
        return "empty"
    if getattr(content, "service_message", None) is not None:
        return "service"
    if getattr(content, "gift", None) is not None:
        return "gift"
    doc = getattr(content, "document", None)
    if doc is None and getattr(content, "mime_type", None) is not None:
        doc = content
    if doc is not None:
        mime = str(getattr(doc, "mime_type", "") or "").lower()
        ext = getattr(doc, "ext", None)
        if ext is not None and getattr(ext, "voice", None) is not None:
            return "voice"
        if mime.startswith("image/webp") or "sticker" in mime:
            return "sticker"
        if mime.startswith("image/"):
            return "photo"
        if mime.startswith("video/"):
            return "video"
        if mime in ("audio/ogg", "audio/opus") or "voice" in mime:
            return "voice"
        if mime.startswith("audio/"):
            return "audio"
        return "file"
    if extract_text(content):
        return "text"
    return "empty"


def display_text(text: str, kind: str) -> str:
    """Text to show for a message; media without caption gets a placeholder."""
    text = (text or "").strip()
    if kind in ("text", "empty", "service"):
        return text
    placeholder = MEDIA_PLACEHOLDERS.get(kind, MEDIA_PLACEHOLDERS["other"])
    return f"{placeholder} {text}" if text else placeholder


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
    content = getattr(m, "content", None)
    text = extract_text(content)
    message_id = getattr(m, "message_id", None)
    date_ms = getattr(m, "date", 0)

    return {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": str(chat_type) if chat_type is not None else "",
        "sender_id": sender_id,
        "sender_username": sender_username,
        "text": text,
        "kind": message_kind(content),
        "date_ms": date_ms,
        "timestamp": format_timestamp(date_ms),
    }
