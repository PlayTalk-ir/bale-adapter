"""Read ``kb/learned_facts.mdl`` for the HTTP API.

The file is append-only structured facts (``kb/learn.py``). This module does
not extract new facts and does not read the userbot session. Iranian mobile
numbers in fact values are masked the same way as outbox status payloads.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bale_platform.phone import looks_like_phone_target, mask_phone, try_normalize_iranian_mobile

_HEADER = re.compile(r"^## Extracted (?P<at>.+?) \| sender=(?P<sender>.*)$")
_ITEM = re.compile(r"^\s*\[(?P<category>[^\]]+)\]\s*(?P<value>.*)$")
_MAX_BYTES = 1_000_000


def read_facts(path: Path, *, query: str = "", limit: int = 50) -> dict[str, Any]:
    """Newest matching fact blocks, up to ``limit``. Missing file → empty list."""
    entries = _parse(path)
    needle = query.strip().casefold()
    if needle:
        entries = [entry for entry in entries if _matches(entry, needle)]
    entries.reverse()
    capped = max(0, int(limit))
    chosen = entries[:capped] if capped else []
    facts = [_public_entry(entry) for entry in chosen]
    return {"facts": facts, "count": len(facts)}


def _parse(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if len(raw) > _MAX_BYTES:
        raw = raw[-_MAX_BYTES:]
        newline = raw.find(b"\n")
        if newline != -1:
            raw = raw[newline + 1 :]
    text = raw.decode("utf-8", errors="replace")
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        header = _HEADER.match(line.strip())
        if header:
            if current and current["items"]:
                entries.append(current)
            current = {
                "extracted_at": header.group("at").strip(),
                "sender": header.group("sender").strip(),
                "items": [],
            }
            continue
        item = _ITEM.match(line)
        if item and current is not None:
            current["items"].append(
                {
                    "category": item.group("category").strip(),
                    "value": item.group("value").strip(),
                }
            )
    if current and current["items"]:
        entries.append(current)
    return entries


def _matches(entry: dict[str, Any], needle: str) -> bool:
    if needle in str(entry.get("sender") or "").casefold():
        return True
    for item in entry["items"]:
        if needle in item["category"].casefold() or needle in item["value"].casefold():
            return True
    return False


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "extracted_at": entry["extracted_at"],
        "sender": entry["sender"],
        "items": [
            {"category": item["category"], "value": _mask_value(item["category"], item["value"])}
            for item in entry["items"]
        ],
    }


def _mask_value(category: str, value: str) -> str:
    if category == "phone" or looks_like_phone_target(value):
        normalized = try_normalize_iranian_mobile(value)
        if normalized:
            return mask_phone(normalized)
        if category == "phone":
            return "***"
    return value
