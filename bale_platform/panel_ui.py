"""HTML rendering for the admin panel (pure strings — no aiohttp import).

Everything user-supplied or customer-sourced is escaped with :func:`esc` before
it reaches markup — the panel renders customer names and message bodies, so a
missing escape would be an XSS hole. Rendering is pure so it is testable in CI.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence

from bale_platform import panel_auth

NAV = [
    ("داشبورد", "/"),
    ("ارسال پیام", "/send"),
    ("دفترچه", "/contacts"),
    ("صندوق", "/inbox"),
    ("پیام‌ها", "/messages"),
    ("تحلیل", "/analysis"),
    ("سیستم", "/system"),
    ("توکن API", "/api-tokens"),
]

# Persian UI font (referenced in PAGE_CSS body { font-family: "Vazirmatn", ... }).
PAGE_HEAD_LINKS = (
    '<link rel="preconnect" href="https://fonts.bunny.net">'
    '<link rel="stylesheet" href="https://fonts.bunny.net/css?family=vazirmatn:400,500,600,700&display=swap">'
)

PAGE_CSS = """
:root { --ink:#1d2433; --muted:#6b7280; --line:#e5e7eb; --bg:#f6f7fb; --card:#fff;
        --ok:#0a7d33; --fail:#b42318; --accent:#2456d6; }
* { box-sizing: border-box; }
body { margin:0; font-family:"Vazirmatn",Tahoma,"Segoe UI",sans-serif; background:var(--bg);
       color:var(--ink); direction:rtl; }
header { background:var(--card); border-bottom:1px solid var(--line); padding:10px 18px;
         display:flex; gap:12px 18px; align-items:center; flex-wrap:wrap; }
header .brand { font-weight:700; font-size:15px; white-space:nowrap; }
header nav { display:flex; flex-wrap:wrap; gap:2px 4px; align-items:center; flex:1 1 auto;
             justify-content:flex-start; }
nav a { text-decoration:none; color:var(--muted); padding:6px 10px; border-radius:8px;
        font-size:13px; font-weight:500; white-space:nowrap; }
nav a:hover { background:#eef2ff; color:var(--accent); }
nav a.active { background:#eef2ff; color:var(--accent); font-weight:600; }
main { max-width:1100px; margin:18px auto; padding:0 16px; display:grid; gap:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
.card h2 { margin:0 0 10px; font-size:15px; color:var(--muted); font-weight:600; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
.stat .n { font-size:26px; font-weight:700; }
.stat .l { color:var(--muted); font-size:12px; margin-top:2px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { text-align:right; padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; white-space:nowrap; }
tr:hover td { background:#fafbff; }
code, .mono { font-family:Consolas,Menlo,monospace; font-size:12px; direction:ltr; unicode-bidi:embed; }
label { display:block; font-size:12px; color:var(--muted); margin:10px 0 4px; }
textarea, input[type=text], input[type=number], input[type=password] {
  width:100%; border:1px solid var(--line); border-radius:8px; padding:8px 10px;
  font:inherit; background:#fff; }
textarea { min-height:90px; resize:vertical; }
button { border:0; border-radius:8px; background:var(--accent); color:#fff; padding:9px 16px;
         font:inherit; cursor:pointer; margin-top:12px; }
button.ghost { background:#eef2ff; color:var(--accent); }
button.danger { background:var(--fail); }
.notice { background:#e7f6ec; color:var(--ok); border:1px solid #bfe6cc; border-radius:10px;
          padding:9px 12px; margin-bottom:12px; }
.error { background:#fdecea; color:var(--fail); border:1px solid #f5c6c0; border-radius:10px;
         padding:9px 12px; margin-bottom:12px; }
.badge { display:inline-block; border-radius:999px; padding:2px 9px; font-size:11px;
         border:1px solid var(--line); background:#f3f4f6; color:var(--muted); }
.badge.ok { background:#e7f6ec; color:var(--ok); border-color:#bfe6cc; }
.badge.fail { background:#fdecea; color:var(--fail); border-color:#f5c6c0; }
.badge.manual { background:#fff4e0; color:#8a5300; border-color:#f2d9a4; }
.log { background:#0f1420; color:#d7e0ff; border-radius:10px; padding:12px; min-height:120px;
       max-height:420px; overflow:auto; white-space:pre-wrap; direction:ltr; text-align:left;
       font-family:Consolas,Menlo,monospace; font-size:12px; }
.muted { color:var(--muted); font-size:12px; }
.row { display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; }
.row > * { flex:1 1 200px; }
a { color:var(--accent); }
"""


def esc(value: Any) -> str:
    """HTML-escape anything that may contain user/customer content."""
    return html.escape(str(value if value is not None else ""), quote=True)


class Raw(str):
    """Marks an already-rendered HTML fragment — inserted without escaping."""


def clip(text: Any, limit: int = 120) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def fmt_ms(ms: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M"
        )
    except (TypeError, ValueError, OverflowError):
        return "—"


def badge(text: Any, kind: str = "") -> Raw:
    css = f"badge {kind}".strip()
    return Raw(f'<span class="{esc(css)}">{esc(text)}</span>')


def hidden(name: str, value: Any) -> str:
    return f'<input type="hidden" name="{esc(name)}" value="{esc(value)}">'


def form_open(action: str, csrf: str) -> str:
    return f'<form method="post" action="{esc(action)}">{hidden("_csrf", csrf)}'


def layout(
    title: str,
    body: str,
    *,
    active: str = "",
    csrf: str = "",
    notice: str = "",
    error: str = "",
) -> str:
    nav = ""
    for label, href in NAV:
        css = ' class="active"' if href == active else ""
        nav += f'<a href="{esc(href)}"{css}>{esc(label)}</a>'
    banners = ""
    if notice:
        banners += f'<div class="notice">{esc(notice)}</div>'
    if error:
        banners += f'<div class="error">{esc(error)}</div>'
    return (
        '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)} — پنل بله پلی‌تاک</title>"
        f"{PAGE_HEAD_LINKS}"
        f"<style>{PAGE_CSS}</style></head><body>"
        '<header><span class="brand">پنل ادمین بله پلی‌تاک</span>'
        f"<nav>{nav}</nav></header>"
        f"<main>{banners}{body}</main></body></html>"
    )


def card(title: str, body: str, *, note: str = "") -> str:
    tail = f'<div class="muted">{esc(note)}</div>' if note else ""
    return f'<section class="card"><h2>{esc(title)}</h2>{body}{tail}</section>'


def stat(number: Any, label: str) -> str:
    return (
        f'<div class="stat"><div class="n">{esc(number)}</div>'
        f'<div class="l">{esc(label)}</div></div>'
    )


def kv_table(pairs: Iterable[tuple]) -> str:
    rows = []
    for label, value in pairs:
        cell = value if isinstance(value, Raw) else esc(value)
        rows.append(f"<tr><th>{esc(label)}</th><td>{cell}</td></tr>")
    return f"<table>{''.join(rows)}</table>"


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]], *, empty: str = "—") -> str:
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body_rows: List[str] = []
    for row in rows:
        cells = []
        for cell in row:
            if isinstance(cell, Raw):
                cells.append(f"<td>{cell}</td>")
            else:
                cells.append(f"<td>{esc(cell)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    if not body_rows:
        body_rows.append(
            f'<tr><td colspan="{len(headers)}" class="muted">{esc(empty)}</td></tr>'
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def login_page(*, error: str = "", notice: str = "") -> str:
    err_html = f'<div class="error">{esc(error)}</div>' if error else ""
    notice_html = f'<div class="notice">{esc(notice)}</div>' if notice else ""
    body = (
        '<section class="card" style="max-width:420px;margin:40px auto">'
        "<h2>ورود ادمین</h2>"
        f"{err_html}{notice_html}"
        '<form method="post" action="/login">'
        '<label>نام کاربری</label>'
        f'<input type="text" name="username" value="{esc(panel_auth.DEFAULT_PANEL_USER)}" autocomplete="username" autofocus>'
        '<label>رمز عبور</label>'
        '<input type="password" name="password" autocomplete="current-password">'
        '<button type="submit">ورود</button>'
        "</form></section>"
    )
    return layout("ورود", body, active="/login", notice=notice, error=error)


def send_form(
    csrf: str,
    *,
    targets: str = "",
    text: str = "",
    preview: bool = True,
    delay: float = 1.0,
) -> str:
    """The one box for names + the one box for the message text."""
    checked = " checked" if preview else ""
    return (
        card(
            "ارسال پیام",
            form_open("/send", csrf)
            + '<label>گیرنده‌ها — اسم ذخیره‌شده، شماره یا chat_id (با اینتر/کاما جدا کنید)</label>'
            + f'<textarea name="targets" placeholder="باران صلواتی&#10;09924466793">{esc(targets)}</textarea>'
            + '<label>متن پیام</label>'
            + f'<textarea name="text">{esc(text)}</textarea>'
            + '<div class="row">'
            + '<div><label>فاصله بین ارسال‌ها (ثانیه)</label>'
            + f'<input type="number" name="delay" value="{esc(delay)}" min="0" step="0.5"></div>'
            + '<div><label>&nbsp;</label>'
            + f'<input type="checkbox" name="preview" value="1"{checked}> '
            + "پیش‌نمایش (فقط Resolve، ارسال نمی‌شود)</div>"
            + "</div>"
            + '<button type="submit">اجرا</button>'
            + "</form>",
            note="اسم‌ها از دفترچه محلی resolve می‌شوند؛ اسم مبهم FAIL می‌شود و هرگز حدس زده نمی‌شود.",
        )
    )
