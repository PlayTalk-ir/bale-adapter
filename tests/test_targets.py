"""Tests for target parsing: inline text, .txt/.csv files and .xlsx workbooks.

The Excel tests build a real (minimal) workbook with zipfile so the stdlib-only
reader in ``bale_platform.targets`` is exercised end to end — no openpyxl.
"""

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform.targets import (
    clean_token,
    load_targets,
    looks_like_header,
    parse_column_spec,
    parse_inline,
    read_targets_file,
    read_xlsx_rows,
    rows_to_targets,
    xlsx_sheets,
)


class TestParseInline:
    def test_newline_separated(self):
        assert parse_inline("نفس پیروز\nامیرحافظ") == ["نفس پیروز", "امیرحافظ"]

    def test_comma_semicolon_tab(self):
        assert parse_inline("a,b;c\td") == ["a", "b", "c", "d"]

    def test_names_with_spaces_survive(self):
        assert parse_inline("امیر حافظ سفیدبری") == ["امیر حافظ سفیدبری"]

    def test_bullets_and_numbering_stripped(self):
        assert parse_inline("- نفس\n2. امیر\n• هانیه") == ["نفس", "امیر", "هانیه"]

    def test_quotes_and_bom_stripped(self):
        assert parse_inline('\ufeff"نفس"') == ["نفس"]

    def test_blank_lines_dropped_and_deduped(self):
        assert load_targets("\nنفس\n\nنفس\n ") == ["نفس"]

    def test_empty_input(self):
        assert parse_inline("") == []
        assert load_targets() == []

    def test_clean_token_handles_none(self):
        assert clean_token(None) == ""


class TestHelpers:
    def test_column_spec_letter_and_number(self):
        assert parse_column_spec("A") == 0
        assert parse_column_spec("B") == 1
        assert parse_column_spec("AA") == 26
        assert parse_column_spec("2") == 1
        assert parse_column_spec(None) is None
        assert parse_column_spec("") is None

    def test_invalid_column_spec(self):
        with pytest.raises(ValueError):
            parse_column_spec("0")
        with pytest.raises(ValueError):
            parse_column_spec("نام")

    def test_header_detection(self):
        assert looks_like_header("نام")
        assert looks_like_header("شماره موبایل")
        assert looks_like_header("Contact Name")
        assert not looks_like_header("نفس پیروز")
        assert not looks_like_header("")

    def test_rows_first_non_empty_cell(self):
        rows = [["", "نفس پیروز"], ["", "امیرحافظ"]]
        assert rows_to_targets(rows) == ["نفس پیروز", "امیرحافظ"]

    def test_rows_pick_column_by_letter(self):
        rows = [["ردیف", "نام"], ["1", "نفس"]]
        assert rows_to_targets(rows, column="B") == ["نفس"]

    def test_rows_auto_skip_header(self):
        assert rows_to_targets([["نام"], ["نفس"]]) == ["نفس"]

    def test_rows_header_kept_when_disabled(self):
        assert rows_to_targets([["نام"], ["نفس"]], has_header=False) == ["نام", "نفس"]


