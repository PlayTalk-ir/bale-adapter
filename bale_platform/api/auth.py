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


def token_valid(token: str, allowed: List[str]) -> bool:
    for candidate in allowed:
        if hmac.compare_digest(token, candidate):
            return True
    return False
