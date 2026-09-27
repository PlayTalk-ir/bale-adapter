"""Outbox store and worker tests."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from bale_platform.api_config import ApiSettings
from bale_platform.outbox.rate_limit import RateLimitConfig, SendRateLimiter
from bale_platform.outbox.store import OutboxStore
from bale_platform.outbox.worker import OutboxWorker
from bale_platform.resolver import RecipientResolver
from bale_platform.sender import DryRunBaleSender
from tests.fake_bale import FakeBaleClient


class FixedClock:
    def __init__(self, start: float = 1_000_000.0):
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _insert_queued(store: OutboxStore, clock: FixedClock, **kwargs):
    defaults = {
        "message_id": "01JTEST0000000000000000000",
        "idempotency_key": "idem-1",
        "payload_hash": "abc",
        "text": "hello",
        "meta": None,
        "recipient_type": "bale_user_id",
        "recipient_masked": "42",
        "recipient_secret": json.dumps({"type": "bale_user_id", "bale_user_id": "42"}),
        "expires_at": clock.now() + 3600,
        "now": clock.now(),
    }
    defaults.update(kwargs)
    store.insert_message(**defaults)


@pytest.mark.asyncio
async def test_outbox_persists_and_claim_atomic(tmp_path):
    path = tmp_path / "outbox.sqlite"
    clock = FixedClock()
    s1 = OutboxStore(path)
    _insert_queued(s1, clock, message_id="m1", idempotency_key="k1")
    s1.close()
    s2 = OutboxStore(path)
    row = s2.claim_next(clock.now())
    assert row["message_id"] == "m1"
    assert row["status"] == "resolving"
    assert s2.claim_next(clock.now()) is None


@pytest.mark.asyncio
async def test_worker_dry_run_zero_sends(tmp_path):
    clock = FixedClock()
    store = OutboxStore(tmp_path / "o.sqlite")
    client = FakeBaleClient()
    settings = ApiSettings(
        enabled=True,
        tokens=["t"],
        outbox_path=tmp_path / "o.sqlite",
        send_mode="dry_run",
        phone_pepper="p",
    )
    _insert_queued(store, clock)
    worker = OutboxWorker(
        store,
        settings,
        get_client=lambda: client,
        get_sender=lambda: DryRunBaleSender(),
        get_resolver=lambda: RecipientResolver(client, store, phone_pepper="p"),
        sending_paused=lambda: False,
        clock=clock.now,
        sleep=lambda s: asyncio.sleep(0),
    )
    task = worker.start()
    for _ in range(50):
        row = store.get_by_message_id("01JTEST0000000000000000000")
        if row and row["status"] == "sent":
            break
        clock.advance(0.05)
        await asyncio.sleep(0.01)
    await worker.stop()
    assert client.send_calls == []
    row = store.get_by_message_id("01JTEST0000000000000000000")
    assert row["status"] == "sent"
    assert row["dry_run"] == 1


@pytest.mark.asyncio
async def test_worker_retry_then_success(tmp_path):
    clock = FixedClock()
    store = OutboxStore(tmp_path / "o.sqlite")
    client = FakeBaleClient()
    client.errors["send_message"] = RuntimeError("network blip")
    settings = ApiSettings(enabled=True, tokens=["t"], outbox_path=tmp_path / "o.sqlite", send_mode="live", phone_pepper="p")

    from bale_platform.sender import LiveBaleSender

    _insert_queued(store, clock, message_id="m2", idempotency_key="k2")
    worker = OutboxWorker(
        store,
        settings,
        get_client=lambda: client,
        get_sender=lambda: LiveBaleSender(client),
        get_resolver=lambda: RecipientResolver(client, store, phone_pepper="p"),
        sending_paused=lambda: False,
        clock=clock.now,
        sleep=lambda s: asyncio.sleep(0),
    )
    worker.start()
    await asyncio.sleep(0.05)
    del client.errors["send_message"]
    for _ in range(100):
        row = store.get_by_message_id("m2")
        if row and row["status"] == "sent":
            break
        clock.advance(5)
        await asyncio.sleep(0.01)
    await worker.stop()
    assert row["status"] == "sent"


@pytest.mark.asyncio
async def test_breaker_trips_on_session_error(tmp_path):
    clock = FixedClock()
    store = OutboxStore(tmp_path / "o.sqlite")
    client = FakeBaleClient()
    client.errors["send_message"] = RuntimeError("session invalid token")
    settings = ApiSettings(
        enabled=True,
        tokens=["t"],
        outbox_path=tmp_path / "o.sqlite",
        send_mode="live",
        phone_pepper="p",
        breaker_errors=3,
    )
    from bale_platform.sender import LiveBaleSender

    _insert_queued(store, clock, message_id="m3", idempotency_key="k3")
    worker = OutboxWorker(
        store,
        settings,
        get_client=lambda: client,
        get_sender=lambda: LiveBaleSender(client),
        get_resolver=lambda: RecipientResolver(client, store, phone_pepper="p"),
        sending_paused=lambda: False,
        clock=clock.now,
        sleep=lambda s: asyncio.sleep(0),
    )
    worker.start()
    await asyncio.sleep(0.1)
    await worker.stop()
    assert store.breaker_open()


@pytest.mark.asyncio
async def test_ttl_expiry(tmp_path):
    clock = FixedClock()
    store = OutboxStore(tmp_path / "o.sqlite")
    _insert_queued(
        store,
        clock,
        message_id="mx",
        idempotency_key="kx",
        expires_at=clock.now() - 1,
    )
    store.expire_due(clock.now())
    row = store.get_by_message_id("mx")
    assert row["status"] == "expired"


@pytest.mark.asyncio
async def test_restart_delivery_unknown(tmp_path):
    path = tmp_path / "o.sqlite"
    store = OutboxStore(path)
    now = time.time()
    store.insert_message(
        message_id="stuck",
        idempotency_key="ks",
        payload_hash="h",
        text="t",
        meta=None,
        recipient_type="bale_user_id",
        recipient_masked="1",
        recipient_secret=json.dumps({"type": "bale_user_id", "bale_user_id": "1"}),
        expires_at=now + 999,
        now=now,
    )
    store.update_row("stuck", status="sending")
    store.close()
    store2 = OutboxStore(path)
    n = store2.recover_stuck_sending()
    assert n == 1
    assert store2.get_by_message_id("stuck")["status"] == "delivery_unknown"


def test_quiet_hours_defer(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    clock = FixedClock()
    clock.t = datetime(2026, 1, 15, 23, 0, tzinfo=ZoneInfo("Asia/Tehran")).timestamp()
    store = OutboxStore(tmp_path / "qh.sqlite")
    lim = SendRateLimiter(
        store,
        RateLimitConfig(quiet_hours="22:00-07:00"),
        clock.now,
    )
    assert lim.defer_seconds(1) > 0


def test_rate_limit_global_interval(tmp_path):
    clock = FixedClock()
    store = OutboxStore(tmp_path / "o.sqlite")
    store.record_send("global", "global", clock.now())
    lim = SendRateLimiter(
        store,
        RateLimitConfig(send_min_interval_s=8.0, send_jitter_s=0),
        clock.now,
    )
    assert lim.defer_seconds(42) > 0
    clock.advance(9)
    assert lim.defer_seconds(42) == 0


def test_phone_resolver_cache_no_import(tmp_path):
    client = FakeBaleClient()
    client.contacts["989924466793"] = 555
    store = OutboxStore(tmp_path / "o.sqlite")
    clock = FixedClock()
    r = RecipientResolver(client, store, phone_pepper="pep", clock=clock.now)

    async def run():
        a, e1 = await r.resolve_phone("09924466793")
        b, e2 = await r.resolve_phone("09924466793")
        assert a and a.bale_user_id == 555
        assert b and b.bale_user_id == 555
        assert len(client.search_contact_calls) == 1

    asyncio.run(run())
