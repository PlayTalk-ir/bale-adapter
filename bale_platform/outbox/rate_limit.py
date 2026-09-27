"""Send rate limiting with injectable clock."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from bale_platform.outbox.store import OutboxStore


@dataclass
class RateLimitConfig:
    send_min_interval_s: float = 8.0
    send_jitter_s: float = 7.0
    send_max_per_hour: int = 120
    send_max_per_day: int = 600
    recipient_min_interval_s: float = 60.0
    recipient_max_per_hour: int = 5
    recipient_max_per_day: int = 15
    quiet_hours: Optional[str] = None  # e.g. "22:00-07:00"


class SendRateLimiter:
    def __init__(
        self,
        store: OutboxStore,
        cfg: RateLimitConfig,
        clock: Callable[[], float],
        rng: Optional[random.Random] = None,
    ) -> None:
        self._store = store
        self._cfg = cfg
        self._clock = clock
        self._rng = rng or random.Random()

    def _in_quiet_hours(self, now: float) -> bool:
        qh = self._cfg.quiet_hours
        if not qh:
            return False
        try:
            start_s, end_s = qh.split("-", 1)
            sh, sm = map(int, start_s.strip().split(":"))
            eh, em = map(int, end_s.strip().split(":"))
        except (ValueError, AttributeError):
            return False
        tz = ZoneInfo("Asia/Tehran")
        dt = datetime.fromtimestamp(now, tz=tz)
        minutes = dt.hour * 60 + dt.minute
        start_m = sh * 60 + sm
        end_m = eh * 60 + em
        if start_m <= end_m:
            return start_m <= minutes < end_m
        return minutes >= start_m or minutes < end_m

    def defer_seconds(self, bale_user_id: int) -> float:
        """Seconds to wait before send; 0 if allowed now."""
        now = self._clock()
        if self._in_quiet_hours(now):
            return 60.0

        global_key = "global"
        last = self._store.last_send_ts("global", global_key)
        if last is not None:
            wait = self._cfg.send_min_interval_s + self._rng.uniform(0, self._cfg.send_jitter_s)
            gap = now - last
            if gap < wait:
                return wait - gap

        if self._store.count_sends("global", global_key, now - 3600) >= self._cfg.send_max_per_hour:
            return 30.0
        if self._store.count_sends("global", global_key, now - 86400) >= self._cfg.send_max_per_day:
            return 120.0

        rkey = str(bale_user_id)
        last_r = self._store.last_send_ts("recipient", rkey)
        if last_r is not None and now - last_r < self._cfg.recipient_min_interval_s:
            return self._cfg.recipient_min_interval_s - (now - last_r)
        if self._store.count_sends("recipient", rkey, now - 3600) >= self._cfg.recipient_max_per_hour:
            return 45.0
        if self._store.count_sends("recipient", rkey, now - 86400) >= self._cfg.recipient_max_per_day:
            return 180.0
        return 0.0

    def record_send(self, bale_user_id: int) -> None:
        now = self._clock()
        self._store.record_send("global", "global", now)
        self._store.record_send("recipient", str(bale_user_id), now)
