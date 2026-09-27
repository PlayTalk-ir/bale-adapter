"""HTTP API and outbox configuration from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name, "")
    if not v:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    v = os.getenv(name, "")
    if not v:
        return default
    return int(v)


def _float(name: str, default: float) -> float:
    v = os.getenv(name, "")
    if not v:
        return default
    return float(v)


@dataclass
class ApiSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8787
    tokens: List[str] = None  # type: ignore[assignment]
    rate_per_min: int = 60
    queue_max: int = 500
    default_ttl_s: int = 86400
    max_ttl_s: int = 7 * 86400
    record_in_inbox: bool = False
    phone_pepper: str = ""

    outbox_path: Path = Path("data/outbox.sqlite")
    send_mode: str = "live"
    sending_paused: bool = False

    send_min_interval_s: float = 8.0
    send_jitter_s: float = 7.0
    send_max_per_hour: int = 120
    send_max_per_day: int = 600
    recipient_min_interval_s: float = 60.0
    recipient_max_per_hour: int = 5
    recipient_max_per_day: int = 15
    new_peer_max_per_day: int = 50
    lookup_min_interval_s: float = 5.0
    allow_contact_import: bool = False
    quiet_hours: Optional[str] = None
    breaker_errors: int = 3

    @classmethod
    def from_env(cls) -> "ApiSettings":
        tokens = [s.strip() for s in os.getenv("BALE_ADAPTER_API_TOKENS", "").split(",") if s.strip()]
        return cls(
            enabled=_bool("BALE_API_ENABLED", False),
            host=os.getenv("BALE_API_HOST", "127.0.0.1"),
            port=_int("BALE_API_PORT", 8787),
            tokens=tokens,
            rate_per_min=_int("BALE_API_RATE_PER_MIN", 60),
            queue_max=_int("BALE_QUEUE_MAX", 500),
            default_ttl_s=_int("BALE_DEFAULT_TTL_S", 86400),
            max_ttl_s=7 * 86400,
            record_in_inbox=_bool("BALE_API_RECORD_IN_INBOX", False),
            phone_pepper=os.getenv("BALE_PHONE_PEPPER", ""),
            outbox_path=Path(os.getenv("BALE_OUTBOX_PATH", "data/outbox.sqlite")),
            send_mode=os.getenv("BALE_SEND_MODE", "live").strip().lower(),
            sending_paused=_bool("BALE_SENDING_PAUSED", False),
            send_min_interval_s=_float("BALE_SEND_MIN_INTERVAL_S", 8.0),
            send_jitter_s=_float("BALE_SEND_JITTER_S", 7.0),
            send_max_per_hour=_int("BALE_SEND_MAX_PER_HOUR", 120),
            send_max_per_day=_int("BALE_SEND_MAX_PER_DAY", 600),
            recipient_min_interval_s=_float("BALE_RECIPIENT_MIN_INTERVAL_S", 60.0),
            recipient_max_per_hour=_int("BALE_RECIPIENT_MAX_PER_HOUR", 5),
            recipient_max_per_day=_int("BALE_RECIPIENT_MAX_PER_DAY", 15),
            new_peer_max_per_day=_int("BALE_NEW_PEER_MAX_PER_DAY", 50),
            lookup_min_interval_s=_float("BALE_LOOKUP_MIN_INTERVAL_S", 5.0),
            allow_contact_import=_bool("BALE_ALLOW_CONTACT_IMPORT", False),
            quiet_hours=os.getenv("BALE_QUIET_HOURS") or None,
            breaker_errors=_int("BALE_BREAKER_ERRORS", 3),
        )

    def validate_startup(self) -> None:
        if self.enabled and not self.tokens:
            raise RuntimeError(
                "BALE_API_ENABLED=true but BALE_ADAPTER_API_TOKENS is empty — "
                "refusing to start API without auth tokens."
            )
        if self.send_mode not in ("live", "dry_run", "resolve_only"):
            raise ValueError(f"invalid BALE_SEND_MODE: {self.send_mode}")
