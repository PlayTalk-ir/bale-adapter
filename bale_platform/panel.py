"""aiohttp admin panel for the Bale support adapter.

One web UI for everything the CLI could do:

* **ارسال پیام** — a names box + a message box (no terminal), preview-first;
* **دفترچه** — the local contact book: search / refresh from Bale / manual add;
* **صندوق** — per-chat and per-agent unread plus live Bale unread;
* **پیام‌ها / تحلیل** — everything stored in SQLite, category buckets, FAQ hints;
* **سیستم** — paths, KB facts, runner log.

Security model:
* single operator token (``BALE_PANEL_TOKEN``) → signed expiring cookie;
* every state-changing POST carries a CSRF token bound to that cookie;
* aiohttp is already a project dependency, so the panel adds no new packages.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aiohttp import web

from bale_platform import panel_auth
from bale_platform import panel_ui as ui
from bale_platform.analysis import analyze_concerns, classify_text
from bale_platform.contact_store import ContactBook, refresh_book
from bale_platform.outbound import (
    TARGET_CHAT_ID,
    TARGET_PHONE,
    classify_target,
    resolve_target,
    send_to_targets,
)
from bale_platform.paths import contacts_path, facts_path, log_path, store_path
from bale_platform.phone import to_ascii_digits
from bale_platform.session import bale_client
from bale_platform.store import StoredMessage, SupportStore
from bale_platform.targets import parse_inline

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090
SEND_FORM_ACTION = "/send"


class PanelState:
    """Config + per-request store factories (cheap SQLite connects)."""

    def __init__(
        self, *, token: str, no_auth: bool = False, dialog_limit: int = 200
    ) -> None:
        self.token = token
        self.no_auth = no_auth
        self.dialog_limit = dialog_limit

    def book(self) -> ContactBook:
        return ContactBook(contacts_path())

    def store(self) -> SupportStore:
        return SupportStore(store_path())

    def session_ok(self, value: str) -> bool:
        return self.no_auth or panel_auth.verify_session(self.token, value)


STATE_KEY: "web.AppKey[PanelState]" = web.AppKey("state", PanelState)
JOBBOX_KEY: "web.AppKey[Dict[str, Any]]" = web.AppKey("jobbox", dict)


def redirect(path: str) -> web.HTTPFound:
    """302 — raised, because aiohttp 3.14 deprecates returning HTTPException."""
    raise web.HTTPFound(path)


@dataclass
class Job:
    """One background action (send / refresh / sync) with a live log."""

    title: str
    lines: List[str] = field(default_factory=list)
    done: bool = False
    error: str = ""
    started: float = field(default_factory=time.time)
    confirm: Optional[Dict[str, str]] = None

    def log(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) > 400:
            del self.lines[:100]

    def elapsed(self) -> float:
        return round(time.time() - self.started, 1)

    def can_confirm(self) -> bool:
        return bool(self.done and not self.error and self.confirm)


async def _run_job(job: Job, runner: Callable[[Job], Awaitable[None]]) -> None:
    try:
        await runner(job)
    except Exception as exc:  # never let a job kill the panel
        job.error = f"{type(exc).__name__}: {exc}"
        job.log(f"[error] {job.error}")
    finally:
        job.done = True


def start_job(
    app: web.Application, title: str, runner: Callable[[Job], Awaitable[None]]
) -> Optional[Job]:
    """Start one background job; ``None`` when another job is still running."""
    current = app[JOBBOX_KEY].get("job")
    if current is not None and not current.done:
        return None
    job = Job(title)
    app[JOBBOX_KEY]["job"] = job
    app[JOBBOX_KEY]["task"] = asyncio.create_task(_run_job(job, runner))
    return job


@web.middleware
async def auth_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    state: PanelState = request.app[STATE_KEY]
    if state.no_auth or request.path in ("/login", "/healthz"):
        return await handler(request)

    session = request.cookies.get(panel_auth.SESSION_COOKIE, "")
    if not state.session_ok(session):
        if request.path.startswith("/api/"):
            return web.json_response({"error": "unauthorized"}, status=401)
        raise web.HTTPFound("/login")

    request["session"] = session
    request["csrf"] = panel_auth.csrf_token(state.token, session)
    return await handler(request)


async def form_and_csrf(request: web.Request) -> Any:
    """Read a POST body and enforce its CSRF token."""
    state: PanelState = request.app[STATE_KEY]
    form = await request.post()
    if not state.no_auth:
        ok = panel_auth.verify_csrf(
            state.token, request.get("session", ""), str(form.get("_csrf", ""))
        )
        if not ok:
            raise web.HTTPForbidden(text="invalid CSRF token")
    return form


def html_response(body: str, *, status: int = 200) -> web.Response:
    return web.Response(
        body=body.encode("utf-8"), content_type="text/html", charset="utf-8", status=status
    )


# ---------------------------------------------------------------------------
# background job runners
# ---------------------------------------------------------------------------


def _make_send_runner(
    state: PanelState,
    targets: List[str],
    text: str,
    *,
    dry_run: bool,
    delay: float,
) -> Callable[[Job], Awaitable[None]]:
    async def runner(job: Job) -> None:
        book = state.book()
        index = book.to_index()
        mode = "DRY-RUN (nothing sent)" if dry_run else "REAL SEND"
        job.log(f"# targets: {len(targets)} | book: {len(book)} entries | {mode}")
        job.log(f"# text: {ui.clip(text, 200)}")
        async with bale_client() as client:
            results = await send_to_targets(
                client,
                targets,
                text,
                store=state.store(),
                dry_run=dry_run,
                index=index,
                delay=delay,
                on_progress=lambda pos, total, target: job.log(
                    f"... [{pos}/{total}] {target}"
                ),
            )
        ok = 0
        for result in results:
            mark = "OK" if result.ok else "FAIL"
            extra = f" -> {result.matched_name}" if result.matched_name else ""
            job.log(
                f"[{mark}] {result.target}{extra} chat_id={result.chat_id} — {result.detail}"
            )
            ok += 1 if result.ok else 0
        job.log(
            f"# {ok}/{len(results)} ok"
            + (" (dry-run — nothing sent)" if dry_run else "")
        )

    return runner


def _make_refresh_runner(state: PanelState) -> Callable[[Job], Awaitable[None]]:
    async def runner(job: Job) -> None:
        book = state.book()
        job.log(f"# refreshing contact book ({book.path}) …")
        async with bale_client() as client:
            counts = await refresh_book(book, client, dialog_limit=state.dialog_limit)
        notes = "; ".join(counts.pop("notes", []) or [])
        summary = ", ".join(f"{key}={value}" for key, value in counts.items())
        job.log(f"# refresh: {summary}" + (f" [{notes}]" if notes else ""))

    return runner


def _make_sync_runner(
    state: PanelState, *, dialog_limit: int = 40, history_limit: int = 30
) -> Callable[[Job], Awaitable[None]]:
    async def runner(job: Job) -> None:
        # inbox.py imports aiobale at module level → keep it lazy (CI has no aiobale)
        from bale_platform.inbox import sync_dialog_history

        store = state.store()
        async with bale_client() as client:
            saved = await sync_dialog_history(
                client,
                store,
                dialog_limit=dialog_limit,
                history_limit=history_limit,
            )
        job.log(f"# synced {saved} messages -> {store.path}")

    return runner


def _make_live_unread_runner(state: PanelState) -> Callable[[Job], Awaitable[None]]:
    async def runner(job: Job) -> None:
        from bale_platform.inbox import account_unread_dialogs, list_dialogs

        async with bale_client() as client:
            dialogs = await list_dialogs(client, limit=50, private_only=False)
        unread = account_unread_dialogs(dialogs)
        job.log(f"# dialogs: {len(dialogs)} | unread chats: {len(unread)}")
        for dialog in unread:
            job.log(
                f"chat={dialog.chat_id} name={dialog.label!r} unread={dialog.unread_count}"
                f" last=[{dialog.last_timestamp}] {ui.clip(dialog.last_message, 100)}"
            )

    return runner


# ---------------------------------------------------------------------------
# auth handlers
# ---------------------------------------------------------------------------


async def h_login_get(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    session = request.cookies.get(panel_auth.SESSION_COOKIE, "")
    if not state.no_auth and state.session_ok(session):
        return redirect("/")
    return html_response(ui.login_page())


async def h_login_post(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    form = await request.post()
    if panel_auth.compare(state.token, str(form.get("token", ""))):
        response = web.HTTPFound("/")
        response.set_cookie(
            panel_auth.SESSION_COOKIE,
            panel_auth.make_session(state.token),
            httponly=True,
            samesite="Strict",
            path="/",
        )
        raise response
    await asyncio.sleep(1.0)  # slow brute force down
    return html_response(ui.login_page(error="توکن اشتباه است"), status=401)


async def h_logout(request: web.Request) -> web.Response:
    response = web.HTTPFound("/login")
    response.del_cookie(panel_auth.SESSION_COOKIE, path="/")
    raise response


async def h_healthz(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


def _utc_day_start_ms() -> int:
    now = time.time()
    return int((now - (now % 86400)) * 1000)


def _name_map(book: ContactBook) -> Dict[str, str]:
    return {str(entry.chat_id): entry.name for entry in book.all()}


def _direction_badge(direction: str) -> str:
    return ui.badge("ورودی", "ok") if direction == "in" else ui.badge("خروجی")


def _messages_table(
    messages: List[StoredMessage], names: Dict[str, str], *, limit: int = 10
) -> str:
    rows = []
    for message in messages[:limit]:
        rows.append(
            (
                ui.fmt_ms(message.date_ms),
                ui.Raw(
                    f'<span class="mono">{ui.esc(message.chat_id)}</span>'
                    f'<div class="muted">{ui.esc(names.get(message.chat_id, ""))}</div>'
                ),
                _direction_badge(message.direction),
                ui.badge(classify_text(message.text)),
                ui.esc(ui.clip(message.text, 140)),
            )
        )
    return ui.table(
        ["زمان", "چت", "جهت", "دسته", "متن"], rows, empty="هنوز پیامی ذخیره نشده"
    )


def _analysis_card(summary: Dict[str, Any]) -> str:
    rows = []
    for bucket in summary.get("categories", []):
        rows.append(
            (
                ui.badge(bucket["category"]),
                str(bucket["count"]),
                ui.esc(ui.clip(" | ".join(bucket.get("examples", [])[:2]), 160)),
            )
        )
    hints = ", ".join(summary.get("faq_topic_hints", [])[:10]) or "—"
    body = (
        ui.table(["دسته", "تعداد", "نمونه"], rows)
        + f'<div class="muted">FAQ hints: {ui.esc(hints)}</div>'
    )
    return ui.card("تحلیل دغدغه‌ها", body)


async def h_dashboard(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    book = state.book()
    store = state.store()
    messages = store.recent_messages(limit=5000)
    incoming = sum(1 for m in messages if m.direction == "in")
    today = sum(1 for m in messages if m.date_ms >= _utc_day_start_ms())
    names = _name_map(book)
    summary = analyze_concerns(messages, incoming_only=True)

    stats = (
        '<div class="cards">'
        + ui.stat(len(book), "مخاطبین دفترچه")
        + ui.stat(len(messages), "پیام ذخیره‌شده")
        + ui.stat(incoming, "ورودی از مشتری")
        + ui.stat(today, "پیام امروز (UTC)")
        + "</div>"
    )
    body = (
        stats
        + ui.send_form(request.get("csrf", ""), preview=True)
        + ui.card(
            "آخرین پیام‌ها",
            _messages_table(messages, names, limit=10)
            + '<div class="muted"><a href="/messages">همه پیام‌ها →</a></div>',
        )
        + _analysis_card(summary)
    )
    return html_response(
        ui.layout(
            "داشبورد",
            body,
            active="/",
            csrf=request.get("csrf", ""),
            notice=request.query.get("notice", ""),
            error=request.query.get("error", ""),
        )
    )


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(str(value))


def _parse_send_form(form: Any) -> tuple[List[str], str, float, bool]:
    targets = parse_inline(str(form.get("targets", "")))
    text = str(form.get("text", "")).strip()
    raw_delay = str(form.get("delay") or "1").strip()
    try:
        delay = max(0.0, float(raw_delay))
    except ValueError:
        delay = 1.0
    preview = str(form.get("preview") or "") == "1"
    return targets, text, delay, preview


async def h_send_post(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    form = await form_and_csrf(request)
    targets, text, delay, preview = _parse_send_form(form)

    if not targets or not text:
        message = "گیرنده و متن پیام هر دو لازم است"
        return redirect(
            f"/?error={_quote(message)}&targets={_quote(chr(10).join(targets))}"
        )

    runner = _make_send_runner(state, targets, text, dry_run=preview, delay=delay)
    job = start_job(request.app, "پیش‌نمایش ارسال" if preview else "ارسال پیام", runner)
    if job is None:
        return redirect("/job?busy=1")
    if preview:
        job.confirm = {"targets": "\n".join(targets), "text": text, "delay": str(delay)}
    return redirect("/job")


async def h_job(request: web.Request) -> web.Response:
    job: Optional[Job] = request.app[JOBBOX_KEY].get("job")
    if job is None:
        return redirect("/")
    state: PanelState = request.app[STATE_KEY]
    csrf = request.get("csrf", "")

    status = "در حال اجرا…" if not job.done else ("خطا" if job.error else "پایان یافت")
    confirm_block = ""
    if job.can_confirm():
        payload = job.confirm or {}
        confirm_block = (
            '<section class="card"><h2>تأیید و ارسال واقعی</h2>'
            "<div class=\"muted\">پیش‌نمایش فقط Resolve بود؛ با این دکمه پیام واقعاً ارسال می‌شود.</div>"
            + ui.form_open("/send", csrf)
            + ui.hidden("targets", payload.get("targets", ""))
            + ui.hidden("text", payload.get("text", ""))
            + ui.hidden("delay", payload.get("delay", "1"))
            + '<button type="submit">تأیید و ارسال</button>'
            + "</form></section>"
        )

    body = (
        ui.card(
            f"# {job.title}",
            f'<div class="muted">وضعیت: {ui.esc(status)} — {job.elapsed()} ثانیه</div>'
            + f'<pre class="log" id="joblog">{ui.esc(chr(10).join(job.lines))}</pre>',
        )
        + confirm_block
        + '<div class="muted"><a href="/">← بازگشت به داشبورد</a></div>'
    )
    poll = "" if job.done else "<script>setTimeout(()=>location.reload(),2000)</script>"
    return html_response(ui.layout("کار در جریان", body + poll, active="/send", csrf=csrf))


async def h_api_job(request: web.Request) -> web.Response:
    job: Optional[Job] = request.app[JOBBOX_KEY].get("job")
    if job is None:
        return web.json_response({"done": True, "lines": []})
    return web.json_response(
        {
            "title": job.title,
            "lines": job.lines,
            "done": job.done,
            "error": job.error,
            "elapsed": job.elapsed(),
            "can_confirm": job.can_confirm(),
        }
    )


# ---------------------------------------------------------------------------
# contact book
# ---------------------------------------------------------------------------


def _int_query(request: web.Request, name: str, default: int) -> int:
    raw = request.query.get(name, "")
    try:
        return max(1, int(raw)) if raw else default
    except ValueError:
        return default


async def h_contacts(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    book = state.book()
    csrf = request.get("csrf", "")
    query = request.query.get("q", "").strip()
    limit = _int_query(request, "limit", 100)
    entries = book.search(query, limit=limit) if query else book.all()[:limit]

    def _remove_form(chat_id: int) -> str:
        return (
            ui.form_open("/contacts/remove", csrf)
            + ui.hidden("chat_id", chat_id)
            + '<button class="danger" type="submit">حذف</button></form>'
        )

    rows = []
    for entry in entries:
        origin = ui.badge("دستی", "manual") if entry.manual else ui.badge(entry.source)
        rows.append(
            (
                ui.Raw(f'<span class="mono">{entry.chat_id}</span>'),
                ui.esc(entry.name),
                ui.esc(entry.local_name),
                ui.esc(entry.profile_name),
                (
                    ui.Raw(f'<span class="mono">@{ui.esc(entry.username)}</span>')
                    if entry.username
                    else "—"
                ),
                origin,
                ui.esc(entry.updated_at),
                ui.Raw(_remove_form(entry.chat_id)),
            )
        )

    search = (
        card_title_form := ui.form_open("/contacts", csrf)
        + '<label>جست‌وجو</label><input type="text" name="q" value="'
        + ui.esc(query)
        + '"><button class="ghost" type="submit">جست‌وجو</button></form>'
    )
    add_form = (
        ui.form_open("/contacts/add", csrf)
        + '<div class="row"><div><label>نام (همان که در پیام می‌نویسید)</label>'
        + '<input type="text" name="name" required></div>'
        + '<div><label>chat_id یا شماره موبایل</label>'
        + '<input type="text" name="target" placeholder="164862466 یا 09924466793" required></div>'
        + "</div><button type=\"submit\">افزودن به دفترچه</button></form>"
    )
    refresh_form = (
        ui.form_open("/contacts/refresh", csrf)
        + '<button type="submit">به‌روزرسانی از بله (چت‌ها + دفترچه بله)</button>'
        + "</form>"
    )

    body = (
        ui.card("افزودن مخاطب دستی", add_form, note="این ردیف manual می‌شود و هیچ refreshی آن را پاک یا بازنویسی نمی‌کند.")
        + ui.card("به‌روزرسانی از بله", refresh_form, note="همه‌ی کسانی که با آن‌ها چت داشته‌ایم ریخته می‌شود؛ ردیف‌های دستی دست‌نخورده می‌مانند. ۳۰ تا ۶۰ ثانیه طول می‌کشد.")
        + ui.card(
            f"دفترچه مخاطبین ({len(book)} ردیف)",
            search + ui.table(["chat_id", "نام", "local", "پروفایل", "یوزرنیم", "منبع", "به‌روزرسانی", ""], rows),
        )
    )
    return html_response(
        ui.layout(
            "دفترچه",
            body,
            active="/contacts",
            csrf=csrf,
            notice=request.query.get("notice", ""),
            error=request.query.get("error", ""),
        )
    )


async def h_contacts_add(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    form = await form_and_csrf(request)
    name = str(form.get("name", "")).strip()
    target = str(form.get("target", "")).strip()
    if not name or not target:
        return redirect("/contacts?error=" + _quote("نام و شناسه هر دو لازم است"))

    kind = classify_target(target)
    if kind == TARGET_CHAT_ID:
        digits = to_ascii_digits(target).replace(" ", "").replace("-", "")
        chat_id = int(digits)
    elif kind == TARGET_PHONE:
        async with bale_client() as client:
            resolved = await resolve_target(client, target)
        if not resolved.chat_id:
            return redirect("/contacts?error=" + _quote(f"شماره {target} در بله پیدا نشد"))
        chat_id = resolved.chat_id
    else:
        return redirect("/contacts?error=" + _quote("بخش دوم باید chat_id یا شماره باشد"))

    entry = state.book().add_manual(name, chat_id)
    return redirect(
        "/contacts?notice=" + _quote(f"اضافه شد: {entry.name} (chat={entry.chat_id})")
    )


async def h_contacts_remove(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    form = await form_and_csrf(request)
    chat_id = str(form.get("chat_id", "")).strip()
    if not chat_id.isdigit():
        return redirect("/contacts?error=" + _quote("chat_id نامعتبر است"))
    removed = state.book().remove(chat_id)
    message = f"حذف شد: chat={chat_id}" if removed else f"chat={chat_id} در دفترچه نبود"
    kind = "notice" if removed else "error"
    return redirect(f"/contacts?{kind}=" + _quote(message))


async def h_contacts_refresh(request: web.Request) -> web.Response:
    await form_and_csrf(request)
    state: PanelState = request.app[STATE_KEY]
    job = start_job(request.app, "به‌روزرسانی دفترچه", _make_refresh_runner(state))
    return redirect("/job?busy=1") if job is None else redirect("/job")


# ---------------------------------------------------------------------------
# inbox
# ---------------------------------------------------------------------------


def _int_query(request: web.Request, name: str, default: int) -> int:
    raw = request.query.get(name, "")
    try:
        return max(1, int(raw)) if raw else default
    except ValueError:
        return default


async def h_inbox(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    store = state.store()
    names = _name_map(state.book())
    csrf = request.get("csrf", "")

    buckets: Dict[str, Dict[str, Any]] = {}
    for message in store.recent_messages(limit=3000):
        bucket = buckets.setdefault(message.chat_id, {"in": 0, "out": 0, "last": None})
        bucket[message.direction] = bucket[message.direction] + 1
        if message.direction == "in" and (
            bucket["last"] is None or message.date_ms > bucket["last"].date_ms
        ):
            bucket["last"] = message

    rows = []
    for chat_id, bucket in sorted(
        buckets.items(), key=lambda kv: kv[1]["last"].date_ms, reverse=True
    )[:40]:
        last: Optional[StoredMessage] = bucket["last"]
        rows.append(
            (
                ui.Raw(
                    f'<span class="mono">{ui.esc(chat_id)}</span>'
                    f'<div class="muted">{ui.esc(names.get(chat_id, ""))}</div>'
                ),
                str(bucket["in"]),
                str(bucket["out"]),
                ui.fmt_ms(last.date_ms) if last else "—",
                ui.esc(ui.clip(last.text, 120)) if last else "—",
            )
        )

    agent = request.query.get("agent", "").strip()
    agent_block = ""
    if agent:
        unread = store.unread_for_agent(agent)
        rows_for_agent = [
            (
                ui.fmt_ms(m.date_ms),
                f'<span class="mono">{ui.esc(m.chat_id)}</span>'
                f'<div class="muted">{ui.esc(names.get(m.chat_id, ""))}</div>',
                ui.esc(ui.clip(m.text, 160)),
            )
            for m in unread[:50]
        ]
        agent_block = ui.card(
            f"پیام‌های نخوانده برای agent «{agent}»",
            ui.table(["زمان", "چت", "متن"], rows_for_agent, empty="همه خوانده شده ✅"),
        )

    agents_line = ", ".join(store.agents()) or "هنوز agentی ack نزده"
    actions = (
        ui.form_open("/inbox/sync", csrf)
        + '<button class="ghost" type="submit">همگام‌سازی تاریخچه از بله</button></form> '
        + ui.form_open("/inbox/live", csrf)
        + '<button class="ghost" type="submit">بررسی unread زنده بله</button></form>'
    )
    agent_form = (
        ui.form_open("/inbox", csrf)
        + '<div class="row"><div><label>agent id (مثل sara)</label>'
        + f'<input type="text" name="agent" value="{ui.esc(agent)}"></div>'
        + '<div><button type="submit">نمایش unread این agent</button></div></div></form>'
    )

    body = (
        ui.card("اقدامات", actions, note=f"agentهای ثبت‌شده: {agents_line}")
        + ui.card("unread هر agent", agent_form)
        + agent_block
        + ui.card(
            "چت‌ها (از دیتابیس محلی)",
            ui.table(["چت", "ورودی", "خروجی", "آخرین ورودی", "متن"], rows),
        )
    )
    return html_response(
        ui.layout(
            "صندوق",
            body,
            active="/inbox",
            csrf=csrf,
            notice=request.query.get("notice", ""),
            error=request.query.get("error", ""),
        )
    )


async def h_inbox_sync(request: web.Request) -> web.Response:
    await form_and_csrf(request)
    state: PanelState = request.app[STATE_KEY]
    job = start_job(request.app, "همگام‌سازی تاریخچه", _make_sync_runner(state))
    return redirect("/job?busy=1") if job is None else redirect("/job")


async def h_inbox_live(request: web.Request) -> web.Response:
    await form_and_csrf(request)
    state: PanelState = request.app[STATE_KEY]
    job = start_job(request.app, "unread زنده بله", _make_live_unread_runner(state))
    return redirect("/job?busy=1") if job is None else redirect("/job")


# ---------------------------------------------------------------------------
# messages / analysis
# ---------------------------------------------------------------------------


async def h_messages(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    store = state.store()
    names = _name_map(state.book())
    chat = request.query.get("chat", "").strip()
    direction = request.query.get("direction", "").strip()
    limit = _int_query(request, "limit", 100)

    messages = store.recent_messages(chat_id=chat or None, limit=limit * 3)
    if direction in ("in", "out"):
        messages = [m for m in messages if m.direction == direction]
    messages = messages[:limit]

    rows = [
        (
            ui.fmt_ms(m.date_ms),
            ui.Raw(
                f'<span class="mono">{ui.esc(m.chat_id)}</span>'
                f'<div class="muted">{ui.esc(names.get(m.chat_id, ""))}</div>'
            ),
            _direction_badge(m.direction),
            ui.badge(classify_text(m.text)),
            ui.esc(ui.clip(m.text, 200)),
        )
        for m in messages
    ]
    filters = (
        '<form method="get" action="/messages"><div class="row">'
        '<div><label>chat_id</label><input type="text" name="chat" value="'
        + ui.esc(chat)
        + '"></div><div><label>جهت</label><select name="direction">'
        + "".join(
            f'<option value="{value}"{" selected" if direction == value else ""}>{label}</option>'
            for value, label in (("", "همه"), ("in", "ورودی"), ("out", "خروجی"))
        )
        + f'</select></div><div><label>تعداد</label><input type="number" name="limit" value="{limit}">'
        + '</div></div><button class="ghost" type="submit">فیلتر</button></form>'
    )
    body = ui.card(
        f"پیام‌ها ({len(messages)} ردیف)",
        filters + ui.table(["زمان", "چت", "جهت", "دسته", "متن"], rows),
    )
    return html_response(
        ui.layout("پیام‌ها", body, active="/messages", csrf=request.get("csrf", ""))
    )


async def h_analysis(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    store = state.store()
    messages = store.recent_messages(limit=3000)
    summary = analyze_concerns(messages, incoming_only=True, top_n=5)
    csrf = request.get("csrf", "")
    sync_form = (
        ui.form_open("/analysis/sync", csrf)
        + '<button class="ghost" type="submit">همگام‌سازی قبل از تحلیل</button></form>'
    )
    body = (
        ui.card(
            "تحلیل", sync_form, note=f"بر پایه {len(messages)} پیام ذخیره‌شده (ورودی‌ها)."
        )
        + _analysis_card(summary)
    )
    return html_response(
        ui.layout(
            "تحلیل",
            body,
            active="/analysis",
            csrf=csrf,
            notice=request.query.get("notice", ""),
            error=request.query.get("error", ""),
        )
    )


async def h_analysis_sync(request: web.Request) -> web.Response:
    await form_and_csrf(request)
    state: PanelState = request.app[STATE_KEY]
    job = start_job(request.app, "همگام‌سازی تاریخچه", _make_sync_runner(state))
    return redirect("/job?busy=1") if job is None else redirect("/job")


# ---------------------------------------------------------------------------
# system
# ---------------------------------------------------------------------------


def _read_tail(path: Any, lines: int) -> str:
    try:
        text = Path(str(path)).read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return "(فایل هنوز ساخته نشده)"
    return "\n".join(text.splitlines()[-lines:]) or "(خالی)"


async def h_system(request: web.Request) -> web.Response:
    state: PanelState = request.app[STATE_KEY]
    book = state.book()
    store = state.store()
    info = ui.kv_table(
        [
            ("دفترچه مخاطبین", ui.Raw(f'<span class="mono">{ui.esc(book.path)}</span>')),
            ("تعداد مخاطبین", str(len(book))),
            ("صندوق پیام", ui.Raw(f'<span class="mono">{ui.esc(store.path)}</span>')),
            ("فایل KB facts", ui.Raw(f'<span class="mono">{ui.esc(facts_path())}</span>')),
            ("لاگ runner", ui.Raw(f'<span class="mono">{ui.esc(log_path())}</span>')),
        ]
    )
    body = (
        ui.card("مسیرها و وضعیت", info)
        + ui.card(
            "KB facts (بدون متن خام، فیلتر PII)",
            f'<pre class="log">{ui.esc(_read_tail(facts_path(), 60))}</pre>',
        )
        + ui.card(
            "لاگ runner (۱۰۰ خط آخر)",
            f'<pre class="log">{ui.esc(_read_tail(log_path(), 100))}</pre>',
        )
    )
    return html_response(
        ui.layout("سیستم", body, active="/system", csrf=request.get("csrf", ""))
    )


# ---------------------------------------------------------------------------
# app factory
# ---------------------------------------------------------------------------


def build_app(
    *, token: str, no_auth: bool = False, dialog_limit: int = 200
) -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app[STATE_KEY] = PanelState(token=token, no_auth=no_auth, dialog_limit=dialog_limit)
    app[JOBBOX_KEY] = {"job": None, "task": None}
    app.add_routes(
        [
            web.get("/", h_dashboard),
            web.get("/login", h_login_get),
            web.post("/login", h_login_post),
            web.get("/logout", h_logout),
            web.post("/send", h_send_post),
            web.get("/job", h_job),
            web.get("/api/job", h_api_job),
            web.get("/contacts", h_contacts),
            web.post("/contacts/add", h_contacts_add),
            web.post("/contacts/remove", h_contacts_remove),
            web.post("/contacts/refresh", h_contacts_refresh),
            web.get("/inbox", h_inbox),
            web.post("/inbox/sync", h_inbox_sync),
            web.post("/inbox/live", h_inbox_live),
            web.get("/messages", h_messages),
            web.get("/analysis", h_analysis),
            web.post("/analysis/sync", h_analysis_sync),
            web.get("/system", h_system),
            web.get("/healthz", h_healthz),
        ]
    )
    return app