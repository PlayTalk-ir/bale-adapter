"""Fake aiobale client for unit tests (no network).

Mirrors aiobale-py 0.3.8 Client surface used by bale-adapter:
  search_contact(phone_number) -> Optional[InfoPeer-like]
  search_username(username) -> ContactResponse-like (.user / .group)
  send_message(..., message_id=...) -> Message-like
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FakePeer:
    id: int
    username: Optional[str] = None


@dataclass
class FakeContactResponse:
    user: Optional[FakePeer] = None
    group: Any = None


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

    async def search_contact(self, phone_number: str):
        self.search_contact_calls.append(phone_number)
        if "search_contact" in self.errors:
            raise self.errors["search_contact"]
        uid = self.contacts.get(phone_number)
        return FakePeer(id=uid) if uid else None

    async def search_username(self, username: str) -> FakeContactResponse:
        self.search_username_calls.append(username)
        if "search_username" in self.errors:
            raise self.errors["search_username"]
        uid = self.usernames.get(username.lower())
        if uid:
            return FakeContactResponse(user=FakePeer(id=uid))
        return FakeContactResponse(user=None)

    async def send_message(
        self,
        text: str,
        chat_id: int,
        chat_type: Any,
        message_id: Optional[int] = None,
        **kwargs: Any,
    ):
        call = {
            "text": text,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "message_id": message_id,
            **kwargs,
        }
        self.send_calls.append(call)
        if "send_message" in self.errors:
            raise self.errors["send_message"]
        mid = message_id if message_id is not None else 9001
        return type("Msg", (), {"message_id": mid, "date": 1})()


class FakeDispatcher:
    def __init__(self):
        self._handlers = []

    def message(self):
        def decorator(fn):
            self._handlers.append(fn)
            return fn

        return decorator
