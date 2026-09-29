"""Tests for the admin panel HTML layer (XSS escaping is the point)."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform import panel_ui as ui


class TestEscaping:
    def test_script_injection_is_neutralized(self):
        rendered = ui.esc("<script>alert(1)</script>")
        assert "<script>" not in rendered
        assert "&lt;script&gt;" in rendered

    def test_none_and_numbers(self):
        assert ui.esc(None) == ""
        assert ui.esc(164862466) == "164862466"

    def test_quote_escaping(self):
        rendered = ui.esc('نام" onmouseover="x')
        assert '"' not in rendered


class TestTable:
    def test_plain_cells_are_escaped(self):
        rendered = ui.table(["متن"], [["<b>سلام</b>"]])
        assert "<b>سلام</b>" not in rendered
        assert "&lt;b&gt;سلام&lt;/b&gt;" in rendered

    def test_raw_cells_pass_through(self):
        rendered = ui.table(["وضعیت"], [[ui.badge("OK", "ok")]])
        assert '<span class="badge ok">OK</span>' in rendered

    def test_customer_text_starting_with_lt_is_escaped(self):
        rendered = ui.table(["متن"], [["<img src=x onerror=alert(1)>"]])
        assert "<img" not in rendered

    def test_empty_table(self):
        rendered = ui.table(["الف", "ب"], [])
        assert "—" in rendered and 'colspan="2"' in rendered

    def test_kv_table_escapes_values(self):
        rendered = ui.kv_table([("مسیر", "C:\\tmp\\<x>")])
        assert "&lt;x&gt;" in rendered


class TestLayoutAndForms:
    def test_layout_nav_and_title(self):
        rendered = ui.layout("عنوان", "<p>بدنه</p>", active="/contacts")
        assert 'href="/contacts"' in rendered
        assert "عنوان" in rendered
        assert "<p>بدنه</p>" in rendered

    def test_banners_escaped(self):
        rendered = ui.layout("t", "", error="<script>x</script>")
        assert "<script>x</script>" not in rendered

    def test_login_page(self):
        rendered = ui.login_page(error="توکن اشتباه است")
        assert 'name="token"' in rendered and "توکن اشتباه است" in rendered

    def test_send_form_fields(self):
        rendered = ui.send_form(
            "csrf-value", targets="باران صلواتی", text="سلام", preview=True, delay=2.5
        )
        assert 'name="targets"' in rendered
        assert 'name="text"' in rendered
        assert 'value="csrf-value"' in rendered
        assert "باران صلواتی" in rendered
        assert "checked" in rendered

    def test_send_form_without_preview(self):
        rendered = ui.send_form("c", preview=False)
        assert "checked" not in rendered


class TestHelpers:
    def test_clip(self):
        assert ui.clip("abcdef", 4) == "abc…"
        assert ui.clip("ab", 4) == "ab"
        assert ui.clip(None) == ""

    def test_fmt_ms(self):
        assert ui.fmt_ms(0) == "1970-01-01 00:00"
        assert ui.fmt_ms("garbage") == "—"

    def test_badge_escapes_label(self):
        rendered = ui.badge("<x>")
        assert "&lt;x&gt;" in rendered and "<x>" not in rendered