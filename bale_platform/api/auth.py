"""Bearer token authentication."""

from __future__ import annotations

import hmac
import hashlib
from typing import List, Optional


def extract_bearer(header: Optional[str]) -> Optional[str]:
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def token_valid(
    token: str,
    plaintext_tokens: List[str],
    hashed_tokens: Optional[List[str]] = None,
) -> bool:
    for candidate in plaintext_tokens:
        if hmac.compare_digest(token, candidate):
            return True
    if hashed_tokens:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for stored in hashed_tokens:
            if hmac.compare_digest(digest, stored):
                return True
    return False
