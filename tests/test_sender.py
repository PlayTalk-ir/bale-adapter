"""LiveBaleSender matches aiobale-py 0.3.8 send_message kwargs."""

from __future__ import annotations

import pytest

from bale_platform.sender import LiveBaleSender
from tests.fake_bale import FakeBaleClient


@pytest.mark.asyncio
async def test_live_sender_passes_message_id_kwarg():
    client = FakeBaleClient()
    sender = LiveBaleSender(client)
    await sender.send_private(42, "hi", message_id=12345)
    assert client.send_calls[0]["message_id"] == 12345
    assert "random_id" not in client.send_calls[0]
