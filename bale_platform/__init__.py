"""bale_platform — Bale userbot adapter (Shape C) for Hermes Agent.

Uses `aiobale` (reverse-engineered Bale WebSocket client) to act as a logged-in
Bale USER account (the company's customer-support account) and:
    1. Observe every incoming message (groups + private chats + channels)
    2. Extract structured facts → KB (kb/learned_facts.mdl)
    3. NEVER persist raw message text (privacy / compliance)

This is a SKELETON — `aiobale` is the production library choice but its API
surface is reverse-engineered and may break. The login flow is interactive
(phone + OTP, one-time); the session file persists across restarts as
opaque protobuf bytes that aiobale writes itself.

SECURITY:
    - Login happens ONLY via scripts/login.py on the VPS console.
    - OTP is typed by the operator; it never enters this chat, this code,
      or any log.
    - The session file is mode 0600, owned by the service user.
"""

from .config import BaleUserbotConfig, is_configured
from .adapter import BaleUserbotAdapter

__all__ = [
    "BaleUserbotAdapter",
    "BaleUserbotConfig",
    "is_configured",
]
