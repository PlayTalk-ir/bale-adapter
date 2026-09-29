"""Target lists for outbound sends: inline text, .txt/.csv, or Excel (.xlsx).

Support staff keep recipient lists in three shapes, all handled here:

``--to``       one line, comma/semicolon/newline separated
``--to-file``  .txt / .csv   → one target per line (Excel's "CSV UTF-8" too)
``--to-file``  .xlsx / .xlsm → a real Excel workbook, read with the stdlib
                              (zipfile + ElementTree) so no new dependency is
                              needed in the VPS venv or in CI

Names containing spaces are preserved; only commas, semicolons, tabs and
newlines split entries, so "امیر حافظ سفیدبری" stays one target.
"""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: Splits one line into several targets (comma, Arabic comma, semicolon, tab).
_SPLIT_RE = re.compile(r"[,;\u060c\t]+")
#: "- نفس", "1. نفس", "• نفس"
_BULLET_RE = re.compile(r"^\s*(?:[-–—•*·]|\d+\s*[.)-])\s*")
_QUOTES = "\"'`“”«»\u200c "
_HEADER_RE = re.compile(r"[^\w\s\u0600-\u06ff]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)

#: Cells that are headers, not recipients (Persian + English).
_HEADER_WORDS = {
    "name", "names", "full name", "contact", "contacts", "contact name",
    "phone", "phones", "phone number", "mobile", "number", "id", "user",
    "username", "title", "recipient", "recipients",
    "نام", "اسم", "نام کامل", "نام و نام خانوادگی", "نام مخاطب", "نام گیرنده",
    "مخاطب", "مخاطبین", "شماره", "شماره تماس", "شماره موبایل", "شماره همراه",
    "موبایل", "تلفن", "همراه", "ردیف", "لیست", "گیرنده",
}

XLSX_SUFFIXES = {".xlsx", ".xlsm"}
CSV_SUFFIXES = {".csv", ".tsv"}


def clean_token(raw: Any) -> str:
    """Strip bullets, list numbering, quotes and stray whitespace."""
    text = str(raw if raw is not None else "").replace("\ufeff", "").strip()
    text = _BULLET_RE.sub("", text).strip()
    return text.strip(_QUOTES).strip()


def split_line(line: str) -> List[str]:
    """Split one input line into cleaned targets."""
    return [t for t in (clean_token(p) for p in _SPLIT_RE.split(line)) if t]


def parse_inline(text: Any) -> List[str]:
    """Parse ``--to``: newlines, commas, semicolons and tabs all separate."""
    out: List[str] = []
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in normalized.split("\n"):
        out.extend(split_line(line))
    return out


def dedupe(items: Iterable[str]) -> List[str]:
    """Drop repeats (case-insensitive) while keeping the original order."""
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def parse_column_spec(spec: Any) -> Optional[int]:
    """``'A'``/``'B'``/``'1'``/``'2'`` → 0-based column index (``None`` = first)."""
    if spec is None:
        return None
    text = str(spec).strip()
    if not text:
        return None
    if text.isdigit():
        number = int(text)
        if number < 1:
            raise ValueError(f"invalid column {spec!r}: numbers are 1-based")
        return number - 1
    if re.fullmatch(r"[A-Za-z]{1,3}", text):
        index = 0
        for ch in text.upper():
            index = index * 26 + (ord(ch) - ord("A") + 1)
        return index - 1
    raise ValueError(f"invalid column {spec!r}: use a letter (A, B) or a number (1, 2)")


def column_ref_to_index(ref: str) -> int:
    """Excel cell reference ``'B12'`` → 0-based column index (1)."""
    letters = re.match(r"[A-Za-z]+", str(ref or ""))
    if not letters:
        return 0
    index = 0
    for ch in letters.group(0).upper():
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def looks_like_header(value: Any) -> bool:
    """True when a cell looks like a column title rather than a recipient."""
    text = _HEADER_RE.sub(" ", str(value or "").lower())
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return False
    if text in _HEADER_WORDS:
        return True
    return any(text.startswith(word + " ") for word in _HEADER_WORDS)


def load_targets(
    inline: Any = None,
    path: Any = None,
    *,
    column: Any = None,
    sheet: Any = None,
    has_header: Optional[bool] = None,
) -> List[str]:
    """Combine ``--to`` and ``--to-file`` into a de-duplicated target list."""
    items: List[str] = []
    if inline:
        items.extend(parse_inline(inline))
    if path:
        items.extend(
            read_targets_file(
                path, column=column, sheet=sheet, has_header=has_header
            )
        )
    return dedupe(items)


def read_targets_file(
    path: Any,
    *,
    column: Any = None,
    sheet: Any = None,
    has_header: Optional[bool] = None,
) -> List[str]:
    """Read recipients from .xlsx/.xlsm, .csv/.tsv or a plain text file."""
    file_path = Path(str(path)).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"target file not found: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"target path is not a file: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix in XLSX_SUFFIXES:
        rows = read_xlsx_rows(file_path, sheet=sheet)
        return rows_to_targets(rows, column=column, has_header=has_header)
    if suffix in CSV_SUFFIXES:
        text = decode_bytes(file_path.read_bytes())
        delimiter = "\t" if suffix == ".tsv" else guess_delimiter(text)
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        return rows_to_targets(rows, column=column, has_header=has_header)

    text = decode_bytes(file_path.read_bytes())
    out: List[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        out.extend(split_line(line))
    return out


def guess_delimiter(sample: str) -> str:
    """Pick the delimiter used by a CSV exported from Excel (may be ``;``)."""
    for candidate in (",", ";", "\t"):
        if candidate in sample:
            return candidate
    return ","


def decode_bytes(raw: bytes) -> str:
    """Decode Persian spreadsheets saved as UTF-8, UTF-16 or CP1256."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for encoding in ("utf-8", "cp1256", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def rows_to_targets(
    rows: Sequence[Sequence[Any]],
    *,
    column: Any = None,
    has_header: Optional[bool] = None,
) -> List[str]:
    """Pick one cell per row (default: first non-empty) and clean it."""
    col = parse_column_spec(column)
    picked: List[str] = []
    for row in rows:
        cells = [str(c) for c in row]
        if col is not None:
            cell = cells[col] if col < len(cells) else ""
        else:
            cell = next((c for c in cells if c.strip()), "")
        picked.append(cell.strip())

    if has_header is True and picked:
        picked = picked[1:]
    elif has_header is None and picked and looks_like_header(picked[0]):
        picked = picked[1:]

    out: List[str] = []
    for cell in picked:
        out.extend(split_line(cell))
    return out


# ---------------------------------------------------------------------------
# Minimal .xlsx reader (stdlib only — no openpyxl in the VPS venv or in CI)
# ---------------------------------------------------------------------------

_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _local(tag: Any) -> str:
    """Namespace-agnostic tag name (``'{ns}sheet'`` → ``'sheet'``)."""
    return str(tag).rsplit("}", 1)[-1]


def _zip_path(target: str) -> str:
    """Normalize a workbook relationship target to a zip member path."""
    path = str(target or "").replace("\\", "/").lstrip("/")
    if not path:
        return ""
    if not path.startswith("xl/"):
        path = "xl/" + path
    return path


def _sheet_sort_key(name: str) -> int:
    match = re.search(r"(\d+)", Path(name).stem)
    return int(match.group(1)) if match else 0


def _fallback_sheets(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    members = [
        name
        for name in zf.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    ]
    return [(Path(name).stem, name) for name in sorted(members, key=_sheet_sort_key)]


def _workbook_rels(zf: zipfile.ZipFile) -> Dict[str, str]:
    try:
        data = zf.read("xl/_rels/workbook.xml.rels")
    except KeyError:
        return {}
    rels: Dict[str, str] = {}
    for element in ET.fromstring(data).iter():
        if _local(element.tag) != "Relationship":
            continue
        rel_id = element.get("Id")
        target = element.get("Target")
        if rel_id and target:
            rels[rel_id] = _zip_path(target)
    return rels


def xlsx_sheets(path: Any) -> List[Tuple[str, str]]:
    """List ``(sheet name, zip member)`` pairs in workbook order."""
    with zipfile.ZipFile(Path(str(path))) as zf:
        try:
            data = zf.read("xl/workbook.xml")
        except KeyError:
            return _fallback_sheets(zf)
        rels = _workbook_rels(zf)
        sheets: List[Tuple[str, str]] = []
        for element in ET.fromstring(data).iter():
            if _local(element.tag) != "sheet":
                continue
            name = element.get("name") or f"sheet{len(sheets) + 1}"
            sheets.append((name, rels.get(element.get(_REL_NS) or "", "")))
        if not sheets:
            return _fallback_sheets(zf)
        if any(not member for _, member in sheets):
            ordered = [member for _, member in _fallback_sheets(zf)]
            fixed: List[Tuple[str, str]] = []
            for index, (name, member) in enumerate(sheets):
                if not member and index < len(ordered):
                    member = ordered[index]
                fixed.append((name, member))
            sheets = fixed
        return [(name, member) for name, member in sheets if member]


def _shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    out: List[str] = []
    for element in ET.fromstring(data).iter():
        if _local(element.tag) != "si":
            continue
        out.append(
            "".join(t.text or "" for t in element.iter() if _local(t.tag) == "t")
        )
    return out


def _cell_value(cell: Any, shared: Sequence[str]) -> str:
    cell_type = (cell.get("t") or "").strip()
    if cell_type == "inlineStr":
        return "".join(t.text or "" for t in cell.iter() if _local(t.tag) == "t")
    raw: Optional[str] = None
    for child in cell:
        if _local(child.tag) == "v":
            raw = child.text
            break
    if raw is None:
        return ""
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""
    # Excel stores typed numbers as floats; phones must not print as 9.89E+11
    try:
        number = float(raw)
    except ValueError:
        return raw
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return raw


def read_xlsx_rows(
    path: Any,
    *,
    sheet: Any = None,
    max_rows: int = 0,
) -> List[List[str]]:
    """Read a worksheet into a list of rows (each a list of cell strings).

    Args:
        sheet: sheet name, or 1-based sheet number; default = first sheet.
        max_rows: stop after N rows (0 = all).
    """
    file_path = Path(str(path))
    with zipfile.ZipFile(file_path) as zf:
        sheets = xlsx_sheets(file_path)
        if not sheets:
            raise ValueError(f"no worksheets found in {file_path}")
        member = _pick_sheet(sheets, sheet)
        shared = _shared_strings(zf)
        root = ET.fromstring(zf.read(member))

    rows: List[List[str]] = []
    for row in root.iter():
        if _local(row.tag) != "row":
            continue
        cells: Dict[int, str] = {}
        fallback = 0
        for cell in list(row):
            if _local(cell.tag) != "c":
                continue
            ref = cell.get("r")
            index = column_ref_to_index(ref) if ref else fallback
            fallback = index + 1
            cells[index] = _cell_value(cell, shared)
        if not cells or not any(value.strip() for value in cells.values()):
            continue
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        if max_rows and len(rows) >= max_rows:
            break
    return rows


def _pick_sheet(sheets: Sequence[Tuple[str, str]], sheet: Any) -> str:
    """Resolve a sheet name / 1-based number to a zip member path."""
    if sheet is None or str(sheet).strip() == "":
        return sheets[0][1]
    wanted = str(sheet).strip()
    if wanted.isdigit():
        index = int(wanted) - 1
        if 0 <= index < len(sheets):
            return sheets[index][1]
        raise ValueError(
            f"sheet #{wanted} not found — workbook has {len(sheets)} sheet(s)"
        )
    for name, member in sheets:
        if name == wanted:
            return member
    available = ", ".join(name for name, _ in sheets)
    raise ValueError(f"sheet {wanted!r} not found — available: {available}")
