"""Integration tests for the admin panel (aiohttp TestClient + fake Bale client).

No network and no aiobale here: ``panel.bale_client`` is monkeypatched with an
async-context-manager fake, so the full request → job → result flow runs
offline. CI installs aiohttp for these tests (deploy.yml test step).
"""

import asyncio
import contextlib
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bale_platform import panel as panel_mod
from bale_platform.outbound import TARGET_CHAT_ID, TARGET_NAME, TARGET_PHONE
from bale_platform.panel import classify_target
from bale_platform.store import SupportStore

TOKEN = "test-operator-signing-secret"
PASSWORD = "test-operator-password"
USER = "admin"


@pytest.fixture(autouse=True)
def fake_chat_type(monkeypatch):
    """Stand in for aiobale's ChatType.PRIVATE (absent in CI)."""
    from bale_platform import contacts as contacts_mod
    from bale_platform import outbound as outbound_mod

    monkeypatch.setattr(contacts_mod, "_private_chat_type", lambda: "PRIVATE")
    monkeypatch.setattr(outbound_mod, "_private_chat_type", lambda: "PRIVATE")


class FakeClient:
    """Duck-typed aiobale client (only what the panel calls)."""

    def __init__(self) -> None:
        self.sent: list = []
        self.phones = {"989924466793": 4242}

    async def get_me(self):
        return SimpleNamespace(id=999)

    async def search_contact(self, phone_number):
        chat_id = self.phones.get(phone_number)
        return SimpleNamespace(id=chat_id) if chat_id else None

    async def send_message(self, *, text, chat_id, chat_type=None):
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=1000 + len(self.sent), date=1700000000000)

    async def load_contacts(self):
        return []

    async def load_dialogs(self, limit=40):
        return []

    async def load_users(self, peers):
        return []


@pytest.fixture()
def fake_bale(monkeypatch):
    client = FakeClient()

    @contextlib.asynccontextmanager
    async def factory():
        yield client

    monkeypatch.setattr(panel_mod, "bale_client", factory)
    return client


