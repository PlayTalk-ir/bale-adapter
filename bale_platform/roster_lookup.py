"""Bulk roster phone → Bale user id lookup (search_contact + cache)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from bale_platform.contact_store import ContactBook
from bale_platform.phone import panel_mobile_from_bale_digits, try_normalize_iranian_mobile
from bale_platform.resolver import RecipientResolver, ResolvedRecipient


async def _resolve_phone_paced(
    resolver: RecipientResolver,
    phone_in: str,
    *,
    max_wait_rounds: int = 12,
) -> Tuple[Optional[ResolvedRecipient], Optional[str]]:
    """Call resolve_phone; on rate_limited, sleep and retry (lookup slot is time-gated)."""
    interval = max(0.5, resolver.lookup_min_interval_s)
    for _ in range(max_wait_rounds):
        rec, err = await resolver.resolve_phone(phone_in)
        if err != "rate_limited":
            return rec, err
        await asyncio.sleep(interval + 0.25)
    return None, "rate_limited"


async def import_roster_contacts(
    resolver: RecipientResolver,
    items: List[Dict[str, Any]],
    book: Optional[ContactBook] = None,
    *,
    max_lookups: int = 25,
) -> Dict[str, Any]:
    """Resolve Iranian mobiles via :meth:`RecipientResolver.resolve_phone`.

    Each hit is written to the outbox phone map (inside the resolver) and,
    when ``book`` is set, ``phone_digits`` on the local contact book.
    """
    cap = max(1, min(int(max_lookups), 50))
    results: List[Dict[str, Any]] = []
    stats = {
        "processed": 0,
        "matched": 0,
        "not_on_bale": 0,
        "invalid": 0,
        "rate_limited": 0,
        "stopped_early": False,
        "lookup_min_interval_s": resolver.lookup_min_interval_s,
    }
    paced = False

    for raw in items:
        if stats["processed"] >= cap:
            stats["stopped_early"] = True
            break
        if paced:
            await asyncio.sleep(max(0.5, resolver.lookup_min_interval_s) + 0.25)
        phone_in = str(raw.get("phone") or "").strip()
        name = str(raw.get("name") or "").strip()
        normalized = try_normalize_iranian_mobile(phone_in)
        panel_phone = panel_mobile_from_bale_digits(normalized) if normalized else None
        if not normalized:
            stats["invalid"] += 1
            stats["processed"] += 1
            results.append(
                {
                    "phone": phone_in or None,
                    "panel_phone": None,
                    "chat_id": None,
                    "ok": False,
                    "error": "invalid",
                }
            )
            continue

        rec, err = await _resolve_phone_paced(resolver, phone_in)
        paced = True
        stats["processed"] += 1
        if err == "rate_limited":
            stats["rate_limited"] += 1
            results.append(
                {
                    "phone": panel_phone or phone_in,
                    "panel_phone": panel_phone,
                    "chat_id": None,
                    "ok": False,
                    "error": "rate_limited",
                }
            )
            stats["stopped_early"] = True
            break
        if err or rec is None:
            code = err or "lookup_failed"
            if code == "recipient_not_on_bale":
                stats["not_on_bale"] += 1
            else:
                stats["invalid"] += 1
            results.append(
                {
                    "phone": panel_phone or phone_in,
                    "panel_phone": panel_phone,
                    "chat_id": None,
                    "ok": False,
                    "error": code,
                }
            )
            continue

        stats["matched"] += 1
        if book is not None:
            book.set_phone_digits(rec.bale_user_id, normalized, display_name=name)
        results.append(
            {
                "phone": panel_phone or phone_in,
                "panel_phone": panel_phone,
                "chat_id": str(rec.bale_user_id),
                "ok": True,
                "error": None,
            }
        )

    return {"results": results, "stats": stats}
