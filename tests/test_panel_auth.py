"""Tests for panel auth: session cookies, CSRF tokens, operator token."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform import panel_auth

SECRET = "operator-secret-token"


class TestSessions:
    def test_roundtrip_valid(self):
        value = panel_auth.make_session(SECRET, ttl=60, now=1000.0)
        assert panel_auth.verify_session(SECRET, value, now=1001.0)

    def test_expired_rejected(self):
        value = panel_auth.make_session(SECRET, ttl=60, now=1000.0)
        assert not panel_auth.verify_session(SECRET, value, now=2000.0)

    def test_tampered_signature_rejected(self):
        value = panel_auth.make_session(SECRET, ttl=60, now=1000.0)
        expires = value.partition(".")[0]
        assert not panel_auth.verify_session(SECRET, expires + ".deadbeef", now=1001.0)

    def test_other_secret_rejected(self):
        value = panel_auth.make_session(SECRET, ttl=60, now=1000.0)
        assert not panel_auth.verify_session("another-secret", value, now=1001.0)

    def test_garbage_rejected(self):
        for value in ("", "not-a-cookie", "abc.def", "123"):
            assert not panel_auth.verify_session(SECRET, value)

    def test_expiry_is_absolute(self):
        value = panel_auth.make_session(SECRET, ttl=60, now=1000.0)
        assert value.startswith("1060.")


class TestCsrf:
    def test_roundtrip(self):
        session = panel_auth.make_session(SECRET, ttl=60, now=1.0)
        token = panel_auth.csrf_token(SECRET, session)
        assert panel_auth.verify_csrf(SECRET, session, token)

    def test_bound_to_the_session(self):
        first = panel_auth.make_session(SECRET, ttl=60, now=1.0)
        second = panel_auth.make_session(SECRET, ttl=60, now=2.0)
        token = panel_auth.csrf_token(SECRET, first)
        assert panel_auth.verify_csrf(SECRET, first, token)
        assert not panel_auth.verify_csrf(SECRET, second, token)

    def test_missing_or_wrong(self):
        session = panel_auth.make_session(SECRET, ttl=60, now=1.0)
        assert not panel_auth.verify_csrf(SECRET, session, "")
        assert not panel_auth.verify_csrf(SECRET, session, "nope")


class TestToken:
    def test_compare_constant_time(self):
        assert panel_auth.compare("s3cret-token", "s3cret-token")
        assert not panel_auth.compare("s3cret-token", "wrong-token")
        assert not panel_auth.compare("", "s3cret-token")
        assert not panel_auth.compare("s3cret-token", "")

    def test_token_length_policy(self):
        assert not panel_auth.token_ok("short")
        assert panel_auth.token_ok("a" * panel_auth.MIN_TOKEN_LENGTH)

    def test_generate_token_is_random_and_long(self):
        first = panel_auth.generate_token()
        second = panel_auth.generate_token()
        assert panel_auth.token_ok(first)
        assert first != second