"""Recipient resolution with HMAC-keyed phone cache."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from bale_platform.phone import (
    looks_like_phone_target,
    mask_phone,
    try_normalize_iranian_mobile,
)


@dataclass
class ResolvedRecipient:
    bale_user_id: int
    recipient_type: str  # phone | bale_user_id | username
    masked: str


class RecipientResolver:
    def __init__(
        self,
        client: Any,
        outbox_store: Any,
        *,
        phone_pepper: str,
        allow_contact_import: bool = False,
        new_peer_max_per_day: int = 50,
        lookup_min_interval_s: float = 5.0,
        clock: Optional[Any] = None,
    ) -> None:
        self._client = client
        self._store = outbox_store
        self._pepper = phone_pepper or "dev-pepper"
        self._allow_import = allow_contact_import
        self._new_peer_max = new_peer_max_per_day
        self._lookup_min_interval = lookup_min_interval_s
        self._clock = clock or time.time

    def _phone_key(self, normalized_phone: str) -> str:
        return hmac.new(
            self._pepper.encode(),
            normalized_phone.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def resolve_phone(self, raw: str) -> tuple[Optional[ResolvedRecipient], Optional[str]]:
        normalized = try_normalize_iranian_mobile(raw)
        if not normalized:
            return None, "recipient_invalid"
        cache_key = f"phone:{self._phone_key(normalized)}"
        hit = self._store.get_peer_cache(cache_key)
        if hit is not None:
            if hit.get("miss"):
                return None, hit.get("error_code") or "recipient_not_on_bale"
            uid = hit.get("bale_user_id")
            if uid:
                return (
                    ResolvedRecipient(
                        int(uid),
                        "phone",
                        mask_phone(normalized),
                    ),
                    None,
                )
        if not self._store.can_new_peer_lookup(self._new_peer_max, self._clock()):
            return None, "rate_limited"
        if not self._store.try_acquire_lookup_slot(self._lookup_min_interval, self._clock()):
            return None, "rate_limited"
        peer = await self._client.search_contact(normalized)
        if peer is None:
            self._store.set_peer_cache(
                cache_key,
                miss=True,
                error_code="recipient_not_on_bale",
                ttl_seconds=86400,
            )
            return None, "recipient_not_on_bale"
        uid = int(getattr(peer, "id", 0) or 0)
        if not uid:
            self._store.set_peer_cache(
                cache_key, miss=True, error_code="recipient_not_found", ttl_seconds=86400
            )
            return None, "recipient_not_found"
        self._store.set_peer_cache(
            cache_key, miss=False, bale_user_id=uid, ttl_seconds=30 * 86400
        )
        self._store.record_new_peer_lookup(self._clock())
        return ResolvedRecipient(uid, "phone", mask_phone(normalized)), None

    async def resolve_username(self, username: str) -> tuple[Optional[ResolvedRecipient], Optional[str]]:
        u = username.strip().lstrip("@")
        if not u:
            return None, "recipient_invalid"
        cache_key = f"username:{u.lower()}"
        hit = self._store.get_peer_cache(cache_key)
        if hit is not None:
            if hit.get("miss"):
                return None, hit.get("error_code") or "recipient_not_found"
            uid = hit.get("bale_user_id")
            if uid:
                return ResolvedRecipient(int(uid), "username", f"@{u[:2]}***"), None
        if not self._store.can_new_peer_lookup(self._new_peer_max, self._clock()):
            return None, "rate_limited"
        if not self._store.try_acquire_lookup_slot(self._lookup_min_interval, self._clock()):
            return None, "rate_limited"
        # aiobale-py 0.3.8: Client.search_username -> ContactResponse (.user / .group)
        search_username = getattr(self._client, "search_username", None)
        if search_username is None:
            return None, "bale_error"
        result = await search_username(u)
        peer = getattr(result, "user", None)
        if peer is None:
            self._store.set_peer_cache(
                cache_key, miss=True, error_code="recipient_not_found", ttl_seconds=86400
            )
            return None, "recipient_not_found"
        uid = int(getattr(peer, "id", 0) or 0)
        self._store.set_peer_cache(
            cache_key, miss=False, bale_user_id=uid, ttl_seconds=30 * 86400
        )
        self._store.record_new_peer_lookup(self._clock())
        masked = f"@{u[:2]}***" if len(u) > 2 else "@***"
        return ResolvedRecipient(uid, "username", masked), None

    async def resolve_bale_user_id(self, raw: str) -> tuple[Optional[ResolvedRecipient], Optional[str]]:
        if not raw.isdigit():
            return None, "recipient_invalid"
        uid = int(raw)
        return ResolvedRecipient(uid, "bale_user_id", str(uid)), None

    async def resolve_target_string(self, target: str) -> tuple[Optional[ResolvedRecipient], Optional[str]]:
        """CLI/outbound: phone, username, or numeric id."""
        target = target.strip()
        if not target:
            return None, "recipient_invalid"
        if target.startswith("@") or (not target.isdigit()):
            if looks_like_phone_target(target):
                return await self.resolve_phone(target)
            return await self.resolve_username(target)
        if looks_like_phone_target(target):
            return await self.resolve_phone(target)
        return await self.resolve_bale_user_id(target)


async def resolve_private_chat_id(client: Any, target: str, resolver: RecipientResolver) -> Optional[int]:
    """Resolve phone or Bale user id to a private chat id (shared with outbound CLI)."""
    rec, err = await resolver.resolve_target_string(target)
    if err or rec is None:
        return None
    return rec.bale_user_id