async def make_http(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("BALE_STORE_PATH", str(tmp_path / "inbox.sqlite"))
    monkeypatch.setenv("BALE_CONTACTS_PATH", str(tmp_path / "contacts.sqlite"))
    app = panel_mod.build_app(token=TOKEN, password=PASSWORD, username=USER)
    # aiohttp refuses cookies from IP hosts unless the jar is "unsafe"
    jar = aiohttp.CookieJar(unsafe=True)
    http = TestClient(TestServer(app), cookie_jar=jar)
    await http.start_server()
    return http


async def login_and_csrf(http: TestClient) -> str:
    login = await http.post(
        "/login",
        data={"username": USER, "password": PASSWORD},
        allow_redirects=False,
    )
    assert login.status == 302, "login should redirect on success"
    page = await http.get("/contacts")
    match = re.search(r'name="_csrf" value="([^"]+)"', await page.text())
    assert match, "no CSRF token rendered"
    return match.group(1)


async def wait_for_job(http: TestClient) -> dict:
    data: dict = {}
    for _ in range(200):
        response = await http.get("/api/job")
        data = await response.json()
        if data.get("done"):
            return data
        await asyncio.sleep(0.02)
    raise AssertionError("job never finished")


class TestAuth:
    @pytest.mark.asyncio
    async def test_anonymous_is_redirected_to_login(self, tmp_path, monkeypatch):
        http = await make_http(tmp_path, monkeypatch)
        try:
            response = await http.get("/", allow_redirects=False)
            assert response.status == 302
            assert response.headers["Location"] == "/login"
            assert (await http.get("/api/job")).status == 401
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_wrong_token_then_correct_token(self, tmp_path, monkeypatch):
        http = await make_http(tmp_path, monkeypatch)
        try:
            wrong = await http.post(
                "/login", data={"username": USER, "password": "wrong-password"}
            )
            assert wrong.status == 401
            right = await http.post(
                "/login",
                data={"username": USER, "password": PASSWORD},
                allow_redirects=False,
            )
            assert right.status == 302
            page = await http.get("/")
            assert page.status == 200
            assert "پنل ادمین بله پلی‌تاک" in await page.text()
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_post_without_csrf_is_rejected(self, tmp_path, monkeypatch):
        http = await make_http(tmp_path, monkeypatch)
        try:
            await http.post(
                "/login", data={"username": USER, "password": PASSWORD}
            )
            response = await http.post(
                "/contacts/add", data={"name": "x", "target": "1"}
            )
            assert response.status == 403
        finally:
            await http.close()


class TestApiTokens:
    @pytest.mark.asyncio
    async def test_create_token_from_panel(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BALE_API_TOKENS_PATH", str(tmp_path / "api_tokens.json"))
        http = await make_http(tmp_path, monkeypatch)
        try:
            csrf = await login_and_csrf(http)
            resp = await http.post(
                "/api-tokens/create",
                data={"label": "CI", "_csrf": csrf},
                allow_redirects=False,
            )
            assert resp.status == 302
            page = await http.get("/api-tokens")
            text = await page.text()
            assert "توکن جدید" in text
            assert "CI" in text or "پیشوند" in text
        finally:
            await http.close()


class TestContactBookPages:
    @pytest.mark.asyncio
    async def test_add_and_remove_contact(self, tmp_path, monkeypatch):
        http = await make_http(tmp_path, monkeypatch)
        try:
            token = await login_and_csrf(http)
            response = await http.post(
                "/contacts/add",
                data={"name": "باران صلواتی", "target": "1547970538", "_csrf": token},
                allow_redirects=False,
            )
            assert response.status == 302
            page = await (await http.get("/contacts")).text()
            assert "باران صلواتی" in page and "manual" in page

            remove = await http.post(
                "/contacts/remove",
                data={"chat_id": "1547970538", "_csrf": token},
                allow_redirects=False,
            )
            assert remove.status == 302
            page = await (await http.get("/contacts")).text()
            assert "باران صلواتی" not in page
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_add_by_phone_resolves_then_saves(self, tmp_path, monkeypatch, fake_bale):
        http = await make_http(tmp_path, monkeypatch)
        try:
            token = await login_and_csrf(http)
            response = await http.post(
                "/contacts/add",
                data={"name": "علی", "target": "09924466793", "_csrf": token},
                allow_redirects=False,
            )
            assert response.status == 302
            state = panel_mod.PanelState(token=TOKEN, password=PASSWORD, username=USER)
            assert state.book().get(4242).name == "علی"
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_refresh_job_reports_diagnostics(self, tmp_path, monkeypatch, fake_bale):
        http = await make_http(tmp_path, monkeypatch)
        try:
            token = await login_and_csrf(http)
            response = await http.post(
                "/contacts/refresh", data={"_csrf": token}, allow_redirects=False
            )
            assert response.headers["Location"] == "/job"
            data = await wait_for_job(http)
            assert data["done"] is True
            assert any("dialogs: 0" in line for line in data["lines"])
        finally:
            await http.close()


class TestSendFlow:
    @pytest.mark.asyncio
    async def test_preview_never_sends(self, tmp_path, monkeypatch, fake_bale):
        http = await make_http(tmp_path, monkeypatch)
        try:
            token = await login_and_csrf(http)
            response = await http.post(
                "/send",
                data={
                    "targets": "باران صلواتی\n09924466793",
                    "text": "سلام",
                    "preview": "1",
                    "delay": "0",
                    "_csrf": token,
                },
                allow_redirects=False,
            )
            assert response.headers["Location"] == "/job"
            data = await wait_for_job(http)
            assert fake_bale.sent == []
            assert any("[OK]" in line for line in data["lines"])
            assert any("dry-run" in line for line in data["lines"])
            assert data["can_confirm"] is True
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_real_send_resolves_names_and_stores_message(
        self, tmp_path, monkeypatch, fake_bale
    ):
        http = await make_http(tmp_path, monkeypatch)
        try:
            token = await login_and_csrf(http)
            panel_mod.ContactBook(panel_mod.contacts_path()).add_manual(
                "باران صلواتی", 1547970538
            )
            await http.post(
                "/send",
                data={
                    "targets": "باران صلواتی",
                    "text": "سلام تست",
                    "delay": "0",
                    "_csrf": token,
                },
                allow_redirects=False,
            )
            await wait_for_job(http)
            assert fake_bale.sent == [(1547970538, "سلام تست")]

            rows = SupportStore(panel_mod.store_path()).recent_messages()
            assert rows and rows[0].direction == "out"
            assert rows[0].chat_id == "1547970538"
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_unknown_name_fails_without_sending(self, tmp_path, monkeypatch, fake_bale):
        http = await make_http(tmp_path, monkeypatch)
        try:
            token = await login_and_csrf(http)
            await http.post(
                "/send",
                data={
                    "targets": "کسی که نیست",
                    "text": "سلام",
                    "delay": "0",
                    "_csrf": token,
                },
                allow_redirects=False,
            )
            data = await wait_for_job(http)
            assert any("[FAIL]" in line for line in data["lines"])
            assert fake_bale.sent == []
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_missing_fields_redirect_with_error(self, tmp_path, monkeypatch):
        http = await make_http(tmp_path, monkeypatch)
        try:
            token = await login_and_csrf(http)
            response = await http.post(
                "/send",
                data={"targets": "", "text": "", "_csrf": token},
                allow_redirects=False,
            )
            assert "error=" in response.headers["Location"]
        finally:
            await http.close()


class TestPages:
    @pytest.mark.asyncio
    async def test_dashboard_shows_book_and_messages(self, tmp_path, monkeypatch, fake_bale):
        http = await make_http(tmp_path, monkeypatch)
        try:
            await login_and_csrf(http)
            panel_mod.ContactBook(panel_mod.contacts_path()).add_manual(
                "باران صلواتی", 1547970538
            )
            SupportStore(panel_mod.store_path()).upsert_message(
                {
                    "chat_id": "1547970538",
                    "message_id": 7,
                    "sender_id": "1",
                    "text": "سلام، قیمت دوره چقدره؟",
                    "timestamp": "t",
                    "date_ms": 1700000000000,
                },
                direction="in",
            )
            page = await (await http.get("/")).text()
            assert "باران صلواتی" in page
            assert "متن پیام" in page
            assert "قیمت" in page
        finally:
            await http.close()

    @pytest.mark.asyncio
    async def test_system_page_shows_paths(self, tmp_path, monkeypatch):
        http = await make_http(tmp_path, monkeypatch)
        try:
            await login_and_csrf(http)
            page = await (await http.get("/system")).text()
            assert "contacts.sqlite" in page and "inbox.sqlite" in page
        finally:
            await http.close()


class TestMisc:
    def test_classify_target_kinds(self):
        assert classify_target("1547970538") == TARGET_CHAT_ID
        assert classify_target("09924466793") == TARGET_PHONE
        assert classify_target("باران") == TARGET_NAME

    def test_store_agents_lists_distinct_ack_ids(self, tmp_path):
        store = SupportStore(tmp_path / "inbox.sqlite")
        assert store.agents() == []
        store.ack_chat("sara", "1", 5)
        store.ack_chat("erfan", "2", 5)
        store.ack_chat("sara", "3", 5)
        assert store.agents() == ["erfan", "sara"]