"""Outbound messaging: send to one or many recipients.

A target may be:

* a numeric Bale chat id   ``1858791866``
* a phone number           ``09924466793`` / ``989924466793`` / ``+98992…``
* a saved contact name     ``نفس پیروز`` / ``امیرحافظ`` / ``@username``

Names are resolved through :class:`bale_platform.contacts.ContactIndex`.
Ambiguous names are reported as a failure (with the candidate chat ids)
instead of being guessed — the adapter must never message the wrong customer.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

from bale_platform.contacts import (
    ContactIndex,
    NameLookupError,
    SavedContact,
)
from bale_platform.phone import normalize_phone_digits, to_ascii_digits
from bale_platform.store import SupportStore

TARGET_CHAT_ID = "chat_id"
TARGET_PHONE = "phone"
TARGET_NAME = "name"

_DIGITS_RE = re.compile(r"^\d+$")


def _private_chat_type() -> Any:
    """aiobale ``ChatType.PRIVATE`` — imported lazily (git-only dependency)."""
    from aiobale.enums import ChatType  # type: ignore[import-untyped]

    return ChatType.PRIVATE


@dataclass
class ResolvedTarget:
    """Result of turning one typed target into a concrete chat id."""

    target: str
    kind: str
    chat_id: Optional[int] = None
    matched_name: str = ""
    error: str = ""


@dataclass
class SendResult:
    target: str
    chat_id: Optional[int]
    ok: bool
    detail: str
    matched_name: str = ""
    kind: str = ""


def classify_target(raw: Any) -> str:
    """Guess what a target string is: ``chat_id``, ``phone`` or ``name``.

    Phone patterns win over bare digit strings, because an 11-digit ``09…``
    value is a mobile number — NOT a chat id. Everything non-numeric is a name.
    """
    text = str(raw or "").strip()
    if not text:
        return TARGET_NAME
    if text.startswith("+"):
        return TARGET_PHONE
    digits = (
        to_ascii_digits(text)
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    if not _DIGITS_RE.match(digits):
        return TARGET_NAME
    if len(digits) == 11 and digits.startswith("0"):
        return TARGET_PHONE
    if len(digits) == 12 and digits.startswith("98"):
        return TARGET_PHONE
    if len(digits) <= 12:
        return TARGET_CHAT_ID
    return TARGET_PHONE


async def resolve_target(
    client: Any,
    target: Any,
    *,
    index: Optional[ContactIndex] = None,
) -> ResolvedTarget:
    """Resolve a typed target to a chat id without sending anything."""
    text = str(target or "").strip()
    kind = classify_target(text)

    if kind == TARGET_CHAT_ID:
        digits = to_ascii_digits(text).replace(" ", "").replace("-", "")
        return ResolvedTarget(target=text, kind=kind, chat_id=int(digits))

    if kind == TARGET_PHONE:
        try:
            phone = normalize_phone_digits(text)
        except ValueError as exc:
            return ResolvedTarget(target=text, kind=kind, error=str(exc))
        try:
            peer = await client.search_contact(phone)
        except Exception as exc:  # network / API failure — report, don't crash
            return ResolvedTarget(target=text, kind=kind, error=f"lookup failed: {exc}")
        chat_id = int(getattr(peer, "id", 0) or 0) if peer is not None else 0
        if not chat_id:
            return ResolvedTarget(
                target=text, kind=kind, error=f"phone {phone} not found on Bale"
            )
        return ResolvedTarget(target=text, kind=kind, chat_id=chat_id)

    if index is None:
        return ResolvedTarget(
            target=text,
            kind=kind,
            error="name given but no contact index was loaded",
        )
    try:
        contact: SavedContact = index.resolve(text)
    except NameLookupError as exc:
        return ResolvedTarget(target=text, kind=kind, error=str(exc))
    return ResolvedTarget(
        target=text, kind=kind, chat_id=contact.chat_id, matched_name=contact.name
    )


async def resolve_private_chat_id(
    client: Any,
    target: Any,
    *,
    index: Optional[ContactIndex] = None,
) -> Optional[int]:
    """Backwards-compatible helper: chat id, or ``None`` when unresolvable."""
    resolved = await resolve_target(client, target, index=index)
    return resolved.chat_id



async def send_to_targets(
    client: Any,
    targets: Sequence[str],
    text: str,
    *,
    store: Optional[SupportStore] = None,
    dry_run: bool = False,
    index: Optional[ContactIndex] = None,
    delay: float = 0.0,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> List[SendResult]:
    """Send ``text`` to every target, resolving phones and saved names.

    Args:
        index: contact index for name targets (see ``contacts.build_contact_index``).
        delay: seconds to wait between real sends (aiobale is unofficial — be
            polite). Ignored for ``dry_run``.
        on_progress: ``(position, total, target)`` callback for CLI progress.
    """
    if not text.strip():
        raise ValueError("message text cannot be empty")

    me = await client.get_me()
    my_id = str(getattr(me, "id", ""))
    results: List[SendResult] = []
    total = len(targets)

    for position, raw in enumerate(targets, start=1):
        target = str(raw or "").strip()
        if not target:
            continue
        if delay and not dry_run and results:
            await asyncio.sleep(delay)
        if on_progress is not None:
            on_progress(position, total, target)

        try:
            resolved = await resolve_target(client, target, index=index)
            if resolved.error or not resolved.chat_id:
                results.append(
                    SendResult(
                        target=target,
                        chat_id=resolved.chat_id,
                        ok=False,
                        detail=resolved.error or "not found",
                        matched_name=resolved.matched_name,
                        kind=resolved.kind,
                    )
                )
                continue

            if dry_run:
                detail = "dry-run — not sent"
                if resolved.matched_name:
                    detail += f" (matches {resolved.matched_name})"
                results.append(
                    SendResult(
                        target=target,
                        chat_id=resolved.chat_id,
                        ok=True,
                        detail=detail,
                        matched_name=resolved.matched_name,
                        kind=resolved.kind,
                    )
                )
                continue

            msg = await client.send_message(
                text=text,
                chat_id=resolved.chat_id,
                chat_type=_private_chat_type(),
            )
            message_id = getattr(msg, "message_id", None)
            if message_id is None and isinstance(msg, list) and msg:
                message_id = getattr(msg[0], "message_id", None)
            if store is not None and message_id is not None:
                store.upsert_message(
                    {
                        "chat_id": str(resolved.chat_id),
                        "message_id": message_id,
                        "sender_id": my_id,
                        "text": text,
                        "timestamp": "",
                        "date_ms": getattr(msg, "date", 0),
                    },
                    direction="out",
                )
            detail = f"sent to {resolved.matched_name}" if resolved.matched_name else "sent"
            results.append(
                SendResult(
                    target=target,
                    chat_id=resolved.chat_id,
                    ok=True,
                    detail=detail,
                    matched_name=resolved.matched_name,
                    kind=resolved.kind,
                )
            )
        except Exception as exc:
            results.append(
                SendResult(
                    target=target,
                    chat_id=None,
                    ok=False,
                    detail=str(exc),
                    kind=classify_target(target),
                )
            )
    return results

