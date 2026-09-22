"""Tests for phone normalization used by login + outbound tools."""

from bale_platform.phone import normalize_phone_int


class TestNormalizePhone:
    def test_local_09_format(self):
        assert normalize_phone_int("09924466793") == 989924466793

    def test_international_98_format(self):
        assert normalize_phone_int("989924466793") == 989924466793

    def test_plus_prefix(self):
        assert normalize_phone_int("+989924466793") == 989924466793