class TestTextAndCsvFiles:
    def test_text_file_one_per_line(self, tmp_path):
        path = tmp_path / "names.txt"
        path.write_text("نفس پیروز\nامیرحافظ\n\n", encoding="utf-8")
        assert read_targets_file(path) == ["نفس پیروز", "امیرحافظ"]

    def test_text_file_with_bullets(self, tmp_path):
        path = tmp_path / "list.txt"
        path.write_text("- نفس\r\n1. امیر\r\n", encoding="utf-8")
        assert read_targets_file(path) == ["نفس", "امیر"]

    def test_utf8_bom_csv(self, tmp_path):
        path = tmp_path / "people.csv"
        path.write_text("نام,شماره\nنفس,09924466793\n", encoding="utf-8-sig")
        assert read_targets_file(path) == ["نفس"]
        assert read_targets_file(path, column="B") == ["09924466793"]

    def test_semicolon_delimited_csv(self, tmp_path):
        path = tmp_path / "people2.csv"
        path.write_text("نفس پیروز;09924466793\n", encoding="utf-8")
        assert read_targets_file(path) == ["نفس پیروز"]
        assert read_targets_file(path, column="2") == ["09924466793"]

    def test_cp1256_persian_csv(self, tmp_path):
        path = tmp_path / "cp.csv"
        path.write_bytes("نفس\n".encode("cp1256"))
        assert read_targets_file(path) == ["نفس"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_targets_file(tmp_path / "nope.txt")

    def test_directory_raises(self, tmp_path):
        with pytest.raises(ValueError):
            read_targets_file(tmp_path)

    def test_load_targets_merges_inline_and_file(self, tmp_path):
        path = tmp_path / "names.txt"
        path.write_text("نفس\n", encoding="utf-8")
        assert load_targets("نفس, امیر", path) == ["نفس", "امیر"]


# ---------------------------------------------------------------------------
# Minimal .xlsx writer used only by these tests
# ---------------------------------------------------------------------------

SHARED = ["نام", "نفس پیروز", "امیرحافظ", "ردیف", "شماره"]

WORKBOOK_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets>'
    '<sheet name="مخاطبین" sheetId="1" r:id="rId1"/>'
    '<sheet name="Backup" sheetId="2" r:id="rId2"/>'
    "</sheets></workbook>"
)

RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>'
    "</Relationships>"
)


def _shared_xml(strings):
    items = "".join(f"<si><t>{s}</t></si>" for s in strings)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{items}</sst>"
    )


def _sheet_xml(rows):
    """int → shared-string index, float → numeric cell, str → inline string."""
    parts = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column, value in enumerate(row):
            ref = f"{chr(ord('A') + column)}{row_number}"
            if isinstance(value, int) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}" t="s"><v>{value}</v></c>')
            elif isinstance(value, float):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
        parts.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(parts)}</sheetData></worksheet>'
    )


def write_xlsx(path, sheet1, sheet2=None, shared=SHARED):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", WORKBOOK_XML)
        zf.writestr("xl/_rels/workbook.xml.rels", RELS_XML)
        zf.writestr("xl/sharedStrings.xml", _shared_xml(shared))
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(sheet1))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml(sheet2 or []))
    return path


class TestExcel:
    def test_sheet_names_and_order(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [[1]])
        assert [name for name, _ in xlsx_sheets(path)] == ["مخاطبین", "Backup"]

    def test_first_sheet_and_header_autoskip(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [[0], [1], [2]])
        assert read_targets_file(path) == ["نفس پیروز", "امیرحافظ"]

    def test_column_letter_selection(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [[3, 0], [1, 4]])
        assert read_targets_file(path, column="A") == ["نفس پیروز"]

    def test_sheet_by_name(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [[1]], sheet2=[[2]])
        assert read_targets_file(path, sheet="Backup") == ["امیرحافظ"]

    def test_sheet_by_number(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [[1]], sheet2=[[2]])
        assert read_targets_file(path, sheet="2") == ["امیرحافظ"]

    def test_unknown_sheet_raises(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [[1]])
        with pytest.raises(ValueError):
            read_targets_file(path, sheet="Missing")

    def test_numeric_phone_not_scientific(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [[1], [989123456789.0]])
        assert read_targets_file(path, has_header=False) == [
            "نفس پیروز",
            "989123456789",
        ]

    def test_inline_strings_and_blank_row(self, tmp_path):
        path = write_xlsx(tmp_path / "book.xlsx", [["نفس پیروز"], [""], ["امیر"]])
        assert read_xlsx_rows(path) == [["نفس پیروز"], ["امیر"]]
        assert read_targets_file(path) == ["نفس پیروز", "امیر"]
