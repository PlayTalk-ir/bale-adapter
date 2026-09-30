"""Tests for panel-managed API bearer tokens."""

from __future__ import annotations

import pytest

from bale_platform.api.auth import token_valid
from bale_platform.api_token_store import (
    api_auth_configured,
    create_token,
    list_records,
    revoke_token,
    verification_sets,
)


def test_create_and_verify(tmp_path, monkeypatch):
    path = tmp_path / "api_tokens.json"
    monkeypatch.setenv("BALE_API_TOKENS_PATH", str(path))
    monkeypatch.delenv("BALE_ADAPTER_API_TOKENS", raising=False)

    plain, rec = create_token(label="Laravel", path=path)
    assert rec.prefix == plain[:8]
    assert len(list_records(path)) == 1
    assert api_auth_configured(path)

    _plain_env, hashes = verification_sets(path)
    assert token_valid(plain, [], hashes)
    assert not token_valid("wrong", [], hashes)

    assert revoke_token(rec.id, path=path)
    assert list_records(path) == []


def test_env_tokens_still_work(monkeypatch):
    monkeypatch.setenv("BALE_ADAPTER_API_TOKENS", "legacy-token")
    plain, _ = verification_sets()
    assert token_valid("legacy-token", plain, _)
