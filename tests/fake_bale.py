"""Fake aiobale client for unit tests (no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FakePeer:
    id: int
    username: Optional[str] = None


class FakeBaleClient:
    """Records calls; inject failures via `errors`."""

    instances: List["FakeBaleClient"] = []

    def __init__(self, dispatcher=None, session_file: str = "", **kwargs):
        self.dispatcher = dispatcher
        self.session_file = session_file
        self.search_contact_calls: List[str] = []
        self.search_username_calls: List[str] = []
        self.send_calls: List[Dict[str, Any]] = []
        self.errors: Dict[str, Exception] = {}
        self.contacts: Dict[str, int] = {}
        self.usernames: Dict[str, int] = {}
        self._me_id = 111
        self._started = False
        FakeBaleClient.instances.append(self)

    async def start(self, run_in_background: bool = False):
        if "start" in self.errors:
            raise self.errors["start"]
        self._started = True

    async def stop(self):
        self._started = False

    async def get_me(self):
        return FakePeer(id=self._me_id)

    async def search_contact(self, phone: str):
        self.search_contact_calls.append(phone)
        if "search_contact" in self.errors:
            raise self.errors["search_contact"]
        uid = self.contacts.get(phone)
        return FakePeer(id=uid) if uid else None

    async def search_by_username(self, username: str):
        self.search_username_calls.append(username)
        if "search_by_username" in self.errors:
            raise self.errors["search_by_username"]
        uid = self.usernames.get(username.lower())
        return FakePeer(id=uid) if uid else None

    async def send_message(self, **kwargs):
        self.send_calls.append(kwargs)
        if "send_message" in self.errors:
            raise self.errors["send_message"]
        return type("Msg", (), {"message_id": 9001, "date": 1})()


class FakeDispatcher:
    def __init__(self):
        self._handlers = []

    def message(self):
        def decorator(fn):
            self._handlers.append(fn)
            return fn

        return decorator
