"""Regression: 09… phones must not be treated as Bale chat ids."""

from __future__ import annotations

import asyncio

import pytest

from bale_platform.outbox.store import OutboxStore
from bale_platform.phone import looks_like_phone_target
from bale_platform.resolver import RecipientResolver, resolve_private_chat_id
from tests.fake_bale import FakeBaleClient


def test_looks_like_phone_for_09():
    assert looks_like_phone_target("09924466793") is True
    assert looks_like_phone_target("123456") is False


@pytest.mark.asyncio
async def test_resolve_username_uses_search_username_user_field(tmp_path):
    client = FakeBaleClient()
    client.usernames["playtalk"] = 888
    store = OutboxStore(tmp_path / "o.sqlite")
    resolver = RecipientResolver(client, store, phone_pepper="x")

    rec, err = await resolver.resolve_username("@playtalk")
    assert err is None
    assert rec is not None and rec.bale_user_id == 888
    assert client.search_username_calls == ["playtalk"]


@pytest.mark.asyncio
async def test_resolve_private_chat_id_calls_search_contact(tmp_path):
    client = FakeBaleClient()
    client.contacts["989924466793"] = 777
    store = OutboxStore(tmp_path / "o.sqlite")
    resolver = RecipientResolver(client, store, phone_pepper="x")
    chat_id = await resolve_private_chat_id(client, "09924466793", resolver)
    assert chat_id == 777
    assert client.search_contact_calls == ["989924466793"]
